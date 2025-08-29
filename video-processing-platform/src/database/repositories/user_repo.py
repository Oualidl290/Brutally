"""
User repository with user-specific query methods.
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Union
from uuid import UUID

from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from .base_repo import BaseRepository
from ..models.user import User, UserRole
from ...config.logging_config import get_logger
from ...utils.exceptions import ValidationError, AuthenticationError

logger = get_logger(__name__)


class UserRepository(BaseRepository[User]):
    """Repository for user-specific operations."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(User, session)
    
    async def create_user(
        self,
        username: str,
        email: str,
        password: str,
        full_name: Optional[str] = None,
        role: UserRole = UserRole.USER
    ) -> User:
        """Create a new user with hashed password."""
        # Check if username or email already exists
        existing_user = await self.get_by_username_or_email(username, email)
        if existing_user:
            if existing_user.username == username:
                raise ValidationError("Username already exists")
            else:
                raise ValidationError("Email already exists")
        
        user_data = {
            "username": username,
            "email": email,
            "full_name": full_name,
            "role": role,
            "hashed_password": User.hash_password(password)
        }
        
        user = await self.create(**user_data)
        
        logger.info(
            "User created",
            extra={
                "user_id": user.id,
                "username": username,
                "email": email,
                "role": role.value
            }
        )
        
        return user
    
    async def get_by_username(self, username: str) -> Optional[User]:
        """Get user by username."""
        stmt = select(User).where(User.username == username)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        stmt = select(User).where(User.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_by_username_or_email(self, username: str, email: str) -> Optional[User]:
        """Get user by username or email."""
        stmt = select(User).where(
            or_(User.username == username, User.email == email)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_by_api_key(self, api_key: str) -> Optional[User]:
        """Get user by API key."""
        stmt = select(User).where(
            and_(User.api_key == api_key, User.is_active == True)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def authenticate(self, username: str, password: str) -> Optional[User]:
        """Authenticate user with username/email and password."""
        # Try to find user by username or email
        user = await self.get_by_username(username)
        if not user:
            user = await self.get_by_email(username)
        
        if not user:
            logger.warning(
                "Authentication failed - user not found",
                extra={"username": username}
            )
            return None
        
        if not user.is_active:
            logger.warning(
                "Authentication failed - user inactive",
                extra={"user_id": user.id, "username": username}
            )
            return None
        
        if not user.verify_password(password):
            logger.warning(
                "Authentication failed - invalid password",
                extra={"user_id": user.id, "username": username}
            )
            return None
        
        # Update last login
        await self.update_last_login(user.id)
        
        logger.info(
            "User authenticated successfully",
            extra={"user_id": user.id, "username": username}
        )
        
        return user
    
    async def update_password(self, user_id: Union[str, UUID], new_password: str) -> Optional[User]:
        """Update user password."""
        hashed_password = User.hash_password(new_password)
        user = await self.update(user_id, hashed_password=hashed_password)
        
        if user:
            logger.info(
                "User password updated",
                extra={"user_id": str(user_id)}
            )
        
        return user
    
    async def update_last_login(self, user_id: Union[str, UUID]) -> Optional[User]:
        """Update user's last login timestamp."""
        return await self.update(user_id, last_login=datetime.utcnow())
    
    async def activate_user(self, user_id: Union[str, UUID]) -> Optional[User]:
        """Activate user account."""
        user = await self.update(user_id, is_active=True)
        
        if user:
            logger.info(
                "User activated",
                extra={"user_id": str(user_id)}
            )
        
        return user
    
    async def deactivate_user(self, user_id: Union[str, UUID]) -> Optional[User]:
        """Deactivate user account."""
        user = await self.update(user_id, is_active=False)
        
        if user:
            logger.info(
                "User deactivated",
                extra={"user_id": str(user_id)}
            )
        
        return user
    
    async def verify_user(self, user_id: Union[str, UUID]) -> Optional[User]:
        """Mark user as verified."""
        user = await self.update(user_id, is_verified=True)
        
        if user:
            logger.info(
                "User verified",
                extra={"user_id": str(user_id)}
            )
        
        return user
    
    async def generate_api_key(self, user_id: Union[str, UUID]) -> Optional[str]:
        """Generate new API key for user."""
        import secrets
        api_key = secrets.token_urlsafe(32)
        
        user = await self.update(user_id, api_key=api_key)
        
        if user:
            logger.info(
                "API key generated",
                extra={"user_id": str(user_id)}
            )
            return api_key
        
        return None
    
    async def revoke_api_key(self, user_id: Union[str, UUID]) -> Optional[User]:
        """Revoke user's API key."""
        user = await self.update(user_id, api_key=None)
        
        if user:
            logger.info(
                "API key revoked",
                extra={"user_id": str(user_id)}
            )
        
        return user
    
    async def update_role(self, user_id: Union[str, UUID], role: UserRole) -> Optional[User]:
        """Update user role."""
        user = await self.update(user_id, role=role)
        
        if user:
            logger.info(
                "User role updated",
                extra={"user_id": str(user_id), "role": role.value}
            )
        
        return user
    
    async def increment_job_count(self, user_id: Union[str, UUID]) -> Optional[User]:
        """Increment user's job count."""
        user = await self.get(user_id)
        if user:
            return await self.update(user_id, job_count=user.job_count + 1)
        return None
    
    async def add_processing_time(self, user_id: Union[str, UUID], seconds: int) -> Optional[User]:
        """Add processing time to user's total."""
        user = await self.get(user_id)
        if user:
            return await self.update(
                user_id, 
                total_processing_time=user.total_processing_time + seconds
            )
        return None
    
    async def get_active_users(self, skip: int = 0, limit: int = 100) -> List[User]:
        """Get active users."""
        stmt = (
            select(User)
            .where(User.is_active == True)
            .order_by(desc(User.created_at))
            .offset(skip)
            .limit(limit)
        )
        
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def get_users_by_role(self, role: UserRole, skip: int = 0, limit: int = 100) -> List[User]:
        """Get users by role."""
        stmt = (
            select(User)
            .where(User.role == role)
            .order_by(desc(User.created_at))
            .offset(skip)
            .limit(limit)
        )
        
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def search_users(self, query: str, skip: int = 0, limit: int = 100) -> List[User]:
        """Search users by username, email, or full name."""
        search_pattern = f"%{query}%"
        
        stmt = (
            select(User)
            .where(
                or_(
                    User.username.ilike(search_pattern),
                    User.email.ilike(search_pattern),
                    User.full_name.ilike(search_pattern)
                )
            )
            .order_by(desc(User.created_at))
            .offset(skip)
            .limit(limit)
        )
        
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def get_user_stats(self) -> Dict[str, Any]:
        """Get user statistics."""
        # Total users
        total_stmt = select(func.count()).select_from(User)
        total_result = await self.session.execute(total_stmt)
        total_users = total_result.scalar()
        
        # Active users
        active_stmt = select(func.count()).select_from(
            select(User).where(User.is_active == True).subquery()
        )
        active_result = await self.session.execute(active_stmt)
        active_users = active_result.scalar()
        
        # Users by role
        role_stmt = (
            select(User.role, func.count())
            .group_by(User.role)
        )
        role_result = await self.session.execute(role_stmt)
        role_counts = {role.value: count for role, count in role_result.all()}
        
        # Recent registrations (last 30 days)
        recent_date = datetime.utcnow() - timedelta(days=30)
        recent_stmt = select(func.count()).select_from(
            select(User).where(User.created_at >= recent_date).subquery()
        )
        recent_result = await self.session.execute(recent_stmt)
        recent_registrations = recent_result.scalar()
        
        return {
            "total_users": total_users,
            "active_users": active_users,
            "role_counts": role_counts,
            "recent_registrations": recent_registrations,
        }
    
    async def cleanup_inactive_users(self, days: int = 365) -> int:
        """Clean up inactive users who haven't logged in for specified days."""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Find users who haven't logged in for the specified period
        # and are not admins
        stmt = select(User).where(
            and_(
                or_(
                    User.last_login < cutoff_date,
                    User.last_login.is_(None)
                ),
                User.role != UserRole.ADMIN,
                User.created_at < cutoff_date  # Don't delete recently created accounts
            )
        )
        
        result = await self.session.execute(stmt)
        inactive_users = result.scalars().all()
        
        deleted_count = 0
        for user in inactive_users:
            if await self.delete(user.id):
                deleted_count += 1
        
        logger.info(
            f"Cleaned up {deleted_count} inactive users",
            extra={"deleted_count": deleted_count, "cutoff_days": days}
        )
        
        return deleted_count