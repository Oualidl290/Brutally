"""
Audit log repository for tracking user actions and system events.
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Union
from uuid import UUID

from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from .base_repo import BaseRepository
from ..models.audit import AuditLog, AuditAction
from ...config.logging_config import get_logger

logger = get_logger(__name__)


class AuditRepository(BaseRepository[AuditLog]):
    """Repository for audit log operations."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(AuditLog, session)
    
    async def log_action(
        self,
        action: AuditAction,
        description: str,
        user_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> AuditLog:
        """Log an action to the audit trail."""
        audit_data = {
            "action": action,
            "description": description,
            "user_id": user_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "details": details or {},
            "success": success,
            "error_message": error_message,
        }
        
        audit_log = await self.create(**audit_data)
        
        logger.debug(
            "Audit log created",
            extra={
                "audit_id": audit_log.id,
                "action": action.value,
                "user_id": user_id,
                "success": success
            }
        )
        
        return audit_log
    
    async def get_user_actions(
        self,
        user_id: str,
        action: Optional[AuditAction] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[AuditLog]:
        """Get audit logs for a specific user."""
        stmt = select(AuditLog).where(AuditLog.user_id == user_id)
        
        if action:
            stmt = stmt.where(AuditLog.action == action)
        
        if start_date:
            stmt = stmt.where(AuditLog.created_at >= start_date)
        
        if end_date:
            stmt = stmt.where(AuditLog.created_at <= end_date)
        
        stmt = stmt.order_by(desc(AuditLog.created_at)).offset(skip).limit(limit)
        
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def get_resource_actions(
        self,
        resource_type: str,
        resource_id: str,
        action: Optional[AuditAction] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[AuditLog]:
        """Get audit logs for a specific resource."""
        stmt = select(AuditLog).where(
            and_(
                AuditLog.resource_type == resource_type,
                AuditLog.resource_id == resource_id
            )
        )
        
        if action:
            stmt = stmt.where(AuditLog.action == action)
        
        stmt = stmt.order_by(desc(AuditLog.created_at)).offset(skip).limit(limit)
        
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def get_actions_by_type(
        self,
        action: AuditAction,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        success_only: bool = False,
        skip: int = 0,
        limit: int = 100
    ) -> List[AuditLog]:
        """Get audit logs by action type."""
        stmt = select(AuditLog).where(AuditLog.action == action)
        
        if start_date:
            stmt = stmt.where(AuditLog.created_at >= start_date)
        
        if end_date:
            stmt = stmt.where(AuditLog.created_at <= end_date)
        
        if success_only:
            stmt = stmt.where(AuditLog.success == True)
        
        stmt = stmt.order_by(desc(AuditLog.created_at)).offset(skip).limit(limit)
        
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def get_failed_actions(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        action: Optional[AuditAction] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[AuditLog]:
        """Get failed actions from audit logs."""
        stmt = select(AuditLog).where(AuditLog.success == False)
        
        if start_date:
            stmt = stmt.where(AuditLog.created_at >= start_date)
        
        if end_date:
            stmt = stmt.where(AuditLog.created_at <= end_date)
        
        if action:
            stmt = stmt.where(AuditLog.action == action)
        
        stmt = stmt.order_by(desc(AuditLog.created_at)).offset(skip).limit(limit)
        
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def get_security_events(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        ip_address: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[AuditLog]:
        """Get security-related audit events."""
        security_actions = [
            AuditAction.AUTH_FAILED,
            AuditAction.ACCESS_DENIED,
            AuditAction.API_KEY_CREATED,
            AuditAction.API_KEY_REVOKED,
        ]
        
        stmt = select(AuditLog).where(AuditLog.action.in_(security_actions))
        
        if start_date:
            stmt = stmt.where(AuditLog.created_at >= start_date)
        
        if end_date:
            stmt = stmt.where(AuditLog.created_at <= end_date)
        
        if ip_address:
            stmt = stmt.where(AuditLog.ip_address == ip_address)
        
        stmt = stmt.order_by(desc(AuditLog.created_at)).offset(skip).limit(limit)
        
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def get_audit_stats(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get audit statistics."""
        base_query = select(AuditLog)
        
        if start_date:
            base_query = base_query.where(AuditLog.created_at >= start_date)
        
        if end_date:
            base_query = base_query.where(AuditLog.created_at <= end_date)
        
        # Total events
        total_stmt = select(func.count()).select_from(base_query.subquery())
        total_result = await self.session.execute(total_stmt)
        total_events = total_result.scalar()
        
        # Events by action
        action_stmt = (
            select(AuditLog.action, func.count())
            .select_from(base_query.subquery())
            .group_by(AuditLog.action)
        )
        if start_date:
            action_stmt = action_stmt.where(AuditLog.created_at >= start_date)
        if end_date:
            action_stmt = action_stmt.where(AuditLog.created_at <= end_date)
        
        action_result = await self.session.execute(action_stmt)
        action_counts = {action.value: count for action, count in action_result.all()}
        
        # Success/failure counts
        success_stmt = (
            select(AuditLog.success, func.count())
            .select_from(base_query.subquery())
            .group_by(AuditLog.success)
        )
        if start_date:
            success_stmt = success_stmt.where(AuditLog.created_at >= start_date)
        if end_date:
            success_stmt = success_stmt.where(AuditLog.created_at <= end_date)
        
        success_result = await self.session.execute(success_stmt)
        success_counts = {
            "successful": 0,
            "failed": 0
        }
        for success, count in success_result.all():
            if success:
                success_counts["successful"] = count
            else:
                success_counts["failed"] = count
        
        # Top IP addresses
        ip_stmt = (
            select(AuditLog.ip_address, func.count())
            .select_from(base_query.subquery())
            .where(AuditLog.ip_address.isnot(None))
            .group_by(AuditLog.ip_address)
            .order_by(desc(func.count()))
            .limit(10)
        )
        if start_date:
            ip_stmt = ip_stmt.where(AuditLog.created_at >= start_date)
        if end_date:
            ip_stmt = ip_stmt.where(AuditLog.created_at <= end_date)
        
        ip_result = await self.session.execute(ip_stmt)
        top_ips = [{"ip": ip, "count": count} for ip, count in ip_result.all()]
        
        return {
            "total_events": total_events,
            "action_counts": action_counts,
            "success_counts": success_counts,
            "top_ips": top_ips,
        }
    
    async def cleanup_old_logs(self, days: int = 90) -> int:
        """Clean up old audit logs."""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Don't delete security events - keep them longer
        security_actions = [
            AuditAction.AUTH_FAILED,
            AuditAction.ACCESS_DENIED,
            AuditAction.API_KEY_CREATED,
            AuditAction.API_KEY_REVOKED,
        ]
        
        stmt = select(AuditLog).where(
            and_(
                AuditLog.created_at < cutoff_date,
                ~AuditLog.action.in_(security_actions)
            )
        )
        
        result = await self.session.execute(stmt)
        old_logs = result.scalars().all()
        
        deleted_count = 0
        for log in old_logs:
            if await self.delete(log.id):
                deleted_count += 1
        
        logger.info(
            f"Cleaned up {deleted_count} old audit logs",
            extra={"deleted_count": deleted_count, "cutoff_days": days}
        )
        
        return deleted_count
    
    async def get_user_login_history(
        self,
        user_id: str,
        days: int = 30,
        limit: int = 100
    ) -> List[AuditLog]:
        """Get user login history."""
        start_date = datetime.utcnow() - timedelta(days=days)
        
        return await self.get_user_actions(
            user_id=user_id,
            action=AuditAction.USER_LOGIN,
            start_date=start_date,
            limit=limit
        )
    
    async def detect_suspicious_activity(
        self,
        hours: int = 24,
        failed_attempts_threshold: int = 5
    ) -> List[Dict[str, Any]]:
        """Detect suspicious activity patterns."""
        start_date = datetime.utcnow() - timedelta(hours=hours)
        
        # Find IPs with multiple failed login attempts
        stmt = (
            select(AuditLog.ip_address, func.count())
            .where(
                and_(
                    AuditLog.action == AuditAction.AUTH_FAILED,
                    AuditLog.created_at >= start_date,
                    AuditLog.ip_address.isnot(None)
                )
            )
            .group_by(AuditLog.ip_address)
            .having(func.count() >= failed_attempts_threshold)
            .order_by(desc(func.count()))
        )
        
        result = await self.session.execute(stmt)
        suspicious_ips = [
            {"ip_address": ip, "failed_attempts": count}
            for ip, count in result.all()
        ]
        
        return suspicious_ips