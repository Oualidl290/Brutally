"""
Base repository class with common CRUD operations.
"""

from abc import ABC
from typing import TypeVar, Generic, List, Optional, Dict, Any, Type, Union
from uuid import UUID

from sqlalchemy import select, update, delete, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import Select

from ..connection import Base
from ...config.logging_config import get_logger
from ...utils.exceptions import ValidationError

logger = get_logger(__name__)

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType], ABC):
    """Base repository with common CRUD operations."""
    
    def __init__(self, model: Type[ModelType], session: AsyncSession):
        self.model = model
        self.session = session
    
    async def create(self, **kwargs) -> ModelType:
        """Create a new record."""
        try:
            instance = self.model(**kwargs)
            self.session.add(instance)
            await self.session.flush()
            await self.session.refresh(instance)
            
            logger.debug(
                f"Created {self.model.__name__}",
                extra={"model": self.model.__name__, "id": getattr(instance, 'id', None)}
            )
            
            return instance
        except Exception as e:
            logger.error(
                f"Failed to create {self.model.__name__}",
                extra={"error": str(e), "kwargs": kwargs},
                exc_info=True
            )
            raise ValidationError(f"Failed to create {self.model.__name__}: {e}")
    
    async def get(self, id: Union[str, UUID]) -> Optional[ModelType]:
        """Get record by ID."""
        try:
            stmt = select(self.model).where(self.model.id == str(id))
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(
                f"Failed to get {self.model.__name__}",
                extra={"error": str(e), "id": str(id)},
                exc_info=True
            )
            raise
    
    async def get_multi(
        self,
        skip: int = 0,
        limit: int = 100,
        order_by: Optional[str] = None,
        **filters
    ) -> List[ModelType]:
        """Get multiple records with pagination and filtering."""
        try:
            stmt = select(self.model)
            
            # Apply filters
            if filters:
                conditions = []
                for key, value in filters.items():
                    if hasattr(self.model, key):
                        if isinstance(value, list):
                            conditions.append(getattr(self.model, key).in_(value))
                        else:
                            conditions.append(getattr(self.model, key) == value)
                
                if conditions:
                    stmt = stmt.where(and_(*conditions))
            
            # Apply ordering
            if order_by:
                if order_by.startswith('-'):
                    # Descending order
                    field = order_by[1:]
                    if hasattr(self.model, field):
                        stmt = stmt.order_by(getattr(self.model, field).desc())
                else:
                    # Ascending order
                    if hasattr(self.model, order_by):
                        stmt = stmt.order_by(getattr(self.model, order_by))
            
            # Apply pagination
            stmt = stmt.offset(skip).limit(limit)
            
            result = await self.session.execute(stmt)
            return result.scalars().all()
        except Exception as e:
            logger.error(
                f"Failed to get multiple {self.model.__name__}",
                extra={"error": str(e), "filters": filters},
                exc_info=True
            )
            raise
    
    async def update(self, id: Union[str, UUID], **kwargs) -> Optional[ModelType]:
        """Update record by ID."""
        try:
            # Remove None values
            update_data = {k: v for k, v in kwargs.items() if v is not None}
            
            if not update_data:
                return await self.get(id)
            
            stmt = (
                update(self.model)
                .where(self.model.id == str(id))
                .values(**update_data)
                .returning(self.model)
            )
            
            result = await self.session.execute(stmt)
            updated_instance = result.scalar_one_or_none()
            
            if updated_instance:
                await self.session.refresh(updated_instance)
                logger.debug(
                    f"Updated {self.model.__name__}",
                    extra={"model": self.model.__name__, "id": str(id), "updates": update_data}
                )
            
            return updated_instance
        except Exception as e:
            logger.error(
                f"Failed to update {self.model.__name__}",
                extra={"error": str(e), "id": str(id), "kwargs": kwargs},
                exc_info=True
            )
            raise
    
    async def delete(self, id: Union[str, UUID]) -> bool:
        """Delete record by ID."""
        try:
            stmt = delete(self.model).where(self.model.id == str(id))
            result = await self.session.execute(stmt)
            
            deleted = result.rowcount > 0
            if deleted:
                logger.debug(
                    f"Deleted {self.model.__name__}",
                    extra={"model": self.model.__name__, "id": str(id)}
                )
            
            return deleted
        except Exception as e:
            logger.error(
                f"Failed to delete {self.model.__name__}",
                extra={"error": str(e), "id": str(id)},
                exc_info=True
            )
            raise
    
    async def exists(self, id: Union[str, UUID]) -> bool:
        """Check if record exists by ID."""
        try:
            stmt = select(func.count()).select_from(
                select(self.model.id).where(self.model.id == str(id)).subquery()
            )
            result = await self.session.execute(stmt)
            return result.scalar() > 0
        except Exception as e:
            logger.error(
                f"Failed to check existence of {self.model.__name__}",
                extra={"error": str(e), "id": str(id)},
                exc_info=True
            )
            raise
    
    async def count(self, **filters) -> int:
        """Count records with optional filtering."""
        try:
            stmt = select(func.count()).select_from(self.model)
            
            # Apply filters
            if filters:
                conditions = []
                for key, value in filters.items():
                    if hasattr(self.model, key):
                        if isinstance(value, list):
                            conditions.append(getattr(self.model, key).in_(value))
                        else:
                            conditions.append(getattr(self.model, key) == value)
                
                if conditions:
                    stmt = stmt.where(and_(*conditions))
            
            result = await self.session.execute(stmt)
            return result.scalar()
        except Exception as e:
            logger.error(
                f"Failed to count {self.model.__name__}",
                extra={"error": str(e), "filters": filters},
                exc_info=True
            )
            raise
    
    async def bulk_create(self, objects: List[Dict[str, Any]]) -> List[ModelType]:
        """Create multiple records in bulk."""
        try:
            instances = [self.model(**obj) for obj in objects]
            self.session.add_all(instances)
            await self.session.flush()
            
            # Refresh all instances to get generated IDs
            for instance in instances:
                await self.session.refresh(instance)
            
            logger.debug(
                f"Bulk created {len(instances)} {self.model.__name__} records",
                extra={"model": self.model.__name__, "count": len(instances)}
            )
            
            return instances
        except Exception as e:
            logger.error(
                f"Failed to bulk create {self.model.__name__}",
                extra={"error": str(e), "count": len(objects)},
                exc_info=True
            )
            raise
    
    async def bulk_update(self, updates: List[Dict[str, Any]]) -> int:
        """Update multiple records in bulk."""
        try:
            if not updates:
                return 0
            
            # Group updates by ID
            update_count = 0
            for update_data in updates:
                if 'id' not in update_data:
                    continue
                
                record_id = update_data.pop('id')
                if update_data:  # Only update if there's data
                    stmt = (
                        update(self.model)
                        .where(self.model.id == str(record_id))
                        .values(**update_data)
                    )
                    result = await self.session.execute(stmt)
                    update_count += result.rowcount
            
            logger.debug(
                f"Bulk updated {update_count} {self.model.__name__} records",
                extra={"model": self.model.__name__, "count": update_count}
            )
            
            return update_count
        except Exception as e:
            logger.error(
                f"Failed to bulk update {self.model.__name__}",
                extra={"error": str(e), "count": len(updates)},
                exc_info=True
            )
            raise
    
    def _build_query(self) -> Select:
        """Build base query for the model."""
        return select(self.model)