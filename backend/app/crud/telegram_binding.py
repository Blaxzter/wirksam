import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.crud.base import CRUDBase
from app.models.notification import TelegramBinding


class _Empty:
    pass


class CRUDTelegramBinding(CRUDBase[TelegramBinding, _Empty, _Empty]):  # type: ignore[type-var]
    async def get_by_user(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
    ) -> TelegramBinding | None:
        query = select(TelegramBinding).where(col(TelegramBinding.user_id) == user_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_chat_id(
        self,
        db: AsyncSession,
        *,
        chat_id: str,
    ) -> TelegramBinding | None:
        query = select(TelegramBinding).where(
            col(TelegramBinding.telegram_chat_id) == chat_id
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_verification_code(
        self,
        db: AsyncSession,
        *,
        code: str,
    ) -> TelegramBinding | None:
        query = select(TelegramBinding).where(
            col(TelegramBinding.verification_code) == code,
            col(TelegramBinding.is_verified) == False,  # noqa: E712
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def create_binding(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        verification_code: str,
        expires_at: datetime,
    ) -> TelegramBinding:

        # Remove any existing unverified binding for this user
        existing = await self.get_by_user(db, user_id=user_id)
        if existing and not existing.is_verified:
            await db.delete(existing)
            await db.flush()
        elif existing and existing.is_verified:
            # Already verified, update the code for re-binding
            existing.verification_code = verification_code
            existing.is_verified = False
            existing.telegram_chat_id = None
            existing.telegram_username = None
            existing.verification_expires_at = expires_at
            db.add(existing)
            await db.flush()
            await db.refresh(existing)
            return existing

        binding = TelegramBinding(
            user_id=user_id,
            verification_code=verification_code,
            verification_expires_at=expires_at,
        )
        db.add(binding)
        await db.flush()
        await db.refresh(binding)
        return binding

    async def verify_binding(
        self,
        db: AsyncSession,
        *,
        binding: TelegramBinding,
        chat_id: str,
        username: str | None = None,
    ) -> TelegramBinding:
        binding.telegram_chat_id = chat_id
        binding.telegram_username = username
        binding.is_verified = True
        binding.verification_code = None
        binding.verification_expires_at = None
        db.add(binding)
        await db.flush()
        await db.refresh(binding)
        return binding

    async def remove_binding(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
    ) -> bool:
        existing = await self.get_by_user(db, user_id=user_id)
        if existing:
            await db.delete(existing)
            await db.flush()
            return True
        return False


telegram_binding = CRUDTelegramBinding(TelegramBinding)
