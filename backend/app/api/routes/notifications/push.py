from fastapi import APIRouter

from app.api.deps import CurrentUser, DBDep
from app.core.config import settings
from app.core.errors import raise_problem
from app.crud.push_subscription import push_subscription as crud_push
from app.schemas.notification import (
    PushSubscriptionCreate,
    PushSubscriptionRead,
)

router = APIRouter()


@router.post(
    "/push-subscriptions", response_model=PushSubscriptionRead, status_code=201
)
async def register_push_subscription(
    sub_in: PushSubscriptionCreate,
    session: DBDep,
    current_user: CurrentUser,
) -> PushSubscriptionRead:
    """Register a Web Push subscription for the current user."""
    sub = await crud_push.create_or_update(
        session, user_id=current_user.id, obj_in=sub_in
    )
    return PushSubscriptionRead.model_validate(sub)


@router.get("/push-subscriptions", response_model=list[PushSubscriptionRead])
async def list_push_subscriptions(
    session: DBDep,
    current_user: CurrentUser,
) -> list[PushSubscriptionRead]:
    """List the current user's push subscriptions."""
    subs = await crud_push.get_by_user(session, user_id=current_user.id)
    return [PushSubscriptionRead.model_validate(s) for s in subs]


@router.delete("/push-subscriptions/{subscription_id}", status_code=204)
async def remove_push_subscription(
    subscription_id: str,
    session: DBDep,
    current_user: CurrentUser,
) -> None:
    """Remove a push subscription."""
    sub = await crud_push.get(session, subscription_id)
    if not sub:
        raise_problem(404, code="push.not_found", detail="Push subscription not found")

    if sub.user_id != current_user.id:
        raise_problem(403, code="push.forbidden", detail="Not your subscription")
    await session.delete(sub)


@router.get("/vapid-public-key")
async def get_vapid_public_key(
    current_user: CurrentUser,  # noqa: ARG001
) -> dict[str, str]:
    """Get the VAPID public key for Web Push subscription."""
    if not settings.VAPID_PUBLIC_KEY:
        raise_problem(
            503,
            code="push.not_configured",
            detail="Push notifications are not configured",
        )

    return {"vapid_public_key": settings.VAPID_PUBLIC_KEY}
