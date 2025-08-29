"""
Audit logging system for security and compliance.
"""

import json
from typing import Dict, Any, Optional
from datetime import datetime
from enum import Enum

from ..config.logging_config import get_logger
from ..database.connection import get_async_session
from ..database.repositories.audit_repo import AuditRepository
from ..database.models.audit import AuditEvent, AuditEventType
from .correlation import get_correlation_id, get_request_context

logger = get_logger(__name__)


class AuditAction(str, Enum):
    """Audit action types."""
    # Authentication actions
    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    PASSWORD_CHANGE = "password_change"
    TOKEN_REFRESH = "token_refresh"
    
    # Job actions
    JOB_CREATE = "job_create"
    JOB_START = "job_start"
    JOB_COMPLETE = "job_complete"
    JOB_FAIL = "job_fail"
    JOB_CANCEL = "job_cancel"
    JOB_DELETE = "job_delete"
    
    # File actions
    FILE_UPLOAD = "file_upload"
    FILE_DOWNLOAD = "file_download"
    FILE_DELETE = "file_delete"
    FILE_ACCESS = "file_access"
    
    # System actions
    CONFIG_CHANGE = "config_change"
    SYSTEM_START = "system_start"
    SYSTEM_STOP = "system_stop"
    MAINTENANCE_START = "maintenance_start"
    MAINTENANCE_END = "maintenance_end"
    
    # Security actions
    ACCESS_DENIED = "access_denied"
    PERMISSION_CHANGE = "permission_change"
    SECURITY_VIOLATION = "security_violation"
    
    # Data actions
    DATA_EXPORT = "data_export"
    DATA_IMPORT = "data_import"
    DATA_PURGE = "data_purge"


class AuditLogger:
    """Audit logging system for tracking security and compliance events."""
    
    def __init__(self):
        self.logger = get_logger(f"{__name__}.audit")
    
    async def log_event(
        self,
        action: AuditAction,
        user_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ):
        """Log an audit event."""
        
        # Get context information
        correlation_id = get_correlation_id()
        request_context = get_request_context()
        
        # Merge context details
        event_details = details or {}
        event_details.update({
            "correlation_id": correlation_id,
            "timestamp": datetime.utcnow().isoformat(),
            "success": success,
        })
        
        if error_message:
            event_details["error_message"] = error_message
        
        # Add request context
        if request_context:
            event_details["request_context"] = request_context
        
        # Determine event type
        event_type = self._determine_event_type(action)
        
        try:
            # Store in database
            async with get_async_session() as session:
                audit_repo = AuditRepository(session)
                
                audit_event = AuditEvent(
                    event_type=event_type,
                    action=action.value,
                    user_id=user_id,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    details=event_details,
                    correlation_id=correlation_id,
                    success=success,
                    error_message=error_message
                )
                
                await audit_repo.create(audit_event)
            
            # Also log to structured logger
            self.logger.info(
                f"Audit event: {action.value}",
                extra={
                    "audit_action": action.value,
                    "audit_event_type": event_type.value,
                    "user_id": user_id,
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "ip_address": ip_address,
                    "success": success,
                    "correlation_id": correlation_id,
                    "details": event_details
                }
            )
            
        except Exception as exc:
            # If audit logging fails, log the error but don't raise
            self.logger.error(
                f"Failed to log audit event: {action.value}",
                extra={
                    "error": str(exc),
                    "action": action.value,
                    "user_id": user_id,
                    "correlation_id": correlation_id
                },
                exc_info=True
            )
    
    def _determine_event_type(self, action: AuditAction) -> AuditEventType:
        """Determine event type based on action."""
        auth_actions = {
            AuditAction.LOGIN, AuditAction.LOGOUT, AuditAction.LOGIN_FAILED,
            AuditAction.PASSWORD_CHANGE, AuditAction.TOKEN_REFRESH
        }
        
        security_actions = {
            AuditAction.ACCESS_DENIED, AuditAction.PERMISSION_CHANGE,
            AuditAction.SECURITY_VIOLATION
        }
        
        system_actions = {
            AuditAction.CONFIG_CHANGE, AuditAction.SYSTEM_START,
            AuditAction.SYSTEM_STOP, AuditAction.MAINTENANCE_START,
            AuditAction.MAINTENANCE_END
        }
        
        data_actions = {
            AuditAction.DATA_EXPORT, AuditAction.DATA_IMPORT,
            AuditAction.DATA_PURGE, AuditAction.FILE_DELETE
        }
        
        if action in auth_actions:
            return AuditEventType.AUTHENTICATION
        elif action in security_actions:
            return AuditEventType.SECURITY
        elif action in system_actions:
            return AuditEventType.SYSTEM
        elif action in data_actions:
            return AuditEventType.DATA
        else:
            return AuditEventType.USER_ACTION
    
    # Convenience methods for common audit events
    
    async def log_authentication(
        self,
        action: AuditAction,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Log authentication event."""
        await self.log_event(
            action=action,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            success=success,
            error_message=error_message,
            details=details
        )
    
    async def log_job_event(
        self,
        action: AuditAction,
        job_id: str,
        user_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ):
        """Log job-related event."""
        await self.log_event(
            action=action,
            user_id=user_id,
            resource_type="job",
            resource_id=job_id,
            details=details,
            success=success,
            error_message=error_message
        )
    
    async def log_file_event(
        self,
        action: AuditAction,
        file_path: str,
        user_id: Optional[str] = None,
        file_size: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ):
        """Log file-related event."""
        event_details = details or {}
        if file_size is not None:
            event_details["file_size"] = file_size
        
        await self.log_event(
            action=action,
            user_id=user_id,
            resource_type="file",
            resource_id=file_path,
            details=event_details,
            success=success,
            error_message=error_message
        )
    
    async def log_security_event(
        self,
        action: AuditAction,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ):
        """Log security-related event."""
        await self.log_event(
            action=action,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            details=details,
            success=False,  # Security events are typically failures
            error_message=error_message
        )
    
    async def log_system_event(
        self,
        action: AuditAction,
        details: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ):
        """Log system-related event."""
        await self.log_event(
            action=action,
            resource_type="system",
            details=details,
            success=success,
            error_message=error_message
        )
    
    async def get_audit_trail(
        self,
        user_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        action: Optional[AuditAction] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> list:
        """Get audit trail with filters."""
        try:
            async with get_async_session() as session:
                audit_repo = AuditRepository(session)
                
                events = await audit_repo.get_events(
                    user_id=user_id,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    action=action.value if action else None,
                    start_date=start_date,
                    end_date=end_date,
                    limit=limit
                )
                
                return [event.to_dict() for event in events]
                
        except Exception as exc:
            self.logger.error(f"Failed to get audit trail: {exc}", exc_info=True)
            return []
    
    async def get_security_events(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> list:
        """Get security-related audit events."""
        try:
            async with get_async_session() as session:
                audit_repo = AuditRepository(session)
                
                events = await audit_repo.get_security_events(
                    start_date=start_date,
                    end_date=end_date,
                    limit=limit
                )
                
                return [event.to_dict() for event in events]
                
        except Exception as exc:
            self.logger.error(f"Failed to get security events: {exc}", exc_info=True)
            return []


# Global audit logger instance
audit_logger = AuditLogger()