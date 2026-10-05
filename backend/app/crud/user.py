from collections.abc import Sequence
from typing import Literal

from sqlalchemy import ColumnElement, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.crud.base import CRUDBase
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate

UserStatus = Literal["all", "active", "pending", "rejected", "suspended"]


class CRUDUser(CRUDBase[User, UserCreate, UserUpdate]):
    async def get_by_subject(self, db: AsyncSession, *, subject: str) -> User | None:
        result = await db.execute(select(User).where(col(User.subject) == subject))
        return result.scalars().first()

    async def get_by_email(self, db: AsyncSession, *, email: str) -> User | None:
        """Find an account by address, without caring how it was typed.

        Email is the login credential now, and nobody types their own address
        the same way twice — a form that rejects ``Anna@Example.com`` because
        the account was created as ``anna@example.com`` reads as "wrong
        password". The comparison is therefore on ``lower(email)``, which is
        also exactly the expression the partial unique index
        ``ix_users_email_lower`` is built on, so this stays an index lookup.

        ``scalar_one_or_none`` rather than ``first``: that index makes two
        accounts sharing an address impossible, and if it were ever dropped, an
        arbitrary row winning a *login* lookup would decide whose account a
        password opens. Failing loudly is the only acceptable behaviour there.
        Rows with a NULL email never match, which is correct — a NULL address
        is not a credential.
        """
        result = await db.execute(
            select(User).where(func.lower(col(User.email)) == email.strip().lower())
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _q_clauses(q: str | None) -> list[ColumnElement[bool]]:
        if not q:
            return []
        pattern = f"%{q.strip().lower()}%"
        return [
            or_(
                func.lower(col(User.name)).like(pattern),
                func.lower(col(User.email)).like(pattern),
            )
        ]

    @staticmethod
    def _status_clauses(status: UserStatus) -> list[ColumnElement[bool]]:
        # "pending" and "rejected" are the registration queue; "suspended" is
        # moderation. An account still in the queue is listed there rather than
        # under "suspended", whatever its ``is_active`` says.
        approved = col(User.approval_status) == "approved"
        if status == "active":
            return [col(User.is_active).is_(True), approved]
        if status == "pending":
            return [col(User.approval_status) == "pending"]
        if status == "rejected":
            return [col(User.approval_status) == "rejected"]
        if status == "suspended":
            return [col(User.is_active).is_(False), approved]
        return []

    async def search(
        self,
        db: AsyncSession,
        *,
        q: str | None = None,
        status: UserStatus = "all",
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[Sequence[User], dict[str, int]]:
        q_clauses = self._q_clauses(q)
        status_clauses = self._status_clauses(status)
        # Guest accounts are an implementation detail of the demo, not people.
        # They would otherwise crowd this list out on a busy day, and every
        # action it offers - suspend, promote, reject - means nothing for a row
        # that deletes itself within the hour.
        q_clauses = [*q_clauses, col(User.is_sandbox).is_(False)]

        items_query = (
            select(User)
            .where(*q_clauses, *status_clauses)
            .order_by(col(User.created_at).desc())
            .offset(skip)
            .limit(limit)
        )

        approved = col(User.approval_status) == "approved"
        pending_case = case((col(User.approval_status) == "pending", 1))
        rejected_case = case((col(User.approval_status) == "rejected", 1))
        active_case = case((col(User.is_active).is_(True) & approved, 1))
        suspended_case = case((col(User.is_active).is_(False) & approved, 1))

        counts_query = (
            select(
                func.count().label("all"),
                func.count(active_case).label("active"),
                func.count(pending_case).label("pending"),
                func.count(rejected_case).label("rejected"),
                func.count(suspended_case).label("suspended"),
            )
            .select_from(User)
            .where(*q_clauses)
        )

        items_result = await db.execute(items_query)
        counts_result = await db.execute(counts_query)
        counts_row = counts_result.one()

        counts = {
            "all": int(counts_row.all or 0),
            "active": int(counts_row.active or 0),
            "pending": int(counts_row.pending or 0),
            "rejected": int(counts_row.rejected or 0),
            "suspended": int(counts_row.suspended or 0),
        }
        return items_result.scalars().all(), counts


user = CRUDUser(User)
