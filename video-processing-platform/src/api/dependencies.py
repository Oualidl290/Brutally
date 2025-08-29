"""
FastAPI dependencies for database access and common functionality.
"""

from fastapi import Depends, HTTPException, status, Request
from typing import AsyncGenerator, Dict, Any

from ..database.service import get_database_service, DatabaseService
from ..database.models import User, UserRole
from .middleware.auth import get_current_user
from ..config.logging_config import get_logger

logger = get_logger(__name__)


async def get_db() -> AsyncGenerator[DatabaseService, None]:
    """
    Dependency to get database service.
    
    This provides a database service instance with automatic
    session management and cleanup.
    """
    async with get_database_service() as db:
        try:
            yield db
        except Exception as e:
            logger.error(f"Database service error: {e}", exc_info=True)
            await db.rollback()
            raise


async def get_current_db_user(
    request: Request,
    db: DatabaseService = Depends(get_db)
) -> User:
    """
    Dependency to get current authenticated user from database.
    
    This fetches the full user object from the database based on
    the JWT token information.
    """
    try:
        # Get user info from JWT token
        user_info = get_current_user(request)
        user_id = user_info["user_id"]
        
        # Fetch full user from database
        user = await db.users.get(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )
        
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is inactive"
            )
        
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get current user error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User authentication service error"
        )


def require_admin(user: User = Depends(get_current_db_user)) -> User:
    """
    Dependency to require admin role.
    """
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return user


def require_active_user(user: User = Depends(get_current_db_user)) -> User:
    """
    Dependency to require active user account.
    """
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is inactive"
        )
    return user


async def log_api_action(
    request: Request,
    user: User,
    action: str,
    resource_type: str = None,
    resource_id: str = None,
    success: bool = True,
    additional_data: Dict[str, Any] = None,
    db: DatabaseService = Depends(get_db)
):
    """
    Helper function to log API actions to audit trail.
    """
    try:
        from ..database.models import AuditAction
        
        # Map action strings to AuditAction enum
        action_mapping = {
            "login": AuditAction.USER_LOGIN,
            "logout": AuditAction.USER_LOGOUT,
            "job_created": AuditAction.JOB_CREATED,
            "job_started": AuditAction.JOB_STARTED,
            "job_completed": AuditAction.JOB_COMPLETED,
            "job_failed": AuditAction.JOB_FAILED,
            "job_cancelled": AuditAction.JOB_CANCELLED,
            "file_uploaded": AuditAction.FILE_UPLOADED,
            "file_downloaded": AuditAction.FILE_DOWNLOADED,
            "file_deleted": AuditAction.FILE_DELETED,
        }
        
        audit_action = action_mapping.get(action)
        if not audit_action:
            logger.warning(f"Unknown audit action: {action}")
            return
        
        # Get client IP
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        
        # Log the action
        await db.audit.log_action(
            action=audit_action,
            description=f"User {user.username} performed {action}",
            user_id=user.id,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=client_ip,
            user_agent=user_agent,
            details=additional_data or {},
            success=success
        )
        
        await db.commit()
        
    except Exception as e:
        logger.error(f"Failed to log audit action: {e}", exc_info=True)
        # Don't fail the main operation if audit logging fails


class PaginationParams:
    """
    Pagination parameters dependency.
    """
    
    def __init__(
        self,
        page: int = 1,
        limit: int = 20,
        sort_by: str = None,
        sort_order: str = "asc"
    ):
        self.page = max(1, page)
        self.limit = min(max(1, limit), 100)  # Limit between 1 and 100
        self.sort_by = sort_by
        self.sort_order = sort_order if sort_order in ["asc", "desc"] else "asc"
        
        # Calculate offset
        self.offset = (self.page - 1) * self.limit
    
    @property
    def skip(self) -> int:
        """Get skip value for database queries."""
        return self.offset


def get_pagination_params(
    page: int = 1,
    limit: int = 20,
    sort_by: str = None,
    sort_order: str = "asc"
) -> PaginationParams:
    """
    Dependency to get pagination parameters.
    """
    return PaginationParams(page, limit, sort_by, sort_order)


async def check_user_job_access(
    job_id: str,
    user: User,
    db: DatabaseService
) -> bool:
    """
    Check if user has access to a specific job.
    
    Users can access their own jobs, admins can access all jobs.
    """
    try:
        job = await db.jobs.get(job_id)
        if not job:
            return False
        
        # Admin can access all jobs
        if user.role == UserRole.ADMIN:
            return True
        
        # User can access their own jobs
        return job.user_id == user.id
        
    except Exception as e:
        logger.error(f"Error checking job access: {e}", exc_info=True)
        return False


async def get_user_job(
    job_id: str,
    user: User = Depends(get_current_db_user),
    db: DatabaseService = Depends(get_db)
):
    """
    Dependency to get a job that the user has access to.
    """
    try:
        job = await db.jobs.get(job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found"
            )
        
        # Check access
        if not await check_user_job_access(job_id, user, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this job"
            )
        
        return job
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user job: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Job access service error"
        )


class RateLimitInfo:
    """
    Rate limit information from middleware.
    """
    
    def __init__(self, request: Request):
        self.limit = request.headers.get("x-ratelimit-limit")
        self.remaining = request.headers.get("x-ratelimit-remaining")
        self.reset = request.headers.get("x-ratelimit-reset")
        self.window = request.headers.get("x-ratelimit-window")


def get_rate_limit_info(request: Request) -> RateLimitInfo:
    """
    Dependency to get rate limit information.
    """
    return RateLimitInfo(request)


async def validate_file_access(
    file_id: str,
    user: User,
    db: DatabaseService
) -> bool:
    """
    Validate if user has access to a specific file.
    """
    try:
        storage_file = await db.storage.get(file_id)
        if not storage_file:
            return False
        
        # Admin can access all files
        if user.role == UserRole.ADMIN:
            return True
        
        # Check if file belongs to user's job
        if storage_file.job_id:
            return await check_user_job_access(storage_file.job_id, user, db)
        
        # For files without job association, check other ownership rules
        # This would depend on your specific business logic
        return False
        
    except Exception as e:
        logger.error(f"Error validating file access: {e}", exc_info=True)
        return False


async def get_user_file(
    file_id: str,
    user: User = Depends(get_current_db_user),
    db: DatabaseService = Depends(get_db)
):
    """
    Dependency to get a file that the user has access to.
    """
    try:
        storage_file = await db.storage.get(file_id)
        if not storage_file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found"
            )
        
        # Check access
        if not await validate_file_access(file_id, user, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this file"
            )
        
        return storage_file
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user file: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="File access service error"
        )