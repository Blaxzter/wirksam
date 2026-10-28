"""Team requirements, the checks a decider records, and request documents.

The privacy rule under test: a team stores *that* someone's police
certificate was seen (by whom, when, issued when), never the certificate. A
file attached to a request lives only until the request is decided.
"""

import io
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.crud.event_team import event_team as crud_team
from app.logic.team_documents import MAX_DOCUMENT_BYTES, safe_filename
from app.logic.team_requirements import add_years
from app.models.event import Event
from app.models.event_membership import EventMembership
from app.models.event_team import (
    EventTeam,
    EventTeamCheck,
    EventTeamDocument,
    EventTeamMember,
    EventTeamRequirement,
)
from app.models.user import User
from tests.fixtures.client import (
    _restore,  # pyright: ignore[reportPrivateUsage]
    _swap_identity,  # pyright: ignore[reportPrivateUsage]
)
from tests.fixtures.storage import drop_file

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"

POLICE = {
    "label": "Erweitertes Führungszeugnis",
    "description": "Don't keep a copy.",
    "ask_issue_date": True,
    "valid_for_years": 5,
    "accepts_document": False,
}
FIRST_AID = {
    "label": "Erste-Hilfe-Kurs",
    "ask_issue_date": True,
    "valid_for_years": 2,
    "accepts_document": True,
}


@contextmanager
def act_as(app: FastAPI, user: User) -> Generator[None]:
    originals = _swap_identity(app, user, superuser=False)
    try:
        yield
    finally:
        _restore(app, originals)


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), (200, 40, 40)).save(buffer, format="PNG")
    return buffer.getvalue()


async def _team(
    db_session: AsyncSession,
    event: Event,
    name: str,
    *requirements: dict[str, Any],
) -> EventTeam:
    team = EventTeam(event_id=event.id, name=name, requires_approval=True)
    db_session.add(team)
    await db_session.flush()
    for position, req in enumerate(requirements):
        db_session.add(EventTeamRequirement(team_id=team.id, position=position, **req))
    await db_session.flush()
    return team


async def _reqs(
    db_session: AsyncSession, team: EventTeam
) -> list[EventTeamRequirement]:
    return await crud_team.requirements(db_session, team_id=team.id)


async def _row(
    db_session: AsyncSession,
    team: EventTeam,
    user: User,
    *,
    status: str = "pending",
    role: str = "member",
) -> EventTeamMember:
    row = EventTeamMember(team_id=team.id, user_id=user.id, status=status, role=role)
    db_session.add(row)
    await db_session.flush()
    return row


def _url(team: EventTeam) -> str:
    return f"/api/v1/events/{team.event_id}/teams/{team.id}"


@pytest_asyncio.fixture
async def kids(db_session: AsyncSession, test_event: Event) -> EventTeam:
    """Childcare: police certificate (no file) and first aid (file allowed)."""
    return await _team(db_session, test_event, "Kinderbetreuung", POLICE, FIRST_AID)


async def _documents(db_session: AsyncSession) -> int:
    result = await db_session.execute(
        select(func.count()).select_from(EventTeamDocument)
    )
    return result.scalar_one()


@pytest.mark.asyncio
class TestRequirements:
    async def test_create_with_requirements(
        self, async_client: AsyncClient, test_event: Event, as_event_admin: None
    ):
        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/teams",
            json={"name": "Kinder", "requirements": [POLICE, FIRST_AID]},
        )
        assert r.status_code == 201, r.text
        reqs = r.json()["requirements"]
        assert [q["label"] for q in reqs] == [POLICE["label"], FIRST_AID["label"]]
        assert reqs[0]["valid_for_years"] == 5
        assert reqs[0]["accepts_document"] is False

    async def test_open_team_cannot_have_requirements(
        self, async_client: AsyncClient, test_event: Event, as_event_admin: None
    ):
        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/teams",
            json={
                "name": "Kinder",
                "requires_approval": False,
                "requirements": [POLICE],
            },
        )
        assert r.status_code == 422
        assert r.json()["code"] == "team.requirements_need_approval"

    async def test_cannot_open_a_team_that_has_requirements(
        self, async_client: AsyncClient, kids: EventTeam, as_event_admin: None
    ):
        r = await async_client.patch(_url(kids), json={"requires_approval": False})
        assert r.status_code == 422
        assert r.json()["code"] == "team.requirements_need_approval"

    async def test_duplicate_labels_are_refused(
        self, async_client: AsyncClient, test_event: Event, as_event_admin: None
    ):
        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/teams",
            json={
                "name": "Kinder",
                "requirements": [
                    POLICE,
                    {**POLICE, "label": " erweitertes führungszeugnis"},
                ],
            },
        )
        assert r.status_code == 422

    async def test_update_replaces_the_list(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        kids: EventTeam,
        test_user: User,
        test_event_admin_user: User,
        as_event_admin: None,
    ):
        """Kept ids keep their checks; dropped requirements take theirs along.

        Only the description changes here; a new label is a new question and
        is covered in ``TestEditingRequirements``.
        """
        police, first_aid = await _reqs(db_session, kids)
        member = await _row(db_session, kids, test_user, status="approved")
        await crud_team.record_check(
            db_session,
            member_id=member.id,
            requirement_id=police.id,
            issued_on=date.today(),
            expires_on=None,
            checked_by=test_event_admin_user,
        )
        await crud_team.record_check(
            db_session,
            member_id=member.id,
            requirement_id=first_aid.id,
            issued_on=date.today(),
            expires_on=None,
            checked_by=test_event_admin_user,
        )
        r = await async_client.patch(
            _url(kids),
            json={
                "requirements": [
                    {**POLICE, "id": str(police.id), "description": "Vorzeigen."},
                    {"label": "Führerschein Klasse B"},
                ]
            },
        )
        assert r.status_code == 200, r.text
        labels = [q["label"] for q in r.json()["requirements"]]
        assert labels == [POLICE["label"], "Führerschein Klasse B"]
        checks = (
            (
                await db_session.execute(
                    select(col(EventTeamCheck.requirement_id)).where(
                        col(EventTeamCheck.member_id) == member.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert list(checks) == [police.id]

    async def test_unknown_requirement_id_is_422(
        self, async_client: AsyncClient, kids: EventTeam, as_event_admin: None
    ):
        r = await async_client.patch(
            _url(kids),
            json={"requirements": [{**POLICE, "id": str(uuid.uuid4())}]},
        )
        assert r.status_code == 422
        assert r.json()["code"] == "team.requirement_not_found"

    async def test_volunteer_sees_the_requirements(
        self, async_client: AsyncClient, kids: EventTeam, test_event: Event
    ):
        [team] = (
            await async_client.get(f"/api/v1/events/{test_event.id}/teams")
        ).json()
        assert [q["label"] for q in team["requirements"]] == [
            POLICE["label"],
            FIRST_AID["label"],
        ]


@pytest.mark.asyncio
class TestApprovingWithChecks:
    async def test_approve_without_checks_is_422(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        kids: EventTeam,
        test_user: User,
        as_event_admin: None,
    ):
        row = await _row(db_session, kids, test_user)
        r = await async_client.post(
            f"{_url(kids)}/members/{test_user.id}/decide", json={"approve": True}
        )
        assert r.status_code == 422
        body = r.json()
        assert body["code"] == "team.checks_missing"
        assert len(body["requirement_ids"]) == 2
        await db_session.refresh(row)
        assert row.status == "pending"

    async def test_missing_issue_date_is_422(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        kids: EventTeam,
        test_user: User,
        as_event_admin: None,
    ):
        police, first_aid = await _reqs(db_session, kids)
        await _row(db_session, kids, test_user)
        r = await async_client.post(
            f"{_url(kids)}/members/{test_user.id}/decide",
            json={
                "approve": True,
                "checks": [
                    {"requirement_id": str(police.id)},
                    {"requirement_id": str(first_aid.id), "issued_on": "2026-01-10"},
                ],
            },
        )
        assert r.status_code == 422
        assert r.json()["requirement_ids"] == [str(police.id)]

    @pytest.mark.parametrize(
        ("issued", "code"),
        [
            (date.today() + timedelta(days=3), "team.check_issued_in_future"),
            (date.today() - timedelta(days=6 * 366), "team.check_expired"),
        ],
    )
    async def test_impossible_dates_are_refused(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        kids: EventTeam,
        test_user: User,
        as_event_admin: None,
        issued: date,
        code: str,
    ):
        police, first_aid = await _reqs(db_session, kids)
        await _row(db_session, kids, test_user)
        r = await async_client.post(
            f"{_url(kids)}/members/{test_user.id}/decide",
            json={
                "approve": True,
                "checks": [
                    {"requirement_id": str(police.id), "issued_on": issued.isoformat()},
                    {"requirement_id": str(first_aid.id), "issued_on": "2026-01-10"},
                ],
            },
        )
        assert r.status_code == 422
        assert r.json()["code"] == code

    async def test_checks_are_stored_with_their_expiry(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        kids: EventTeam,
        test_user: User,
        as_event_admin: None,
    ):
        police, first_aid = await _reqs(db_session, kids)
        await _row(db_session, kids, test_user)
        issued = date.today() - timedelta(days=30)
        r = await async_client.post(
            f"{_url(kids)}/members/{test_user.id}/decide",
            json={
                "approve": True,
                "checks": [
                    {"requirement_id": str(police.id), "issued_on": issued.isoformat()},
                    {
                        "requirement_id": str(first_aid.id),
                        "issued_on": issued.isoformat(),
                    },
                ],
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "approved"
        assert data["needs_recheck"] is False
        by_label = {c["label"]: c for c in data["checks"]}
        police_check = by_label[POLICE["label"]]
        assert police_check["checked_by_name"] == "Manager User"
        assert police_check["issued_on"] == issued.isoformat()
        assert police_check["expires_on"] == add_years(issued, 5).isoformat()
        assert by_label[FIRST_AID["label"]]["expires_on"] == (
            add_years(issued, 2).isoformat()
        )

    async def test_declining_needs_no_checks(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        kids: EventTeam,
        test_user: User,
        as_event_admin: None,
    ):
        await _row(db_session, kids, test_user)
        r = await async_client.post(
            f"{_url(kids)}/members/{test_user.id}/decide", json={"approve": False}
        )
        assert r.status_code == 200
        assert r.json()["checks"] == []

    async def test_placing_someone_directly_needs_the_checks_too(
        self,
        async_client: AsyncClient,
        kids: EventTeam,
        test_user: User,
        as_event_admin: None,
    ):
        r = await async_client.post(
            f"{_url(kids)}/members", json={"user_id": str(test_user.id)}
        )
        assert r.status_code == 422
        assert r.json()["code"] == "team.checks_missing"

    async def test_requirement_without_a_date_counts_from_the_check(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
        as_event_admin: None,
    ):
        team = await _team(
            db_session,
            test_event,
            "Fahrdienst",
            {"label": "Führerschein B"},
            {"label": "Belehrung", "valid_for_years": 1},
        )
        licence, briefing = await _reqs(db_session, team)
        r = await async_client.post(
            f"{_url(team)}/members",
            json={
                "user_id": str(test_user.id),
                "checks": [
                    # An issue date for a requirement that does not ask is dropped.
                    {"requirement_id": str(licence.id), "issued_on": "2020-01-01"},
                    {"requirement_id": str(briefing.id)},
                ],
            },
        )
        assert r.status_code == 201, r.text
        by_label = {c["label"]: c for c in r.json()["checks"]}
        assert by_label["Führerschein B"]["issued_on"] is None
        assert by_label["Führerschein B"]["expires_on"] is None
        assert by_label["Belehrung"]["expires_on"] == (
            add_years(date.today(), 1).isoformat()
        )


@pytest.mark.asyncio
class TestExpiry:
    async def _approved_with_old_check(
        self,
        db_session: AsyncSession,
        team: EventTeam,
        user: User,
        checker: User,
    ) -> EventTeamMember:
        police, first_aid = await _reqs(db_session, team)
        row = await _row(db_session, team, user, status="approved")
        await crud_team.record_check(
            db_session,
            member_id=row.id,
            requirement_id=police.id,
            issued_on=date.today() - timedelta(days=4 * 365),
            expires_on=date.today() + timedelta(days=300),
            checked_by=checker,
        )
        await crud_team.record_check(
            db_session,
            member_id=row.id,
            requirement_id=first_aid.id,
            issued_on=date.today() - timedelta(days=800),
            expires_on=date.today() - timedelta(days=70),
            checked_by=checker,
        )
        return row

    async def test_expired_check_flags_but_keeps_access(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        kids: EventTeam,
        test_user: User,
        test_event_admin_user: User,
        test_event: Event,
        app: FastAPI,
    ):
        await self._approved_with_old_check(
            db_session, kids, test_user, test_event_admin_user
        )
        [mine] = (
            await async_client.get(f"/api/v1/events/{test_event.id}/teams")
        ).json()
        assert mine["my_status"] == "approved"
        assert mine["my_needs_recheck"] is True

        with act_as(app, test_event_admin_user):
            [member] = (await async_client.get(f"{_url(kids)}/members")).json()
        assert member["needs_recheck"] is True
        expired = {c["label"]: c["expired"] for c in member["checks"]}
        assert expired == {POLICE["label"]: False, FIRST_AID["label"]: True}

    async def test_renewing_clears_the_flag(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        kids: EventTeam,
        test_user: User,
        test_event_admin_user: User,
        as_event_admin: None,
    ):
        await self._approved_with_old_check(
            db_session, kids, test_user, test_event_admin_user
        )
        _, first_aid = await _reqs(db_session, kids)
        r = await async_client.put(
            f"{_url(kids)}/members/{test_user.id}/checks",
            json={
                "checks": [
                    {
                        "requirement_id": str(first_aid.id),
                        "issued_on": date.today().isoformat(),
                    }
                ]
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["needs_recheck"] is False

    async def test_requirement_added_later_flags_existing_members(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
        as_event_admin: None,
    ):
        team = await _team(db_session, test_event, "Kasse")
        await _row(db_session, team, test_user, status="approved")
        r = await async_client.patch(
            _url(team), json={"requirements": [{"label": "Kassenschulung"}]}
        )
        assert r.status_code == 200
        [member] = (await async_client.get(f"{_url(team)}/members")).json()
        assert member["needs_recheck"] is True

    async def test_recording_checks_needs_a_manager_and_a_member(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        kids: EventTeam,
        test_user: User,
        test_event_admin_user: User,
        app: FastAPI,
    ):
        police, _ = await _reqs(db_session, kids)
        body = {
            "checks": [{"requirement_id": str(police.id), "issued_on": "2026-01-01"}]
        }
        url = f"{_url(kids)}/members/{test_user.id}/checks"
        assert (await async_client.put(url, json=body)).status_code == 403
        await _row(db_session, kids, test_user)
        with act_as(app, test_event_admin_user):
            pending = await async_client.put(url, json=body)
        assert pending.status_code == 404


async def _check_rows(
    db_session: AsyncSession, member: EventTeamMember
) -> dict[uuid.UUID, EventTeamCheck]:
    # populate_existing: the request changed these rows behind the session.
    result = await db_session.execute(
        select(EventTeamCheck)
        .where(col(EventTeamCheck.member_id) == member.id)
        .execution_options(populate_existing=True)
    )
    return {c.requirement_id: c for c in result.scalars().all()}


@pytest.mark.asyncio
class TestEditingRequirements:
    """A check answers one question; an edit that changes it drops the answer."""

    @pytest_asyncio.fixture
    async def member(
        self,
        db_session: AsyncSession,
        kids: EventTeam,
        test_user: User,
        test_event_admin_user: User,
    ) -> EventTeamMember:
        row = await _row(db_session, kids, test_user, status="approved")
        issued = date.today() - timedelta(days=100)
        for req in await _reqs(db_session, kids):
            await crud_team.record_check(
                db_session,
                member_id=row.id,
                requirement_id=req.id,
                issued_on=issued,
                expires_on=add_years(issued, req.valid_for_years or 0),
                checked_by=test_event_admin_user,
            )
        return row

    async def _patch(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        team: EventTeam,
        **police_changes: Any,
    ) -> None:
        police, first_aid = await _reqs(db_session, team)
        r = await client.patch(
            _url(team),
            json={
                "requirements": [
                    {**POLICE, "id": str(police.id), **police_changes},
                    {**FIRST_AID, "id": str(first_aid.id)},
                ]
            },
        )
        assert r.status_code == 200, r.text

    async def test_renaming_drops_the_checks(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        kids: EventTeam,
        member: EventTeamMember,
        as_event_admin: None,
    ):
        """Turning "First aid" into "Police certificate" must not carry ticks over."""
        _, first_aid = await _reqs(db_session, kids)
        await self._patch(async_client, db_session, kids, label="Führerschein")

        assert set(await _check_rows(db_session, member)) == {first_aid.id}
        [row] = (await async_client.get(f"{_url(kids)}/members")).json()
        assert row["needs_recheck"] is True

    async def test_spacing_and_case_are_not_a_new_label(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        kids: EventTeam,
        member: EventTeamMember,
        as_event_admin: None,
    ):
        await self._patch(
            async_client, db_session, kids, label="erweitertes  FÜHRUNGSZEUGNIS"
        )
        assert len(await _check_rows(db_session, member)) == 2

    async def test_asking_for_the_issue_date_drops_the_checks(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
        test_event_admin_user: User,
        as_event_admin: None,
    ):
        team = await _team(
            db_session, test_event, "Fahrdienst", {"label": "Führerschein"}
        )
        [licence] = await _reqs(db_session, team)
        row = await _row(db_session, team, test_user, status="approved")
        await crud_team.record_check(
            db_session,
            member_id=row.id,
            requirement_id=licence.id,
            issued_on=None,
            expires_on=None,
            checked_by=test_event_admin_user,
        )
        r = await async_client.patch(
            _url(team),
            json={
                "requirements": [
                    {
                        "id": str(licence.id),
                        "label": "Führerschein",
                        "ask_issue_date": True,
                    }
                ]
            },
        )
        assert r.status_code == 200, r.text
        assert await _check_rows(db_session, row) == {}

    async def test_new_validity_moves_the_expiry(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        kids: EventTeam,
        member: EventTeamMember,
        as_event_admin: None,
    ):
        police, _ = await _reqs(db_session, kids)
        await self._patch(async_client, db_session, kids, valid_for_years=3)
        check = (await _check_rows(db_session, member))[police.id]
        assert check.issued_on is not None
        assert check.expires_on == add_years(check.issued_on, 3)

        await self._patch(async_client, db_session, kids, valid_for_years=None)
        assert (await _check_rows(db_session, member))[police.id].expires_on is None

    async def test_no_longer_taking_files_deletes_attached_ones(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        kids: EventTeam,
        test_user: User,
        as_event_admin: None,
    ):
        police, first_aid = await _reqs(db_session, kids)
        row = await _row(db_session, kids, test_user)
        await crud_team.upsert_document(
            db_session,
            member_id=row.id,
            requirement_id=first_aid.id,
            filename="kurs.pdf",
            content_type="application/pdf",
            size=len(PDF),
            storage_key=await crud_team.store_document_file(
                db_session, data=PDF, content_type="application/pdf"
            ),
        )
        r = await async_client.patch(
            _url(kids),
            json={
                "requirements": [
                    {**POLICE, "id": str(police.id)},
                    {**FIRST_AID, "id": str(first_aid.id), "accepts_document": False},
                ]
            },
        )
        assert r.status_code == 200, r.text
        assert await _documents(db_session) == 0


@pytest.mark.asyncio
class TestReuse:
    async def test_valid_check_in_the_same_event_is_offered(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        kids: EventTeam,
        test_user: User,
        test_event_admin_user: User,
        as_event_admin: None,
    ):
        """A police certificate seen for the youth team counts for childcare."""
        youth = await _team(
            db_session,
            test_event,
            "Jugendarbeit",
            {**POLICE, "label": "erweitertes  führungszeugnis"},
        )
        [youth_police] = await _reqs(db_session, youth)
        youth_row = await _row(db_session, youth, test_user, status="approved")
        issued = date.today() - timedelta(days=100)
        await crud_team.record_check(
            db_session,
            member_id=youth_row.id,
            requirement_id=youth_police.id,
            issued_on=issued,
            expires_on=add_years(issued, 5),
            checked_by=test_event_admin_user,
        )
        await _row(db_session, kids, test_user)

        [request] = (
            await async_client.get(f"/api/v1/events/{test_event.id}/teams/requests")
        ).json()
        police, _ = await _reqs(db_session, kids)
        [reusable] = request["reusable_checks"]
        assert reusable["requirement_id"] == str(police.id)
        assert reusable["issued_on"] == issued.isoformat()
        assert reusable["source_team_name"] == "Jugendarbeit"
        assert request["other_team_names"] == ["Jugendarbeit"]

    async def test_expired_check_is_not_offered(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        kids: EventTeam,
        test_user: User,
        test_event_admin_user: User,
        as_event_admin: None,
    ):
        youth = await _team(db_session, test_event, "Jugendarbeit", POLICE)
        [youth_police] = await _reqs(db_session, youth)
        youth_row = await _row(db_session, youth, test_user, status="approved")
        await crud_team.record_check(
            db_session,
            member_id=youth_row.id,
            requirement_id=youth_police.id,
            issued_on=date.today() - timedelta(days=6 * 365),
            expires_on=date.today() - timedelta(days=1),
            checked_by=test_event_admin_user,
        )
        await _row(db_session, kids, test_user)
        [request] = (await async_client.get(f"{_url(kids)}/members")).json()
        assert request["reusable_checks"] == []

    async def test_another_events_check_is_never_offered(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_draft_event: Event,
        kids: EventTeam,
        test_user: User,
        test_event_admin_user: User,
        as_event_admin: None,
    ):
        other = await _team(db_session, test_draft_event, "Kinder", POLICE)
        [other_police] = await _reqs(db_session, other)
        other_row = await _row(db_session, other, test_user, status="approved")
        await crud_team.record_check(
            db_session,
            member_id=other_row.id,
            requirement_id=other_police.id,
            issued_on=date.today(),
            expires_on=None,
            checked_by=test_event_admin_user,
        )
        await _row(db_session, kids, test_user)
        [request] = (await async_client.get(f"{_url(kids)}/members")).json()
        assert request["reusable_checks"] == []
        assert request["other_team_names"] == []

    async def test_offered_when_adding_someone_directly(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        kids: EventTeam,
        test_user: User,
        test_event_admin_user: User,
        as_event_admin: None,
    ):
        """No request row to carry them, so the add dialog asks for them."""
        youth = await _team(db_session, test_event, "Jugendarbeit", POLICE)
        [youth_police] = await _reqs(db_session, youth)
        youth_row = await _row(db_session, youth, test_user, status="approved")
        issued = date.today() - timedelta(days=30)
        await crud_team.record_check(
            db_session,
            member_id=youth_row.id,
            requirement_id=youth_police.id,
            issued_on=issued,
            expires_on=add_years(issued, 5),
            checked_by=test_event_admin_user,
        )
        police, _ = await _reqs(db_session, kids)
        r = await async_client.get(
            f"{_url(kids)}/members/{test_user.id}/reusable-checks"
        )
        assert r.status_code == 200, r.text
        [reusable] = r.json()
        assert reusable["requirement_id"] == str(police.id)
        assert reusable["issued_on"] == issued.isoformat()
        assert reusable["source_team_name"] == "Jugendarbeit"

    async def test_reusable_checks_need_a_manager(
        self,
        async_client: AsyncClient,
        kids: EventTeam,
        test_user: User,
    ):
        r = await async_client.get(
            f"{_url(kids)}/members/{test_user.id}/reusable-checks"
        )
        assert r.status_code == 403


@pytest.mark.asyncio
class TestDocuments:
    async def _upload(
        self,
        client: AsyncClient,
        team: EventTeam,
        requirement: EventTeamRequirement,
        content: bytes,
        name: str = "card.pdf",
        content_type: str = "application/pdf",
    ):
        return await client.put(
            f"{_url(team)}/join/documents/{requirement.id}",
            files={"file": (name, content, content_type)},
        )

    async def test_requester_attaches_a_pdf(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        kids: EventTeam,
        test_event: Event,
        test_user: User,
    ):
        _, first_aid = await _reqs(db_session, kids)
        join = await async_client.post(
            f"{_url(kids)}/join", json={"message": "Kurs im März gemacht"}
        )
        assert join.status_code == 201
        r = await self._upload(async_client, kids, first_aid, PDF, name="../Kurs.pdf")
        assert r.status_code == 200, r.text
        assert r.json()["filename"] == "Kurs.pdf"
        assert r.json()["content_type"] == "application/pdf"
        assert r.json()["size"] == len(PDF)

        [team] = (
            await async_client.get(f"/api/v1/events/{test_event.id}/teams")
        ).json()
        assert [d["filename"] for d in team["my_documents"]] == ["Kurs.pdf"]

        own = await async_client.get(
            f"{_url(kids)}/members/{test_user.id}/documents/{first_aid.id}"
        )
        assert own.status_code == 200
        assert own.content == PDF
        assert own.headers["content-type"] == "application/pdf"
        assert own.headers["x-content-type-options"] == "nosniff"
        assert own.headers["cache-control"] == "private, no-store"
        assert own.headers["content-disposition"].startswith("inline;")

    async def test_photo_is_re_encoded(
        self, async_client: AsyncClient, db_session: AsyncSession, kids: EventTeam
    ):
        _, first_aid = await _reqs(db_session, kids)
        await async_client.post(f"{_url(kids)}/join", json={})
        r = await self._upload(
            async_client,
            kids,
            first_aid,
            _png(),
            name="IMG_1.png",
            content_type="image/png",
        )
        assert r.status_code == 200, r.text
        assert r.json()["content_type"] == "image/webp"
        assert r.json()["filename"] == "IMG_1.webp"

    async def test_second_upload_replaces_the_first(
        self, async_client: AsyncClient, db_session: AsyncSession, kids: EventTeam
    ):
        _, first_aid = await _reqs(db_session, kids)
        await async_client.post(f"{_url(kids)}/join", json={})
        await self._upload(async_client, kids, first_aid, PDF)
        await self._upload(async_client, kids, first_aid, PDF + b"%x", name="neu.pdf")
        assert await _documents(db_session) == 1

    async def test_racing_uploads_end_in_one_file(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        kids: EventTeam,
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """The loser of an insert race replaces the winner's file, not a 500."""
        _, first_aid = await _reqs(db_session, kids)
        row = await _row(db_session, kids, test_user)
        await crud_team.upsert_document(
            db_session,
            member_id=row.id,
            requirement_id=first_aid.id,
            filename="first.pdf",
            content_type="application/pdf",
            size=len(PDF),
            storage_key=await crud_team.store_document_file(
                db_session, data=PDF, content_type="application/pdf"
            ),
        )
        real_get = crud_team.get_document
        calls = 0

        async def miss_once(
            session: AsyncSession, *, member_id: uuid.UUID, requirement_id: uuid.UUID
        ) -> EventTeamDocument | None:
            # The first look sees nothing, as when the other upload has not
            # committed yet; the insert then hits the unique index.
            nonlocal calls
            calls += 1
            if calls == 1:
                return None
            return await real_get(
                session, member_id=member_id, requirement_id=requirement_id
            )

        monkeypatch.setattr(crud_team, "get_document", miss_once)
        r = await self._upload(async_client, kids, first_aid, PDF, name="second.pdf")
        assert r.status_code == 200, r.text
        assert r.json()["filename"] == "second.pdf"
        assert await _documents(db_session) == 1

    @pytest.mark.parametrize(
        ("content", "name", "code"),
        [
            (b"GIF89a....", "x.gif", "team.document_unsupported"),
            (b"<html><script>alert(1)</script>", "x.pdf", "team.document_unsupported"),
            (b"", "x.pdf", "team.document_unsupported"),
            (
                b"%PDF-" + b"0" * MAX_DOCUMENT_BYTES,
                "big.pdf",
                "team.document_too_large",
            ),
        ],
        ids=["gif", "html-as-pdf", "empty", "too-large"],
    )
    async def test_limits(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        kids: EventTeam,
        content: bytes,
        name: str,
        code: str,
    ):
        _, first_aid = await _reqs(db_session, kids)
        await async_client.post(f"{_url(kids)}/join", json={})
        r = await self._upload(async_client, kids, first_aid, content, name=name)
        assert r.status_code == 422
        assert r.json()["code"] == code
        assert await _documents(db_session) == 0

    async def test_requirement_without_a_file_slot_refuses(
        self, async_client: AsyncClient, db_session: AsyncSession, kids: EventTeam
    ):
        """The police certificate is never uploaded: nobody should keep a copy."""
        police, _ = await _reqs(db_session, kids)
        await async_client.post(f"{_url(kids)}/join", json={})
        r = await self._upload(async_client, kids, police, PDF)
        assert r.status_code == 422
        assert r.json()["code"] == "team.document_not_accepted"

    async def test_needs_an_open_request(
        self, async_client: AsyncClient, db_session: AsyncSession, kids: EventTeam
    ):
        _, first_aid = await _reqs(db_session, kids)
        r = await self._upload(async_client, kids, first_aid, PDF)
        assert r.status_code == 404
        assert r.json()["code"] == "team.request_not_found"

    async def test_requester_can_take_it_back(
        self, async_client: AsyncClient, db_session: AsyncSession, kids: EventTeam
    ):
        _, first_aid = await _reqs(db_session, kids)
        await async_client.post(f"{_url(kids)}/join", json={})
        await self._upload(async_client, kids, first_aid, PDF)
        url = f"{_url(kids)}/join/documents/{first_aid.id}"
        assert (await async_client.delete(url)).status_code == 204
        assert (await async_client.delete(url)).status_code == 404
        assert await _documents(db_session) == 0


@pytest.mark.asyncio
class TestDocumentAccess:
    @pytest_asyncio.fixture
    async def attached(
        self,
        db_session: AsyncSession,
        kids: EventTeam,
        test_user: User,
    ) -> str:
        _, first_aid = await _reqs(db_session, kids)
        row = await _row(db_session, kids, test_user)
        await crud_team.upsert_document(
            db_session,
            member_id=row.id,
            requirement_id=first_aid.id,
            filename="kurs.pdf",
            content_type="application/pdf",
            size=len(PDF),
            storage_key=await crud_team.store_document_file(
                db_session, data=PDF, content_type="application/pdf"
            ),
        )
        return f"{_url(kids)}/members/{test_user.id}/documents/{first_aid.id}"

    async def test_event_admin_reads_it(
        self, async_client: AsyncClient, attached: str, as_event_admin: None
    ):
        r = await async_client.get(attached)
        assert r.status_code == 200
        assert r.content == PDF

    async def test_team_lead_reads_it(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        attached: str,
        kids: EventTeam,
        test_event: Event,
        test_outsider_user: User,
        app: FastAPI,
    ):
        db_session.add(
            EventMembership(user_id=test_outsider_user.id, event_id=test_event.id)
        )
        await _row(db_session, kids, test_outsider_user, status="approved", role="lead")
        with act_as(app, test_outsider_user):
            r = await async_client.get(attached)
        assert r.status_code == 200

    async def test_requester_reads_it(self, async_client: AsyncClient, attached: str):
        assert (await async_client.get(attached)).status_code == 200

    async def test_file_gone_reads_as_not_found(
        self, async_client: AsyncClient, db_session: AsyncSession, attached: str
    ):
        """A row whose stored file is missing answers the same 404."""
        doc = (await db_session.execute(select(EventTeamDocument))).scalar_one()
        await drop_file(db_session, doc.storage_key)
        r = await async_client.get(attached)
        assert r.status_code == 404
        assert r.json()["code"] == "team.document_not_found"

    async def test_other_member_gets_404(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        attached: str,
        kids: EventTeam,
        test_event: Event,
        test_outsider_user: User,
        app: FastAPI,
    ):
        """Even an approved plain member of the same team."""
        db_session.add(
            EventMembership(user_id=test_outsider_user.id, event_id=test_event.id)
        )
        await _row(db_session, kids, test_outsider_user, status="approved")
        with act_as(app, test_outsider_user):
            r = await async_client.get(attached)
        assert r.status_code == 404
        assert r.json()["code"] == "team.document_not_found"

    async def test_outsider_gets_404(
        self, async_client: AsyncClient, attached: str, as_outsider: None
    ):
        r = await async_client.get(attached)
        assert r.status_code == 404


@pytest.mark.asyncio
class TestDocumentsAreDeleted:
    @pytest_asyncio.fixture
    async def pending(
        self,
        db_session: AsyncSession,
        kids: EventTeam,
        test_user: User,
    ) -> EventTeamMember:
        _, first_aid = await _reqs(db_session, kids)
        row = await _row(db_session, kids, test_user)
        await crud_team.upsert_document(
            db_session,
            member_id=row.id,
            requirement_id=first_aid.id,
            filename="kurs.pdf",
            content_type="application/pdf",
            size=len(PDF),
            storage_key=await crud_team.store_document_file(
                db_session, data=PDF, content_type="application/pdf"
            ),
        )
        assert await _documents(db_session) == 1
        return row

    async def test_on_approve(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        kids: EventTeam,
        pending: EventTeamMember,
        test_user: User,
        as_event_admin: None,
    ):
        police, first_aid = await _reqs(db_session, kids)
        r = await async_client.post(
            f"{_url(kids)}/members/{test_user.id}/decide",
            json={
                "approve": True,
                "checks": [
                    {"requirement_id": str(police.id), "issued_on": "2026-01-02"},
                    {"requirement_id": str(first_aid.id), "issued_on": "2026-01-02"},
                ],
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["documents"] == []
        assert await _documents(db_session) == 0

    async def test_on_decline(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        kids: EventTeam,
        pending: EventTeamMember,
        test_user: User,
        as_event_admin: None,
    ):
        r = await async_client.post(
            f"{_url(kids)}/members/{test_user.id}/decide", json={"approve": False}
        )
        assert r.status_code == 200
        assert await _documents(db_session) == 0

    async def test_on_withdraw(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        kids: EventTeam,
        pending: EventTeamMember,
    ):
        assert (await async_client.delete(f"{_url(kids)}/join")).status_code == 204
        assert await _documents(db_session) == 0

    async def test_on_removal_from_the_team(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        kids: EventTeam,
        pending: EventTeamMember,
        test_user: User,
        as_event_admin: None,
    ):
        r = await async_client.delete(f"{_url(kids)}/members/{test_user.id}")
        assert r.status_code == 204
        assert await _documents(db_session) == 0

    async def test_on_leaving_the_event(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        pending: EventTeamMember,
        test_user: User,
    ):
        r = await async_client.delete(
            f"/api/v1/events/{test_event.id}/members/{test_user.id}"
        )
        assert r.status_code == 204
        assert await _documents(db_session) == 0

    async def test_on_placing_directly(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        kids: EventTeam,
        pending: EventTeamMember,
        test_user: User,
        as_event_admin: None,
    ):
        police, first_aid = await _reqs(db_session, kids)
        r = await async_client.post(
            f"{_url(kids)}/members",
            json={
                "user_id": str(test_user.id),
                "checks": [
                    {"requirement_id": str(police.id), "issued_on": "2026-01-02"},
                    {"requirement_id": str(first_aid.id), "issued_on": "2026-01-02"},
                ],
            },
        )
        assert r.status_code == 201, r.text
        assert await _documents(db_session) == 0

    async def test_on_a_leftover_request_let_through(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        kids: EventTeam,
        pending: EventTeamMember,
    ):
        """A request still waiting when its team stopped needing approval."""
        kids.requires_approval = False
        db_session.add(kids)
        await db_session.flush()
        r = await async_client.post(f"{_url(kids)}/join", json={})
        assert r.status_code == 201, r.text
        assert r.json()["status"] == "approved"
        assert await _documents(db_session) == 0

    async def test_review_shows_document_metadata(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        kids: EventTeam,
        pending: EventTeamMember,
        as_event_admin: None,
    ):
        _, first_aid = await _reqs(db_session, kids)
        [request] = (
            await async_client.get(
                f"{_url(kids)}/members", params={"status": "pending"}
            )
        ).json()
        [doc] = request["documents"]
        assert doc["requirement_id"] == str(first_aid.id)
        assert doc["filename"] == "kurs.pdf"
        assert doc["size"] == len(PDF)


class TestFilenames:
    @pytest.mark.parametrize(
        ("given", "expected"),
        [
            ("C:\\Users\\x\\Ausweis.PDF", "Ausweis.pdf"),
            ("../../etc/passwd", "passwd.pdf"),
            (None, "document.pdf"),
            ('a"\x00b.pdf', "ab.pdf"),
        ],
    )
    def test_safe_filename(self, given: str | None, expected: str):
        assert safe_filename(given, suffix=".pdf") == expected

    def test_add_years_on_leap_day(self):
        assert add_years(date(2024, 2, 29), 1) == date(2025, 2, 28)
