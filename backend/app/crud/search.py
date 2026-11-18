"""Free-text search in SQL."""


def like_pattern(q: str) -> str:
    """``%q%`` for ``ILIKE``, with the wildcards ``%`` and ``_`` in ``q`` matched
    literally.

    Otherwise searching for "100%" matches everything that contains "100". The
    escape character is the backslash, which is also PostgreSQL's default for
    ``LIKE``, so the pattern needs no ``ESCAPE`` clause:
    ``col(Model.name).ilike(like_pattern(q))``.
    """
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
