"""The guest's manage token and the keyed address hash (``guest_tokens``),
and what each token opens once a confirmation made a guest account."""

import datetime as dt
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.crud.shared_list_guest import shared_list_guest as crud_guest
from app.logic.shared_lists import guest_tokens
from app.logic.shared_lists.erase import erase_guests
from app.models.shared_list import SharedList
from tests.fixtures.guest_signups import confirm_address
from tests.fixtures.shared_lists import ListGuest, ListGuestFactory


async def test_a_token_resolves_to_its_guest(
    db_session: AsyncSession,
    test_shared_list: SharedList,
    make_list_guest: ListGuestFactory,
) -> None:
    signed = await make_list_guest(test_shared_list)
    token = guest_tokens.manage_token(signed.guest)

    assert token.startswith(f"{signed.user.id.hex}.")
    # The nonce is an input, never a part.
    assert signed.guest.manage_nonce is not None
    assert signed.guest.manage_nonce not in token
    resolved = await guest_tokens.resolve(db_session, token)
    assert resolved is not None
    assert (resolved.guest.user_id, resolved.from_mail) == (signed.user.id, False)


async def test_only_the_mail_token_says_it_came_from_the_mailbox(
    db_session: AsyncSession,
    test_shared_list: SharedList,
    make_list_guest: ListGuestFactory,
) -> None:
    """Two keys of their own: the token the sign-up answers with is no mail
    token, and neither can be turned into the other."""
    signed = await make_list_guest(test_shared_list)
    from_form = guest_tokens.manage_token(signed.guest)
    from_mail = guest_tokens.mail_token(signed.guest)

    assert from_mail != from_form
    assert from_mail.partition(".")[0] == from_form.partition(".")[0]
    resolved = await guest_tokens.resolve(db_session, from_mail)
    assert resolved is not None
    assert (resolved.guest.user_id, resolved.from_mail) == (signed.user.id, True)


async def test_a_tampered_or_foreign_token_resolves_to_nobody(
    db_session: AsyncSession,
    test_shared_list: SharedList,
    make_list_guest: ListGuestFactory,
) -> None:
    one = await make_list_guest(test_shared_list)
    two = await make_list_guest(test_shared_list, name="Zwei")
    token = guest_tokens.manage_token(one.guest)
    _, _, tag = token.partition(".")
    other_tag = guest_tokens.manage_token(two.guest).partition(".")[2]

    for bad in (
        "",
        "no-dot",
        f"{'z' * 32}.{tag}",
        f"{uuid.uuid4().hex}.{tag}",
        f"{one.user.id.hex}.{other_tag}",
        f"{one.user.id.hex}.{tag[:-1]}",
        f"{two.user.id.hex}.{tag}",
    ):
        assert await guest_tokens.resolve(db_session, bad) is None, bad


async def test_a_new_nonce_or_secret_kills_every_link(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    test_shared_list: SharedList,
    make_list_guest: ListGuestFactory,
) -> None:
    signed = await make_list_guest(test_shared_list)
    tokens = (
        guest_tokens.manage_token(signed.guest),
        guest_tokens.mail_token(signed.guest),
    )

    monkeypatch.setattr(settings, "SECRET_KEY", "another-secret-key-of-32-bytes!!")
    for token in tokens:
        assert await guest_tokens.resolve(db_session, token) is None
    monkeypatch.undo()

    signed.guest.manage_nonce = "f" * 32
    db_session.add(signed.guest)
    await db_session.flush()
    for token in tokens:
        assert await guest_tokens.resolve(db_session, token) is None

    signed.guest.manage_nonce = None
    db_session.add(signed.guest)
    await db_session.flush()
    for token in tokens:
        assert await guest_tokens.resolve(db_session, token) is None


def test_the_link_keeps_the_token_in_the_fragment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FRONTEND_HOST", "https://app.example.test")
    assert (
        guest_tokens.manage_url("abc.def")
        == "https://app.example.test/guest-signup#abc.def"
    )


def test_the_address_hash_is_keyed_and_stable(monkeypatch: pytest.MonkeyPatch) -> None:
    hashed = guest_tokens.address_hash("anna@example.org")
    assert len(hashed) == 64
    assert "anna" not in hashed
    assert guest_tokens.address_hash("anna@example.org") == hashed
    assert guest_tokens.address_hash("berta@example.org") != hashed
    monkeypatch.setattr(settings, "SECRET_KEY", "another-secret-key-of-32-bytes!!")
    assert guest_tokens.address_hash("anna@example.org") != hashed


# ── Guest accounts (guest_account.confirm) ──────────────────────


async def _family(
    db: AsyncSession, shared_list: SharedList, make_list_guest: ListGuestFactory
) -> tuple[ListGuest, ListGuest, str, str]:
    """An account (promoted) and a second chain merged into it, and the
    merged chain's two old tokens."""
    account = await make_list_guest(shared_list, name="Maria", email="fam@example.org")
    merged = await make_list_guest(shared_list, name="Tom", email="fam@example.org")
    old_mail = guest_tokens.mail_token(merged.guest)
    old_response = guest_tokens.manage_token(merged.guest)
    await confirm_address(db, account.guest)
    await confirm_address(db, merged.guest)
    return account, merged, old_mail, old_response


async def test_a_merged_chains_mail_link_opens_the_account(
    db_session: AsyncSession,
    test_shared_list: SharedList,
    make_list_guest: ListGuestFactory,
) -> None:
    account, _, old_mail, old_response = await _family(
        db_session, test_shared_list, make_list_guest
    )

    resolved = await guest_tokens.resolve(db_session, old_mail)
    assert resolved is not None
    assert (resolved.guest.user_id, resolved.from_mail) == (account.user.id, True)
    # The token its sign-up answered with is retired.
    assert await guest_tokens.resolve(db_session, old_response) is None
    assert await guest_tokens.retired_response_token(db_session, old_response)
    assert not await guest_tokens.retired_response_token(db_session, old_mail)


async def test_a_promoted_chains_response_token_is_retired(
    db_session: AsyncSession,
    test_shared_list: SharedList,
    make_list_guest: ListGuestFactory,
) -> None:
    chain = await make_list_guest(test_shared_list, email="solo@example.org")
    response = guest_tokens.manage_token(chain.guest)
    assert not await guest_tokens.retired_response_token(db_session, response)

    await confirm_address(db_session, chain.guest)

    assert await guest_tokens.resolve(db_session, response) is None
    assert await guest_tokens.retired_response_token(db_session, response)
    resolved = await guest_tokens.resolve(
        db_session, guest_tokens.mail_token(chain.guest)
    )
    assert resolved is not None and resolved.from_mail


async def test_peek_reports_only_a_verified_token_and_which_key(
    db_session: AsyncSession,
    test_shared_list: SharedList,
    make_list_guest: ListGuestFactory,
) -> None:
    account, merged, old_mail, _ = await _family(
        db_session, test_shared_list, make_list_guest
    )
    chain = await make_list_guest(test_shared_list, email="other@example.org")
    head, _, tag = guest_tokens.mail_token(account.guest).partition(".")

    for bad in ("garbage", f"{head}.{tag[:-1]}", f"{merged.user.id.hex}.{tag}"):
        assert await guest_tokens.peek(db_session, bad) is None, bad
    by_mail = await guest_tokens.peek(
        db_session, guest_tokens.mail_token(account.guest)
    )
    by_form = await guest_tokens.peek(
        db_session, guest_tokens.manage_token(chain.guest)
    )
    by_alias = await guest_tokens.peek(db_session, old_mail)
    assert by_mail is not None and by_form is not None and by_alias is not None
    assert (by_mail.from_mail, by_form.from_mail, by_alias.from_mail) == (
        True,
        False,
        True,
    )
    assert by_mail.guest is account.guest and by_mail.alias is None
    assert by_alias.guest is None and by_alias.holder_id == account.user.id


async def test_peek_finds_nothing_behind_a_retired_response_token(
    db_session: AsyncSession,
    test_shared_list: SharedList,
    make_list_guest: ListGuestFactory,
) -> None:
    """What ``resolve`` refuses: the confirmation took the chain from whoever
    typed the address, so the confirm route counts such a token as a miss."""
    account, _, _, old_response = await _family(
        db_session, test_shared_list, make_list_guest
    )

    for retired in (guest_tokens.manage_token(account.guest), old_response):
        assert await guest_tokens.retired_response_token(db_session, retired)
        assert await guest_tokens.peek(db_session, retired) is None


async def test_erasing_the_account_kills_its_aliases(
    db_session: AsyncSession,
    test_shared_list: SharedList,
    make_list_guest: ListGuestFactory,
) -> None:
    account, merged, old_mail, _ = await _family(
        db_session, test_shared_list, make_list_guest
    )

    await erase_guests(
        db_session, user_ids=[account.user.id], now=dt.datetime(2026, 6, 1)
    )

    assert await guest_tokens.resolve(db_session, old_mail) is None
    assert await guest_tokens.peek(db_session, old_mail) is None
    assert await crud_guest.get_alias(db_session, user_id=merged.user.id) is None
