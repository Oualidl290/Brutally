"""
Database connection management with async SQLAlchemy.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool, QueuePool

from ..config import settings
from ..config.logging_config import get_logger

logger = get_logger(__name__)


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


class DatabaseManager:
    """Database connection manager."""
    
    def __init__(self):
        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[async_sessionmaker[AsyncSession]] = None
    
    def create_engine(self) -> AsyncEngine:
        """Create database engine with configuration."""
        if self._engine is not None:
            return self._engine
        
        # Configure connection pool based on environment
        if settings.is_testing:
            # Use NullPool for testing to avoid connection issues
            poolclass = NullPool
            pool_size = 0
            max_overflow = 0
        else:
            poolclass = QueuePool
            pool_size = settings.DATABASE_POOL_SIZE
            max_overflow = settings.DATABASE_MAX_OVERFLOW
        
        self._engine = create_async_engine(
            settings.DATABASE_URL,
            echo=settings.is_development,
            poolclass=poolclass,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=True,
            pool_recycle=3600,  # Recycle connections after 1 hour
        )
        
        logger.info(
            "Database engine created",
            extra={
                "database_url": settings.DATABASE_URL.split("@")[-1],  # Hide credentials
                "pool_size": pool_size,
                "max_overflow": max_overflow,
                "echo": settings.is_development,
            }
        )
        
        return self._engine
    
    def create_session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Create session factory."""
        if self._session_factory is not None:
            return self._session_factory
        
        engine = self.create_engine()
        self._session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=True,
            autocommit=False,
        )
        
        return self._session_factory
    
    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get database session context manager."""
        session_factory = self.create_session_factory()
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
    
    async def close(self):
        """Close database connections."""
        if self._engine:
            await self._engine.dispose()
            logger.info("Database connections closed")
    
    async def create_tables(self):
        """Create all database tables."""
        engine = self.create_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created")
    
    async def drop_tables(self):
        """Drop all database tables."""
        engine = self.create_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        logger.info("Database tables dropped")


# Global database manager instance
db_manager = DatabaseManager()


# Convenience functions
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session."""
    async with db_manager.get_session() as session:
        yield session


async def init_database():
    """Initialize database connection and create tables."""
    try:
        await db_manager.create_tables()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}", exc_info=True)
        raise


async def close_database():
    """Close database connections."""
    await db_manager.close()