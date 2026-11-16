"""The operator's lookup, export and erasure of guest data, and lifting a
"Das war ich nicht" (``/list-guests``).

A guest's address is not in ``users.email`` and the admin user search leaves
guests out, so these are how a data-subject request sent to the operator is
answered. Superadmin only; an event admin is refused.
"""

import datetime as dt
import uuid

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.logic.shared_lists import guest_quota
from app.models.event import Event
from app.models.shared_list import GuestMailSuppression, SharedList
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from app.models.voucher import VoucherEntry
from tests.fixtures.guest_signups import add_shift, confirm_address, freeze_clocks
from tests.fixtures.shared_lists import ListGuestFactory

API = "/api/v1/list-guests"


@pytest.fixture(autouse=True)
def _clocks(monkeypatch: pytest.MonkeyPatch) -> None:
    freeze_clocks(monkeypatch)


async def _search(client: AsyncClient, q: str) -> Response:
    return await client.get(API, params={"q": q})


@pytest.mark.asyncio
@pytest.mark.usefixtures("as_admin")
class TestLookup:
    async def test_by_address_name_or_phone(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        test_task: Task,
        test_event: Event,
    ) -> None:
        shift = await add_shift(db_session, test_task)
        hanna = await make_list_guest(
            test_shared_list,
            name="Hanna Lind",
            email="hanna@example.org",
            phone="+49 30 1234",
            shifts=[shift],
        )
        await make_list_guest(test_shared_list, name="Ida Berg", shifts=[shift])

        by_address = (await _search(async_client, " Hanna@Example.org ")).json()
        assert by_address["total"] == 1
        [row] = by_address["items"]
        assert row == {
            "guest_user_id": str(hanna.user.id),
            "name": "Hanna Lind",
            "email": "hanna@example.org",
            "phone": "+49 30 1234",
            "event_id": str(test_event.id),
            "event_name": test_event.name,
            "booking_count": 1,
            "last_signup_at": "2026-06-01T06:00:00",
            "erased": False,
        }
        assert [
            r["name"] for r in (await _search(async_client, "lind")).json()["items"]
        ] == ["Hanna Lind"]
        assert [
            r["name"] for r in (await _search(async_client, "30 12")).json()["items"]
        ] == ["Hanna Lind"]
        # Part of an address finds nobody: only the whole one does.
        assert (await _search(async_client, "hanna@")).json()["total"] == 0

    async def test_a_pooled_sign_up_is_found_under_its_own_name(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        test_task: Task,
    ) -> None:
        """Tom's sign-up was confirmed into Maria's account: the operator asked
        about Tom finds the account that holds it."""
        maria = await make_list_guest(
            test_shared_list, name="Maria Lind", email="lind@example.org"
        )
        tom = await make_list_guest(
            test_shared_list,
            name="Tom Lind",
            email="lind@example.org",
            phone="0170 77",
            shifts=[await add_shift(db_session, test_task)],
        )
        await confirm_address(db_session, maria.guest)
        await confirm_address(db_session, tom.guest)

        for q in ("tom lind", "0170 77"):
            found = (await _search(async_client, q)).json()
            assert [r["guest_user_id"] for r in found["items"]] == [
                str(maria.user.id)
            ], q

    async def test_members_are_not_guests(
        self, async_client: AsyncClient, test_user: User
    ) -> None:
        assert test_user.name
        assert (await _search(async_client, test_user.name)).json()["total"] == 0

    async def test_a_short_query_is_refused(self, async_client: AsyncClient) -> None:
        assert (await _search(async_client, "ab")).status_code == 422


@pytest.mark.asyncio
@pytest.mark.usefixtures("as_admin")
class TestExportAndErase:
    async def test_the_export_holds_everything_stored(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        test_task: Task,
        test_event: Event,
    ) -> None:
        shift = await add_shift(db_session, test_task)
        signed = await make_list_guest(
            test_shared_list,
            name="Jana",
            email="jana@example.org",
            phone="0171 2",
            language="en",
            shifts=[shift],
        )

        response = await async_client.get(f"{API}/{signed.user.id}")

        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Jana"
        assert body["email"] == "jana@example.org"
        assert body["phone"] == "0171 2"
        assert body["preferred_language"] == "en"
        assert body["confirmed_at"] is None
        assert body["vouchers"] == []
        assert body["shared_list_id"] == str(test_shared_list.id)
        assert body["event_id"] == str(test_event.id)
        assert body["erased_at"] is None
        assert body["created_at"]
        [booking] = body["bookings"]
        assert booking["booking_id"] == str(signed.bookings[0].id)
        assert booking["task_name"] == test_task.name
        assert booking["event_name"] == test_event.name
        assert (booking["name"], booking["phone"], booking["show_first_name"]) == (
            "Jana",
            "0171 2",
            False,
        )
        assert "manage_nonce" not in response.text
        assert signed.guest.manage_nonce is not None
        assert signed.guest.manage_nonce not in response.text

    async def test_the_export_holds_the_vouchers_without_names_or_notes(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        test_task: Task,
        test_event: Event,
    ) -> None:
        test_task.vouchers_per_shift = 2
        db_session.add(test_task)
        signed = await make_list_guest(
            test_shared_list,
            email="kim@example.org",
            shifts=[await add_shift(db_session, test_task, day=dt.date(2026, 5, 20))],
        )
        db_session.add_all(
            [
                VoucherEntry(
                    event_id=test_event.id,
                    user_id=signed.user.id,
                    kind="redemption",
                    amount=-1,
                    method="code",
                    actor_name="Stand Steffi",
                    task_name="Theke",
                ),
                VoucherEntry(
                    event_id=test_event.id,
                    user_id=signed.user.id,
                    kind="adjustment",
                    amount=1,
                    note="Für Kim, Handy leer",
                    actor_name="Olga Organisatorin",
                ),
            ]
        )
        await db_session.flush()
        await confirm_address(db_session, signed.guest)

        body = (await async_client.get(f"{API}/{signed.user.id}")).json()

        assert body["confirmed_at"] is not None
        [vouchers] = body["vouchers"]
        assert vouchers["event_id"] == str(test_event.id)
        summary = vouchers["account"]["summary"]
        assert (summary["earned"], summary["redeemed"], summary["adjusted"]) == (
            2,
            1,
            1,
        )
        assert sorted(
            (e["kind"], e["amount"], e["note"], e["actor_name"])
            for e in vouchers["account"]["entries"]
        ) == [("adjustment", 1, None, None), ("redemption", -1, None, None)]
        assert "Steffi" not in str(body) and "Handy" not in str(body)

    async def test_not_a_guest(
        self, async_client: AsyncClient, test_user: User
    ) -> None:
        for response in (
            await async_client.get(f"{API}/{test_user.id}"),
            await async_client.get(f"{API}/{uuid.uuid4()}"),
            await async_client.post(f"{API}/{test_user.id}/erase"),
        ):
            assert response.status_code == 404
            assert response.json()["code"] == "guest_signup.not_found"

    async def test_erase(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        test_shift: Shift,
    ) -> None:
        signed = await make_list_guest(
            test_shared_list, name="Kai", email="kai@example.org", shifts=[test_shift]
        )
        response = await async_client.post(f"{API}/{signed.user.id}/erase")
        assert response.status_code == 204
        body = (await async_client.get(f"{API}/{signed.user.id}")).json()
        assert body["name"] is None
        assert body["email"] is None
        assert body["erased"] is True
        assert body["erased_at"] == "2026-06-01T06:00:00"
        assert len(body["bookings"]) == 1

    async def test_works_with_the_lists_switched_off(
        self,
        async_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
    ) -> None:
        monkeypatch.setattr(settings, "SHARED_LISTS_ENABLED", False)
        signed = await make_list_guest(test_shared_list, email="lea@example.org")
        assert (await _search(async_client, "lea@example.org")).json()["total"] == 1
        assert (
            await async_client.post(f"{API}/{signed.user.id}/erase")
        ).status_code == 204


@pytest.mark.asyncio
@pytest.mark.usefixtures("as_admin")
class TestLiftMailSuppression:
    async def test_an_address_is_mailed_again(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Its owner asks the operator, who types it as anyone would."""
        await guest_quota.suppress(db_session, address="nina@example.org")

        lifted = await async_client.post(
            f"{API}/mail-suppressions/lift", json={"email": " Nina@Example.org "}
        )
        again = await async_client.post(
            f"{API}/mail-suppressions/lift", json={"email": "nina@example.org"}
        )

        assert lifted.status_code == 204
        assert again.status_code == 404
        assert again.json()["code"] == "guest_signup.not_suppressed"
        assert (
            await db_session.scalar(
                select(func.count()).select_from(GuestMailSuppression)
            )
        ) == 0

    async def test_a_malformed_address_is_a_422(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.post(
            f"{API}/mail-suppressions/lift", json={"email": "not an address"}
        )
        assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.usefixtures("as_event_admin")
async def test_event_admins_are_refused(
    async_client: AsyncClient,
    test_shared_list: SharedList,
    make_list_guest: ListGuestFactory,
) -> None:
    signed = await make_list_guest(test_shared_list, email="mo@example.org")
    for response in (
        await _search(async_client, "mo@example.org"),
        await async_client.get(f"{API}/{signed.user.id}"),
        await async_client.post(f"{API}/{signed.user.id}/erase"),
        await async_client.post(
            f"{API}/mail-suppressions/lift", json={"email": "mo@example.org"}
        ),
    ):
        assert response.status_code == 403
