"""Web Push notification channel using pywebpush."""

import json

from app.core.config import settings
from app.core.logger import get_logger
from app.logic.notifications.channels.base import NotificationChannel
from app.models.user import User
from app.schemas.notification import NotificationData

logger = get_logger(__name__)


class PushChannel(NotificationChannel):
    name = "push"

    def is_configured(self) -> bool:
        return bool(settings.VAPID_PRIVATE_KEY and settings.VAPID_PUBLIC_KEY)

    async def send(
        self,
        *,
        recipient: User,
        title: str,
        body: str,
        data: NotificationData | None = None,
    ) -> bool:
        if not self.is_configured():
            logger.warning("Push channel not configured (missing VAPID keys), skipping")
            return False

        if recipient.auth0_sub.startswith("demo|"):
            return False

        try:
            from pywebpush import WebPushException, webpush  # pyright: ignore[reportMissingTypeStubs]  # noqa: I001

            from app.core.db import async_session
            from app.crud.push_subscription import push_subscription as crud_push

            async with async_session() as db:
                subscriptions = await crud_push.get_by_user(db, user_id=recipient.id)

            if not subscriptions:
                logger.debug(f"No push subscriptions for user {recipient.id}")
                return False

            payload = json.dumps(
                {
                    "title": title,
                    "body": body,
                    "data": data or {},
                    "icon": "/favicon.ico",
                }
            )

            vapid_claims: dict[str, str | int] = {
                "sub": f"mailto:{settings.VAPID_CLAIMS_EMAIL or 'noreply@example.com'}",
            }

            any_success = False
            stale_endpoints: list[str] = []

            for sub in subscriptions:
                try:
                    webpush(
                        subscription_info={
                            "endpoint": sub.endpoint,
                            "keys": {
                                "p256dh": sub.p256dh_key,
                                "auth": sub.auth_key,
                            },
                        },
                        data=payload,
                        vapid_private_key=settings.VAPID_PRIVATE_KEY,
                        vapid_claims=vapid_claims,
                    )
                    any_success = True
                except WebPushException as e:
                    response = getattr(e, "response", None)
                    if (
                        response is not None
                        and getattr(response, "status_code", None) == 410
                    ):
                        stale_endpoints.append(sub.endpoint)
                        logger.info(
                            f"Removing stale push subscription: {sub.endpoint[:50]}..."
                        )
                    else:
                        logger.warning(
                            f"Push failed for endpoint {sub.endpoint[:50]}...: {e}"
                        )

            # Clean up stale subscriptions
            if stale_endpoints:
                async with async_session() as db:
                    for endpoint in stale_endpoints:
                        await crud_push.remove_by_endpoint(db, endpoint=endpoint)
                    await db.commit()

            return any_success

        except ImportError:
            logger.warning("pywebpush not installed, push notifications disabled")
            return False
        except Exception:
            logger.exception("Unexpected error in push channel")
            return False
