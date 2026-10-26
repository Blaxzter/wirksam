"""Pure rules about team requirements, shared by the CRUD and logic layers.

Kept free of database and CRUD imports so ``app.crud.event_team`` can use
them when a requirement is edited (``app.logic.teams`` imports the CRUD, so
the CRUD cannot import it back).
"""

import datetime as dt


def add_years(day: dt.date, years: int) -> dt.date:
    """``day`` plus whole years; 29 February falls back to the 28th."""
    try:
        return day.replace(year=day.year + years)
    except ValueError:
        return day.replace(year=day.year + years, day=28)


def label_key(label: str) -> str:
    """Requirements in two teams count as the same when their labels match."""
    return " ".join(label.split()).casefold()
