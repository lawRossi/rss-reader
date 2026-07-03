"""Database configuration and session management."""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False, poolclass=NullPool)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    """Dependency that provides a database session."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    """Create all database tables."""
    from app.models import (  # noqa: F401 - import to register models
        Setting, Group, Feed, Article, Tag, ArticleTag, DailyBriefing, ScheduledTask
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # ── Migrate: add new columns to existing tables ──
    async with async_session() as session:
        # DailyBriefing.ref_audio_id
        try:
            from sqlalchemy import text
            await session.execute(
                text("ALTER TABLE daily_briefings ADD COLUMN ref_audio_id VARCHAR(50)")
            )
            await session.commit()
        except Exception:
            await session.rollback()  # Column already exists

        # ScheduledTask.ref_audio_id
        try:
            from sqlalchemy import text
            await session.execute(
                text("ALTER TABLE scheduled_tasks ADD COLUMN ref_audio_id VARCHAR(50)")
            )
            await session.commit()
        except Exception:
            await session.rollback()  # Column already exists


async def seed_default_settings():
    """Insert default LLM, TTS and fetch settings if not present."""
    from app.models import Setting
    from app.config import DEFAULT_LLM_SETTINGS, DEFAULT_TTS_SETTINGS, DEFAULT_FETCH_SETTINGS

    async with async_session() as session:
        all_defaults = {**DEFAULT_LLM_SETTINGS, **DEFAULT_TTS_SETTINGS, **DEFAULT_FETCH_SETTINGS}
        for key, value in all_defaults.items():
            existing = await session.get(Setting, key)
            if existing is None:
                session.add(Setting(key=key, value=value))
        await session.commit()
