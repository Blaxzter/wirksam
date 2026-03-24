import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter

from app.api.deps import CurrentUser, DBDep
from app.core.config import settings
from app.core.errors import raise_problem
from app.crud.telegram_binding import telegram_binding as crud_telegram
from app.schemas.notification import (
    TelegramBindingRead,
    TelegramBindResponse,
    TelegramConfigResponse,
    TelegramLoginData,
    TelegramVerifyRequest,
    TelegramWebhookUpdate,
)

router = APIRouter()


def _clean_bot_username(name: str | None) -> str | None:
    """Strip leading @ from bot username if present."""
    if name:
        return name.lstrip("@")
    return name


def _verify_telegram_login(data: TelegramLoginData, bot_token: str) -> bool:
    """Verify auth data from the Telegram Login Widget.

    See https://core.telegram.org/widgets/login#checking-authorization
    """
    check_hash = data.hash
    data_dict = data.model_dump(exclude={"hash"}, exclude_none=True)
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data_dict.items()))
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    computed = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(computed, check_hash)


@router.get("/telegram/config", response_model=TelegramConfigResponse)
async def get_telegram_config(
    _current_user: CurrentUser,
) -> TelegramConfigResponse:
    """Return Telegram bot configuration (needed for the Login Widget)."""
    return TelegramConfigResponse(
        bot_username=_clean_bot_username(settings.TELEGRAM_BOT_USERNAME),
        is_configured=bool(settings.TELEGRAM_BOT_TOKEN),
    )


@router.get("/telegram", response_model=TelegramBindingRead | None)
async def get_telegram_binding(
    session: DBDep,
    current_user: CurrentUser,
):
    """Get the current user's Telegram binding status."""
    binding = await crud_telegram.get_by_user(session, user_id=current_user.id)
    if not binding:
        return None
    return TelegramBindingRead.model_validate(binding)


@router.post("/telegram/login", response_model=TelegramBindingRead)
async def telegram_login(
    body: TelegramLoginData,
    session: DBDep,
    current_user: CurrentUser,
) -> TelegramBindingRead:
    """Authenticate via Telegram Login Widget and create a verified binding."""
    if not settings.TELEGRAM_BOT_TOKEN:
        raise_problem(
            400,
            code="telegram.not_configured",
            detail="Telegram bot is not configured",
        )

    if not _verify_telegram_login(body, settings.TELEGRAM_BOT_TOKEN):
        raise_problem(
            400,
            code="telegram.invalid_auth",
            detail="Invalid Telegram authentication data",
        )

    # Check auth_date is not too old (1 hour)
    if abs(time.time() - body.auth_date) > 3600:
        raise_problem(
            400,
            code="telegram.auth_expired",
            detail="Telegram authentication has expired",
        )

    binding = await crud_telegram.create_verified_binding(
        session,
        user_id=current_user.id,
        chat_id=str(body.id),
        username=body.username,
    )
    return TelegramBindingRead.model_validate(binding)


@router.post("/telegram/bind", response_model=TelegramBindResponse)
async def start_telegram_binding(
    session: DBDep,
    current_user: CurrentUser,
) -> TelegramBindResponse:
    """Start the Telegram binding process. Returns a verification code."""
    code = secrets.token_hex(4).upper()  # 8-char hex code
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=10)

    await crud_telegram.create_binding(
        session,
        user_id=current_user.id,
        verification_code=code,
        expires_at=expires_at,
    )

    return TelegramBindResponse(
        verification_code=code,
        bot_username=_clean_bot_username(settings.TELEGRAM_BOT_USERNAME),
        expires_at=expires_at,
    )


@router.post("/telegram/verify", response_model=TelegramBindingRead)
async def verify_telegram_binding(
    body: TelegramVerifyRequest,
    session: DBDep,
    current_user: CurrentUser,
) -> TelegramBindingRead:
    """Verify a Telegram binding with the code received from the bot."""
    binding = await crud_telegram.get_by_verification_code(
        session, code=body.verification_code
    )
    if not binding or binding.user_id != current_user.id:
        raise_problem(
            400,
            code="telegram.invalid_code",
            detail="Invalid or expired verification code",
        )

    # Check expiration
    if binding.verification_expires_at:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if now > binding.verification_expires_at:
            raise_problem(
                400,
                code="telegram.code_expired",
                detail="Verification code has expired",
            )

    verified = await crud_telegram.verify_binding(
        session,
        binding=binding,
        chat_id=body.telegram_chat_id,
        username=body.telegram_username,
    )
    return TelegramBindingRead.model_validate(verified)


@router.delete("/telegram", status_code=204)
async def unbind_telegram(
    session: DBDep,
    current_user: CurrentUser,
) -> None:
    """Remove the Telegram binding for the current user."""
    removed = await crud_telegram.remove_binding(session, user_id=current_user.id)
    if not removed:
        raise_problem(
            404, code="telegram.not_bound", detail="No Telegram binding found"
        )


@router.post("/telegram/webhook")
async def telegram_webhook(
    body: TelegramWebhookUpdate,
    session: DBDep,
) -> dict[str, bool]:
    """Receive updates from Telegram Bot API.

    When a user sends the verification code to the bot, this webhook
    finds the matching binding and verifies it.
    """
    message = body.message
    if not message or not message.text or not message.chat:
        return {"ok": True}

    text = message.text.strip()
    chat_id = str(message.chat.id)
    username = message.chat.username

    if not text or not chat_id:
        return {"ok": True}

    # Handle /start deep-link: Telegram sends "/start CODE" when user
    # opens a https://t.me/bot?start=CODE link
    if text.startswith("/start "):
        text = text[7:]

    code = text.upper()

    # Try to find a binding with this verification code
    binding = await crud_telegram.get_by_verification_code(session, code=code)
    if binding:
        if binding.verification_expires_at:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            if now > binding.verification_expires_at:
                return {"ok": True}

        await crud_telegram.verify_binding(
            session, binding=binding, chat_id=chat_id, username=username
        )

    return {"ok": True}
