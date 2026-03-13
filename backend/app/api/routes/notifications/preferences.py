from fastapi import APIRouter

from app.api.deps import CurrentUser, DBDep
from app.core.errors import raise_problem
from app.crud.notification_subscription import (
    notification_subscription as crud_subscription,
)
from app.models.notification import NotificationSubscription
from app.schemas.notification import (
    NotificationPreferencesBulkUpdate,
    NotificationSubscriptionCreate,
    NotificationSubscriptionRead,
    NotificationSubscriptionUpdate,
)

router = APIRouter()


@router.get("/preferences", response_model=list[NotificationSubscriptionRead])
async def list_preferences(
    session: DBDep,
    current_user: CurrentUser,
) -> list[NotificationSubscription]:
    """Get the current user's notification preferences."""
    prefs = await crud_subscription.get_user_preferences(
        session, user_id=current_user.id
    )
    return list(prefs)


@router.put("/preferences", response_model=list[NotificationSubscriptionRead])
async def bulk_update_preferences(
    body: NotificationPreferencesBulkUpdate,
    session: DBDep,
    current_user: CurrentUser,
) -> list[NotificationSubscription]:
    """Bulk upsert notification preferences (full matrix from frontend)."""
    results = await crud_subscription.bulk_upsert(
        session, user_id=current_user.id, preferences=body.preferences
    )
    return results


@router.post(
    "/preferences", response_model=NotificationSubscriptionRead, status_code=201
)
async def create_preference(
    pref_in: NotificationSubscriptionCreate,
    session: DBDep,
    current_user: CurrentUser,
):
    """Create a single notification subscription."""
    results = await crud_subscription.bulk_upsert(
        session, user_id=current_user.id, preferences=[pref_in]
    )
    return results[0]


@router.patch(
    "/preferences/{preference_id}", response_model=NotificationSubscriptionRead
)
async def update_preference(
    preference_id: str,
    pref_in: NotificationSubscriptionUpdate,
    session: DBDep,
    current_user: CurrentUser,
):
    """Update a single notification subscription."""
    existing = await crud_subscription.get(session, preference_id)
    if not existing:
        raise_problem(404, code="preference.not_found", detail="Preference not found")

    if existing.user_id != current_user.id:
        raise_problem(403, code="preference.forbidden", detail="Not your preference")
    return await crud_subscription.update(session, db_obj=existing, obj_in=pref_in)


@router.delete("/preferences/{preference_id}", status_code=204)
async def delete_preference(
    preference_id: str,
    session: DBDep,
    current_user: CurrentUser,
) -> None:
    """Delete a single notification subscription."""
    existing = await crud_subscription.get(session, preference_id)
    if not existing:
        raise_problem(404, code="preference.not_found", detail="Preference not found")

    if existing.user_id != current_user.id:
        raise_problem(403, code="preference.forbidden", detail="Not your preference")
    await session.delete(existing)
