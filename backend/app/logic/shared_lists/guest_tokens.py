"""The guest's manage link, and the keyed hash that stands for an address.

**Manage tokens.** ``<user id hex>.<tag>``, where the tag is an HMAC over the
guest user's id and the ``manage_nonce`` of its ``shared_list_guests`` row,
under a key derived from ``SECRET_KEY``. Nothing secret is stored, so every
mail can rebuild the link and a database dump does not reveal it. Setting the
nonce to NULL (erasing, "Das war ich nicht", retention) revokes every link at
once; rotating ``SECRET_KEY`` does too, as it signs out everyone.

Two tokens open the same manage page, under keys of their own. The sign-up
answers with :func:`manage_token`, so whoever filled in the form holds it,
and that may be anyone who typed the address. Every mail links to
:func:`mail_token`, which only whoever reads that mailbox holds. Both read,
cancel, switch reminders, erase the chain and show a voucher code. Only the
mail's may say "Das war ich nicht", which stops all mail to the address for
good, so a stranger cannot silence somebody else's address by typing it into
a form; and only the mail's may confirm the address (``guest_account``).

**Accounts.** A confirmation makes the chain the guest account of its
address, or merges it into the one that exists. :func:`resolve` accepts:

=========================  =========  =====================================
Token                      Found      Opens
=========================  =========  =====================================
mail, unconfirmed chain    guest row  the chain, ``from_mail``
response, unconfirmed      guest row  the chain
mail, account              guest row  the account, ``from_mail``
response, account          guest row  nothing: the confirmation retired it
mail, merged chain         alias      the alias's account, ``from_mail``
response, merged chain     alias      nothing: the confirmation retired it
=========================  =========  =====================================

So an account is only ever reached through a mail token, and whoever merely
typed the address loses the chain when its owner confirms it.
:func:`retired_response_token` lets a sign-up that continues with such a
token start a new chain instead.

A token reaches the browser only in a URL fragment (``/guest-signup#…``) and
in POST bodies, never in a path or a query, which the request log and nginx
write down.

**Address hash.** ``guest_activity_log`` and ``guest_mail_suppressions`` keep
an address only as an HMAC of its normalised form, under a third key, so the
daily ceilings and "never write to me again" work without the address in
clear text.
"""

import base64
import hashlib
import hmac
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.crud.shared_list_guest import shared_list_guest as crud_guest
from app.models.shared_list import SharedListGuest, SharedListGuestAlias

_MANAGE_KEY_LABEL = b"wirksam/guest-manage/v1"
_MAIL_KEY_LABEL = b"wirksam/guest-mail/v1"
_ADDRESS_KEY_LABEL = b"wirksam/guest-address/v1"


@dataclass(frozen=True, slots=True)
class GuestKey:
    """A manage token that resolved, and to whom: a chain or an account."""

    guest: SharedListGuest
    #: It is the link from a mail, so the caller reads the chain's address.
    from_mail: bool


@dataclass(frozen=True, slots=True)
class Peeked:
    """A token that opens something, read without a lock (:func:`peek`).

    Exactly one of ``guest`` and ``alias`` is set: the row the token names,
    or the alias a merged chain left behind, which only a mail token opens.
    """

    guest: SharedListGuest | None
    alias: SharedListGuestAlias | None
    #: The mail's key matched; otherwise the sign-up response's did.
    from_mail: bool

    @property
    def holder_id(self) -> uuid.UUID:
        """The guest user the token stands for: the row's, or the account a
        merged chain's alias points at."""
        if self.guest is not None:
            return self.guest.user_id
        assert self.alias is not None
        return self.alias.account_user_id


def _key(label: bytes) -> bytes:
    """A key of its own per use, so no HMAC here can be replayed as another."""
    return hmac.new(settings.SECRET_KEY.encode(), label, hashlib.sha256).digest()


def _signed(user_id: uuid.UUID, nonce: str, label: bytes) -> str:
    mac = hmac.new(
        _key(label), f"{user_id.hex}:{nonce}".encode(), hashlib.sha256
    ).digest()
    tag = base64.urlsafe_b64encode(mac).rstrip(b"=").decode()
    return f"{user_id.hex}.{tag}"


def _token(guest: SharedListGuest, label: bytes) -> str:
    # The caller has just read a guest with a nonce; erased guests have none.
    assert guest.manage_nonce is not None
    return _signed(guest.user_id, guest.manage_nonce, label)


def _matches(token: str, user_id: uuid.UUID, nonce: str, label: bytes) -> bool:
    """Whether ``token`` is the one under ``label``, in constant time."""
    return hmac.compare_digest(token.encode(), _signed(user_id, nonce, label).encode())


def manage_token(guest: SharedListGuest) -> str:
    """The token the sign-up answers with. Only for a guest whose links are alive."""
    return _token(guest, _MANAGE_KEY_LABEL)


def mail_token(guest: SharedListGuest) -> str:
    """The token every mail links to. Only for a guest whose links are alive."""
    return _token(guest, _MAIL_KEY_LABEL)


def manage_url(token: str) -> str:
    """The page behind a manage token; the token stays in the fragment."""
    return f"{settings.FRONTEND_HOST}/guest-signup#{token}"


def _user_id(token: str) -> uuid.UUID | None:
    head, dot, _ = token.partition(".")
    if not dot or len(head) != 32:
        return None
    try:
        return uuid.UUID(hex=head)
    except ValueError:
        return None


async def resolve(session: AsyncSession, token: str) -> GuestKey | None:
    """The chain or account a token opens (the module docstring's table),
    locked ``FOR UPDATE``; None for a token that is malformed, forged,
    revoked, retired, or of an erased guest.

    The lock comes first, as on every path that changes a guest's sign-ups,
    so the check and what the caller does next see the same nonce. A merged
    chain's mail token locks only its account's row.
    """
    user_id = _user_id(token)
    if user_id is None:
        return None
    guest = await crud_guest.get_for_update(session, user_id=user_id)
    if guest is not None:
        nonce = guest.manage_nonce
        if nonce is None:
            return None
        if _matches(token, user_id, nonce, _MAIL_KEY_LABEL):
            return GuestKey(guest=guest, from_mail=True)
        if guest.confirmed_at is None and _matches(
            token, user_id, nonce, _MANAGE_KEY_LABEL
        ):
            return GuestKey(guest=guest, from_mail=False)
        return None
    alias = await crud_guest.get_alias(session, user_id=user_id)
    if alias is None or not _matches(
        token, user_id, alias.manage_nonce, _MAIL_KEY_LABEL
    ):
        return None
    account = await crud_guest.get_for_update(session, user_id=alias.account_user_id)
    if account is None or account.manage_nonce is None or account.erased_at is not None:
        return None
    return GuestKey(guest=account, from_mail=True)


async def retired_response_token(session: AsyncSession, token: str) -> bool:
    """Whether ``token`` is the sign-up response's token of a chain that was
    confirmed since, promoted or merged. :func:`resolve` refuses it, and a
    sign-up continuing with it starts a new chain."""
    user_id = _user_id(token)
    if user_id is None:
        return False
    guest = await crud_guest.get_by_user_id(session, user_id=user_id)
    if guest is not None:
        return (
            guest.confirmed_at is not None
            and guest.manage_nonce is not None
            and _matches(token, user_id, guest.manage_nonce, _MANAGE_KEY_LABEL)
        )
    alias = await crud_guest.get_alias(session, user_id=user_id)
    return alias is not None and _matches(
        token, user_id, alias.manage_nonce, _MANAGE_KEY_LABEL
    )


async def peek(session: AsyncSession, token: str) -> Peeked | None:
    """The row or alias behind a token that :func:`resolve` would accept
    (the module docstring's table), read without a lock; None for anything
    else, a retired response token included, so nothing unverified or dead
    ever comes back. A confirmation looks first, so a forged token takes no
    lock and a dead one counts as a miss."""
    user_id = _user_id(token)
    if user_id is None:
        return None
    guest = await crud_guest.get_by_user_id(session, user_id=user_id)
    if guest is not None:
        nonce = guest.manage_nonce
        if nonce is None:
            return None
        if _matches(token, user_id, nonce, _MAIL_KEY_LABEL):
            return Peeked(guest=guest, alias=None, from_mail=True)
        if guest.confirmed_at is None and _matches(
            token, user_id, nonce, _MANAGE_KEY_LABEL
        ):
            return Peeked(guest=guest, alias=None, from_mail=False)
        return None
    alias = await crud_guest.get_alias(session, user_id=user_id)
    if alias is not None and _matches(
        token, user_id, alias.manage_nonce, _MAIL_KEY_LABEL
    ):
        return Peeked(guest=None, alias=alias, from_mail=True)
    return None


def address_hash(email: str) -> str:
    """The keyed hash of a normalised address (``normalize.normalize_email``)."""
    return hmac.new(
        _key(_ADDRESS_KEY_LABEL), email.encode(), hashlib.sha256
    ).hexdigest()
