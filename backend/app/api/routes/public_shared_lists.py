"""The public side of shared lists: the list page, signing up without an
account, and the guest's own manage link: their sign-ups, confirming their
address, and the voucher code they show at a stand.

No identity dependency: the list code and the manage token are the only keys.
An unknown, rotated or wrong code is one 404, ``shared_list.not_found``, and
every failing manage token another, ``guest_signup.not_found``, so neither
tells a guesser anything.

The guest routes count calls per guest once the token resolves, and per IP
only when it does not (``core/rate_limit.py``): a queue of guests showing
codes at a stand behind one venue NAT must not share a bucket. A guest's
mail link and the token its sign-up answered with count apart, since whoever
typed the address holds the latter and must not use up the calls of whoever
reads the mailbox.

The list routes answer 404 ``shared_list.disabled`` while
``SHARED_LISTS_ENABLED`` is off; the guest's own ``/guest-signups`` routes do
not. Switching the lists off stops new sign-ups, while the guests already
signed up keep getting mail about their shifts, and each mail sends them
here to take their name off, stop the reminders, erase their data or say
"Das war ich nicht".

The manage token travels in the body (and in the page's URL fragment), never
in a path or a query, which the request log and nginx would write down.

``verify_turnstile`` and ``send_guest_mail`` are imported by name so tests can
replace them here.
"""

import uuid
from typing import NoReturn

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DBDep, require_shared_lists_enabled
from app.core.config import settings
from app.core.errors import raise_problem
from app.core.rate_limit import (
    RateLimiter,
    client_ip,
    guest_ip_limiter,
    guest_link_miss_limiter,
    guest_manage_limiter,
    guest_pass_status_limiter,
    shared_list_miss_limiter,
    shared_list_signup_ip_limiter,
    shared_list_signup_limiter,
    shared_list_view_limiter,
    voucher_pass_limiter,
)
from app.core.turnstile import verify_turnstile
from app.crud.shared_list import shared_list as crud_shared_list
from app.logic import clock
from app.logic.shared_lists import (
    guest_account,
    guest_manage,
    guest_quota,
    guest_tokens,
    guest_vouchers,
)
from app.logic.shared_lists.erase import erase_guests
from app.logic.shared_lists.guest_mail import send_guest_mail
from app.logic.shared_lists.guest_tokens import GuestKey
from app.logic.shared_lists.public_page import build_public_list, count_view
from app.logic.shared_lists.signup import sign_up
from app.models.event import Event
from app.schemas.public_shared_list import (
    GuestCancelRequest,
    GuestConfirmResult,
    GuestPassRequest,
    GuestPassStatusRequest,
    GuestRemindersRequest,
    GuestSignupManage,
    GuestTokenRequest,
    PublicSharedList,
    PublicSignupRequest,
    PublicSignupResult,
)
from app.schemas.voucher import VoucherPassRead, VoucherPassStatus

router = APIRouter(prefix="/public", tags=["public-shared-lists"])

#: The kill switch, on the list routes only.
_ENABLED = [Depends(require_shared_lists_enabled)]


@router.get(
    "/shared-lists/{code}", response_model=PublicSharedList, dependencies=_ENABLED
)
async def get_public_shared_list(
    code: str, request: Request, response: Response, session: DBDep
) -> PublicSharedList:
    """A list's public page; its shifts only while it is live.

    Counts as a view while live, never for the organisers' preview.
    """
    ip = client_ip(request)
    await shared_list_view_limiter.check(ip)
    shared_list = await crud_shared_list.get_by_code(session, code=code)
    if shared_list is None:
        # Only misses count here: a scan for live codes meets this long
        # before a crowd opening one shared link would.
        await shared_list_miss_limiter.check(ip)
        raise_problem(404, code="shared_list.not_found", detail="Shared list not found")
    event = await session.get(Event, shared_list.event_id)
    assert event is not None  # shared_lists.event_id is a foreign key
    page = await build_public_list(session, shared_list, event=event)
    if page.status == "live":
        # Last: its row lock lasts only until the commit that follows.
        await count_view(session, shared_list.id)
    response.headers["Cache-Control"] = "no-store"
    return page


@router.post(
    "/shared-lists/{code}/signups",
    response_model=PublicSignupResult,
    status_code=201,
    dependencies=_ENABLED,
)
async def sign_up_on_shared_list(
    code: str,
    body: PublicSignupRequest,
    request: Request,
    session: DBDep,
    background_tasks: BackgroundTasks,
) -> PublicSignupResult:
    """Sign up for one shift without an account (``logic/shared_lists/signup.py``).

    The rate limits and the bot check come first, before a row is read.
    """
    ip = client_ip(request)
    await shared_list_signup_limiter.check(f"{ip}|{code}")
    await shared_list_signup_ip_limiter.check(ip)
    if settings.turnstile_enabled and not await verify_turnstile(
        body.turnstile_token, expected_action="shared-list-signup"
    ):
        raise_problem(403, code="auth.captcha_failed")
    outcome = await sign_up(session, code=code, form=body, now=clock.utc_now())
    if outcome.confirmation is not None:
        background_tasks.add_task(send_guest_mail, outcome.confirmation)
    return outcome.result


def _not_found() -> NoReturn:
    raise_problem(
        404, code="guest_signup.not_found", detail="This link does not work (any more)"
    )


def _bucket(user_id: uuid.UUID, *, from_mail: bool) -> str:
    """The per-guest rate-limit key of a token that resolved: one for the
    mail links, one for the sign-up's response token."""
    return f"guest:{user_id}:{'mail' if from_mail else 'response'}"


async def _guest(
    request: Request,
    session: AsyncSession,
    token: str,
    *,
    limiter: RateLimiter = guest_manage_limiter,
) -> GuestKey:
    """The guest behind a manage token, locked; 404 for any token that fails.

    The flood guard per IP comes before any database work; then a token that
    does not resolve counts against its IP, and one that does against its
    guest and kind of token (:func:`_bucket`), in ``limiter``.
    """
    ip = client_ip(request)
    await guest_ip_limiter.check(ip)
    key = await guest_tokens.resolve(session, token)
    if key is None:
        await guest_link_miss_limiter.check(ip)
        _not_found()
    await limiter.check(_bucket(key.guest.user_id, from_mail=key.from_mail))
    return key


@router.post("/guest-signups/manage", response_model=GuestSignupManage)
async def read_guest_signups(
    body: GuestTokenRequest, request: Request, session: DBDep
) -> GuestSignupManage:
    """The guest's sign-ups, each with its own event, place and options."""
    key = await _guest(request, session, body.token)
    return await guest_manage.manage_view(session, key)


@router.post("/guest-signups/cancel", response_model=GuestSignupManage)
async def cancel_guest_signup(
    body: GuestCancelRequest, request: Request, session: DBDep
) -> GuestSignupManage:
    """Take the guest off one shift, until it is over."""
    key = await _guest(request, session, body.token)
    await guest_manage.cancel(session, guest=key.guest, booking_id=body.booking_id)
    return await guest_manage.manage_view(session, key)


@router.post("/guest-signups/reminders", response_model=GuestSignupManage)
async def set_guest_reminders(
    body: GuestRemindersRequest, request: Request, session: DBDep
) -> GuestSignupManage:
    """Switch the reminder mail on or off for every shift still ahead."""
    key = await _guest(request, session, body.token)
    await guest_manage.set_reminders(session, guest=key.guest, enabled=body.enabled)
    return await guest_manage.manage_view(session, key)


@router.post("/guest-signups/erase", status_code=204)
async def erase_guest_data(
    body: GuestTokenRequest, request: Request, session: DBDep
) -> None:
    """Delete the guest's data; worked shifts stay, without a name."""
    key = await _guest(request, session, body.token)
    await erase_guests(session, user_ids=[key.guest.user_id], now=clock.utc_now())


@router.post("/guest-signups/not-me", status_code=204)
async def reject_guest_signup(
    body: GuestTokenRequest, request: Request, session: DBDep
) -> None:
    """Erase the chain, as "Das war ich nicht" asks, and never mail this
    address again, unless the address has a confirmed guest account.

    403 ``guest_signup.mail_link_required`` for the token the sign-up
    answered with: whoever typed an address holds that one, and must not be
    able to stop all mail to somebody else. 409
    ``guest_signup.reject_confirmed`` on an account: its owner confirmed
    those sign-ups, and can cancel them or erase. The suppression is global,
    so while the address has an account at any event it would also stop the
    mail about the sign-ups its owner confirmed; then only the chain goes.
    """
    key = await _guest(request, session, body.token)
    if not key.from_mail:
        raise_problem(
            403,
            code="guest_signup.mail_link_required",
            detail="Only the link in the mail can say this was not you",
        )
    if key.guest.confirmed_at is not None:
        raise_problem(
            409,
            code="guest_signup.reject_confirmed",
            detail="You confirmed these sign-ups yourself",
        )
    email = key.guest.email
    if email is not None and await guest_quota.rejection_suppresses(
        session, address=email
    ):
        await guest_quota.suppress(session, address=email)
    await erase_guests(session, user_ids=[key.guest.user_id], now=clock.utc_now())


@router.post("/guest-signups/confirm", response_model=GuestConfirmResult)
async def confirm_guest_address(
    body: GuestTokenRequest, request: Request, session: DBDep
) -> GuestConfirmResult:
    """Confirm the address behind a mail link, as "Ja, das bin ich" asks
    (``logic/shared_lists/guest_account.py``).

    The chain becomes the address's guest account at its event, or is merged
    into the one that exists. Answers with the account's mail token, which
    the page uses from then on. Only from a button: the page's automatic
    ``/manage`` stays read-only, so a link scanner confirms nothing. The token
    is verified before any lock is taken, and a dead one, the response token
    a confirmation retired included, counts as a miss.
    """
    ip = client_ip(request)
    await guest_ip_limiter.check(ip)
    peeked = await guest_tokens.peek(session, body.token)
    if peeked is None:
        await guest_link_miss_limiter.check(ip)
        _not_found()
    await guest_manage_limiter.check(
        _bucket(peeked.holder_id, from_mail=peeked.from_mail)
    )
    key = await guest_account.confirm(
        session, peeked=peeked, token=body.token, now=clock.utc_now()
    )
    return GuestConfirmResult(
        token=guest_tokens.mail_token(key.guest),
        manage=await guest_manage.manage_view(session, key),
    )


@router.post(
    "/guest-signups/vouchers/pass", response_model=VoucherPassRead, status_code=201
)
async def issue_guest_voucher_pass(
    body: GuestPassRequest, request: Request, session: DBDep
) -> VoucherPassRead:
    """A fresh voucher code for one event, as members get theirs; the guest's
    previous unused code there stops working, unless a redeemer holds it.

    Any live token of the chain or account may ask. 404
    ``guest_signup.not_found`` for an event in which the guest has no
    vouchers, 429 ``voucher.rate_limited`` past 20 a minute.
    """
    key = await _guest(request, session, body.token, limiter=voucher_pass_limiter)
    return await guest_vouchers.issue_pass(
        session, guest=key.guest, event_id=body.event_id, now_utc=clock.utc_now()
    )


@router.post("/guest-signups/vouchers/pass-status", response_model=VoucherPassStatus)
async def read_guest_voucher_pass(
    body: GuestPassStatusRequest, request: Request, session: DBDep
) -> VoucherPassStatus:
    """What happened to one of the guest's codes: still showing, being
    redeemed, used, or expired. 404 ``voucher.pass_not_found`` once it was
    replaced, or deleted by a confirmation."""
    key = await _guest(request, session, body.token, limiter=guest_pass_status_limiter)
    return await guest_vouchers.pass_status(
        session, guest=key.guest, event_id=body.event_id, pass_id=body.pass_id
    )
