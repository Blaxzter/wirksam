"""``crud.search.like_pattern``: what someone types is matched as text, never as
a wildcard."""

import datetime as dt

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.crud.search import like_pattern
from app.models.event import Event
from app.models.task import Task

NAMES = ["100% Spaß", "1000 Lose", "Ab_bau", "Abxbau", "C:\\Kasse", "C:Kasse"]


def test_escapes_wildcards_and_the_escape_character() -> None:
    assert like_pattern("50%_\\") == "%50\\%\\_\\\\%"
    assert like_pattern("Bar") == "%Bar%"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("q", "expected"),
    [
        ("100%", ["100% Spaß"]),
        ("b_b", ["Ab_bau"]),
        ("c:\\k", ["C:\\Kasse"]),
        ("spaß", ["100% Spaß"]),
    ],
)
async def test_matches_case_insensitively_and_literally(
    q: str, expected: list[str], db_session: AsyncSession, test_event: Event
) -> None:
    db_session.add_all(
        Task(
            name=name,
            start_date=dt.date(2026, 6, 11),
            end_date=dt.date(2026, 6, 11),
            event_id=test_event.id,
        )
        for name in NAMES
    )
    await db_session.flush()

    result = await db_session.execute(
        select(col(Task.name))
        .where(
            col(Task.event_id) == test_event.id,
            col(Task.name).ilike(like_pattern(q)),
        )
        .order_by(col(Task.name))
    )

    assert list(result.scalars().all()) == expected
