"""
Correlation ID management for distributed tracing.
"""

import uuid
import contextvars
from typing import Optional, Dict, Any
from contextvars import ContextVar

from ..config.logging_config import get_logger

logger = get_logger(__name__)

# Context variable for correlation ID
correlation_id_var: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)
request_context_var: ContextVar[Dict[str, Any]] = ContextVar('request_context', default={})


class CorrelationManager:
    """Manages correlation IDs for request tracing."""
    
    @staticmethod
    def generate_id() -> str:
        """Generate a new correlation ID."""
        return str(uuid.uuid4())
    
    @staticmethod
    def set_correlation_id(correlation_id: Optional[str] = None) -> str:
        """Set correlation ID in context."""
        if correlation_id is None:
            correlation_id = CorrelationManager.generate_id()
        
        correlation_id_var.set(correlation_id)
        logger.debug(f"Correlation ID set: {correlation_id}")
        return correlation_id
    
    @staticmethod
    def get_correlation_id() -> Optional[str]:
        """Get current correlation ID from context."""
        return correlation_id_var.get()
    
    @staticmethod
    def ensure_correlation_id() -> str:
        """Ensure correlation ID exists, create if needed."""
        correlation_id = correlation_id_var.get()
        if correlation_id is None:
            correlation_id = CorrelationManager.generate_id()
            correlation_id_var.set(correlation_id)
        return correlation_id
    
    @staticmethod
    def set_request_context(context: Dict[str, Any]):
        """Set request context information."""
        current_context = request_context_var.get({})
        current_context.update(context)
        request_context_var.set(current_context)
    
    @staticmethod
    def get_request_context() -> Dict[str, Any]:
        """Get current request context."""
        return request_context_var.get({})
    
    @staticmethod
    def add_context(key: str, value: Any):
        """Add single item to request context."""
        context = request_context_var.get({})
        context[key] = value
        request_context_var.set(context)
    
    @staticmethod
    def clear_context():
        """Clear all context variables."""
        correlation_id_var.set(None)
        request_context_var.set({})
    
    @staticmethod
    def get_logging_context() -> Dict[str, Any]:
        """Get context for structured logging."""
        context = {
            "correlation_id": correlation_id_var.get(),
        }
        context.update(request_context_var.get({}))
        return {k: v for k, v in context.items() if v is not None}


# Convenience functions
def get_correlation_id() -> Optional[str]:
    """Get current correlation ID."""
    return CorrelationManager.get_correlation_id()


def set_correlation_id(correlation_id: Optional[str] = None) -> str:
    """Set correlation ID."""
    return CorrelationManager.set_correlation_id(correlation_id)


def ensure_correlation_id() -> str:
    """Ensure correlation ID exists."""
    return CorrelationManager.ensure_correlation_id()


def get_logging_context() -> Dict[str, Any]:
    """Get logging context."""
    return CorrelationManager.get_logging_context()