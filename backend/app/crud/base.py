import datetime
from collections.abc import AsyncGenerator, Sequence
from typing import (
    Any,
    Generic,
    Literal,
    NamedTuple,
    TypeVar,
    overload,
)
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import col
from starlette import status

from app.logic.utils.db_utils import get_comparison
from app.models import Base

ModelType = TypeVar("ModelType", bound=Base)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)


class NamedFilterFields(NamedTuple):
    field: str
    value: Any
    is_not: bool = False
    greater_then_comp: Literal["gt", "le"] | None = None


excludeList = {
    "id",
    "created_on",
    "updated_on",
}


class CRUDBase(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def __init__(self, model: type[ModelType]):
        """
        CRUD object with default methods to Create, Read, Update, Delete (CRUD).

        **Parameters**

        * `model`: A SQLAlchemy model class
        * `schema`: A Pydantic model (schema) class
        """
        self.model = model

    # These overloads allow the type checker to understand that
    # when `raise_404_error` is True, the return type is never None.

    @overload
    async def get(  # noqa: E704
        self,
        db: AsyncSession,
        id: Any,
        *,
        raise_404_error: Literal[True],
        select_in_load: list[str] | None = None,
    ) -> ModelType: ...

    @overload
    async def get(  # noqa: E704
        self,
        db: AsyncSession,
        id: Any,
        *,
        raise_404_error: Literal[False] = False,
        select_in_load: list[str] | None = None,
    ) -> ModelType | None: ...

    async def get(
        self,
        db: AsyncSession,
        id: Any,
        *,
        raise_404_error: bool = False,
        select_in_load: list[str] | None = None,
    ) -> ModelType | None:
        query = select(self.model).where(col(self.model.id) == id)
        if select_in_load:
            for attr in select_in_load:
                query = query.options(selectinload(getattr(self.model, attr)))

        result = await db.execute(query)
        first = result.scalars().first()
        if not first and raise_404_error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{self.model.__name__} not found",
            )
        return first

    # write a function that iterates over all elements in self.model and return n elements as yield

    async def get_multi(
        self,
        db: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 100,
        ids: list[str] | None = None,
        select_in_load: list[str] | None = None,
    ) -> Sequence[ModelType]:
        query = select(self.model).offset(skip).limit(limit)
        if ids:
            query = query.where(col(self.model.id).in_(ids))

        if select_in_load:
            for attr in select_in_load:
                query = query.options(selectinload(getattr(self.model, attr)))

        result = await db.execute(query)
        return result.scalars().all()

    async def remove_multi(self, db: AsyncSession, *, ids: list[int]) -> bool:
        await db.execute(delete(self.model).where(col(self.model.id).in_(ids)))
        return True

    async def create(self, db: AsyncSession, *, obj_in: CreateSchemaType) -> ModelType:
        # get all fields from obj_in that have type datetime, date, or time
        datetime_fields = [
            (property, value)
            for property, value in vars(obj_in).items()
            if type(value) in (datetime.datetime, datetime.date, datetime.time)
        ]

        obj_in_data = jsonable_encoder(obj_in)
        for property, value in datetime_fields:
            obj_in_data[property] = value

        db_obj = self.model(**obj_in_data)  # type: ignore[call-arg]
        db.add(db_obj)
        await db.flush()
        await db.refresh(db_obj)
        return db_obj

    async def update(
        self,
        db: AsyncSession,
        *,
        db_obj: ModelType,
        obj_in: UpdateSchemaType | dict[str, Any],
        skip_refresh: bool = False,
    ) -> ModelType:
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.model_dump(exclude_unset=True)

        db_obj.sqlmodel_update(update_data)

        db.add(db_obj)
        await db.flush()
        if not skip_refresh:
            await db.refresh(db_obj)
        else:
            # manually set the updated_on field
            db_obj.updated_on = datetime.datetime.now(ZoneInfo("UTC"))

        return db_obj

    async def remove(self, db: AsyncSession, *, id: Any) -> ModelType | None:
        obj = await db.get(self.model, id)
        if not obj:
            return None

        await db.delete(obj)
        return obj

    async def iterate(
        self,
        db: AsyncSession,
        *,
        n: int = 100,
        continues: bool = True,
        filter_by: list[NamedFilterFields] | None = None,
    ) -> AsyncGenerator[ModelType, None]:
        """
        Yields `n` elements at a time from the table associated with `self.model`.

        **Parameters**

        * `session`: The SQLAlchemy session object
        * `n`: The number of elements to yield at a time
        continue: If False, the function will continue to yield elements until there are no more elements in the table
        """
        offset = 0
        while True:
            query = select(self.model).offset(offset).limit(n)

            if filter_by:
                for attr, value, is_not, greater_then_comp in filter_by:
                    comparison = get_comparison(
                        getattr(self.model, attr),
                        value,
                        is_not=is_not,
                        greater_then_comp=greater_then_comp,
                    )
                    query = query.where(comparison)

            result = await db.execute(query)
            items = result.scalars().all()

            if not items:
                break
            for item in items:
                yield item
            if continues:
                offset += n

    async def get_count(
        self,
        db: AsyncSession,
        filter_by: list[NamedFilterFields] | None = None,
    ) -> int:
        """
        Returns the total number of elements in the table associated with `self.model`.

        **Parameters**

        * `session`: The SQLAlchemy session object
        """
        query = select(func.count()).select_from(self.model)
        if filter_by:
            for attr, value, is_not, greater_then_comp in filter_by:
                comparison = get_comparison(
                    getattr(self.model, attr),
                    value,
                    is_not=is_not,
                    greater_then_comp=greater_then_comp,
                )
                query = query.where(comparison)

        result = await db.execute(query)
        return result.scalar() or 0
