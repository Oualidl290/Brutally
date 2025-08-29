"""
WebSocket endpoints for real-time job progress updates and notifications.
"""

import json
import asyncio
from typing import Dict, Set, Optional, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.websockets import WebSocketState
from datetime import datetime

from ..middleware.auth import jwt_manager
from ...config.logging_config import get_logger
from ...utils.exceptions import AuthenticationError

logger = get_logger(__name__)
router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections for real-time updates."""
    
    def __init__(self):
        # Active connections: {user_id: {connection_id: websocket}}
        self.active_connections: Dict[str, Dict[str, WebSocket]] = {}
        # Job subscriptions: {job_id: {user_id: set of connection_ids}}
        self.job_subscriptions: Dict[str, Dict[str, Set[str]]] = {}
        # Connection metadata: {connection_id: {user_id, connected_at, etc.}}
        self.connection_metadata: Dict[str, Dict[str, Any]] = {}
    
    async def connect(self, websocket: WebSocket, user_id: str, connection_id: str):
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        
        # Initialize user connections if not exists
        if user_id not in self.active_connections:
            self.active_connections[user_id] = {}
        
        # Store connection
        self.active_connections[user_id][connection_id] = websocket
        self.connection_metadata[connection_id] = {
            "user_id": user_id,
            "connected_at": datetime.utcnow(),
            "last_ping": datetime.utcnow()
        }
        
        logger.info(
            f"WebSocket connection established",
            extra={
                "user_id": user_id,
                "connection_id": connection_id,
                "total_connections": self.get_total_connections()
            }
        )
    
    def disconnect(self, user_id: str, connection_id: str):
        """Remove a WebSocket connection."""
        # Remove from active connections
        if user_id in self.active_connections:
            self.active_connections[user_id].pop(connection_id, None)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        
        # Remove from job subscriptions
        for job_id, job_subs in self.job_subscriptions.items():
            if user_id in job_subs:
                job_subs[user_id].discard(connection_id)
                if not job_subs[user_id]:
                    del job_subs[user_id]
        
        # Remove connection metadata
        self.connection_metadata.pop(connection_id, None)
        
        logger.info(
            f"WebSocket connection closed",
            extra={
                "user_id": user_id,
                "connection_id": connection_id,
                "total_connections": self.get_total_connections()
            }
        )
    
    async def send_personal_message(self, message: dict, user_id: str, connection_id: Optional[str] = None):
        """Send message to specific user connection(s)."""
        if user_id not in self.active_connections:
            return
        
        connections = self.active_connections[user_id]
        
        # Send to specific connection or all user connections
        target_connections = {connection_id: connections[connection_id]} if connection_id and connection_id in connections else connections
        
        for conn_id, websocket in target_connections.items():
            try:
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_text(json.dumps(message))
            except Exception as e:
                logger.warning(f"Failed to send message to {user_id}:{conn_id}: {e}")
                # Connection might be stale, will be cleaned up on next disconnect
    
    async def broadcast_job_update(self, job_id: str, message: dict):
        """Broadcast job update to all subscribed users."""
        if job_id not in self.job_subscriptions:
            return
        
        job_subs = self.job_subscriptions[job_id]
        
        for user_id, connection_ids in job_subs.items():
            for connection_id in connection_ids.copy():  # Copy to avoid modification during iteration
                try:
                    websocket = self.active_connections.get(user_id, {}).get(connection_id)
                    if websocket and websocket.client_state == WebSocketState.CONNECTED:
                        await websocket.send_text(json.dumps(message))
                except Exception as e:
                    logger.warning(f"Failed to broadcast to {user_id}:{connection_id}: {e}")
                    # Remove stale connection
                    connection_ids.discard(connection_id)
    
    def subscribe_to_job(self, job_id: str, user_id: str, connection_id: str):
        """Subscribe connection to job updates."""
        if job_id not in self.job_subscriptions:
            self.job_subscriptions[job_id] = {}
        
        if user_id not in self.job_subscriptions[job_id]:
            self.job_subscriptions[job_id][user_id] = set()
        
        self.job_subscriptions[job_id][user_id].add(connection_id)
        
        logger.debug(
            f"Subscribed to job updates",
            extra={
                "job_id": job_id,
                "user_id": user_id,
                "connection_id": connection_id
            }
        )
    
    def unsubscribe_from_job(self, job_id: str, user_id: str, connection_id: str):
        """Unsubscribe connection from job updates."""
        if job_id in self.job_subscriptions and user_id in self.job_subscriptions[job_id]:
            self.job_subscriptions[job_id][user_id].discard(connection_id)
            
            # Clean up empty subscriptions
            if not self.job_subscriptions[job_id][user_id]:
                del self.job_subscriptions[job_id][user_id]
            
            if not self.job_subscriptions[job_id]:
                del self.job_subscriptions[job_id]
        
        logger.debug(
            f"Unsubscribed from job updates",
            extra={
                "job_id": job_id,
                "user_id": user_id,
                "connection_id": connection_id
            }
        )
    
    def get_total_connections(self) -> int:
        """Get total number of active connections."""
        return sum(len(connections) for connections in self.active_connections.values())
    
    def get_job_subscriber_count(self, job_id: str) -> int:
        """Get number of subscribers for a job."""
        if job_id not in self.job_subscriptions:
            return 0
        
        return sum(len(connection_ids) for connection_ids in self.job_subscriptions[job_id].values())


# Global connection manager
manager = ConnectionManager()


async def authenticate_websocket(token: str) -> Dict[str, Any]:
    """Authenticate WebSocket connection using JWT token."""
    try:
        payload = jwt_manager.verify_token(token)
        return {
            "user_id": payload.get("sub"),
            "username": payload.get("username"),
            "role": payload.get("role"),
            "permissions": payload.get("permissions", [])
        }
    except Exception as e:
        raise AuthenticationError(f"WebSocket authentication failed: {e}")


@router.websocket("/progress")
async def websocket_progress_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT authentication token")
):
    """
    WebSocket endpoint for real-time job progress updates.
    
    Clients can subscribe to specific job updates and receive real-time
    progress notifications, status changes, and completion events.
    """
    connection_id = None
    user_id = None
    
    try:
        # Authenticate user
        user_info = await authenticate_websocket(token)
        user_id = user_info["user_id"]
        
        # Generate unique connection ID
        import uuid
        connection_id = str(uuid.uuid4())
        
        # Accept connection
        await manager.connect(websocket, user_id, connection_id)
        
        # Send welcome message
        welcome_message = {
            "type": "connection_established",
            "message": "WebSocket connection established",
            "connection_id": connection_id,
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        await websocket.send_text(json.dumps(welcome_message))
        
        # Handle incoming messages
        while True:
            try:
                # Receive message from client
                data = await websocket.receive_text()
                message = json.loads(data)
                
                await handle_websocket_message(websocket, user_id, connection_id, message)
                
            except WebSocketDisconnect:
                break
            except json.JSONDecodeError:
                error_message = {
                    "type": "error",
                    "message": "Invalid JSON format",
                    "timestamp": datetime.utcnow().isoformat()
                }
                await websocket.send_text(json.dumps(error_message))
            except Exception as e:
                logger.error(f"WebSocket message handling error: {e}", exc_info=True)
                error_message = {
                    "type": "error",
                    "message": "Message processing error",
                    "timestamp": datetime.utcnow().isoformat()
                }
                await websocket.send_text(json.dumps(error_message))
    
    except AuthenticationError as e:
        logger.warning(f"WebSocket authentication failed: {e}")
        await websocket.close(code=4001, reason="Authentication failed")
    
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}", exc_info=True)
        await websocket.close(code=1011, reason="Internal server error")
    
    finally:
        # Clean up connection
        if user_id and connection_id:
            manager.disconnect(user_id, connection_id)


async def handle_websocket_message(websocket: WebSocket, user_id: str, connection_id: str, message: dict):
    """Handle incoming WebSocket messages from clients."""
    
    message_type = message.get("type")
    
    if message_type == "subscribe_job":
        # Subscribe to job updates
        job_id = message.get("job_id")
        if job_id:
            # In a real implementation, verify user has access to this job
            manager.subscribe_to_job(job_id, user_id, connection_id)
            
            response = {
                "type": "subscription_confirmed",
                "job_id": job_id,
                "message": f"Subscribed to job {job_id} updates",
                "timestamp": datetime.utcnow().isoformat()
            }
            await websocket.send_text(json.dumps(response))
    
    elif message_type == "unsubscribe_job":
        # Unsubscribe from job updates
        job_id = message.get("job_id")
        if job_id:
            manager.unsubscribe_from_job(job_id, user_id, connection_id)
            
            response = {
                "type": "unsubscription_confirmed",
                "job_id": job_id,
                "message": f"Unsubscribed from job {job_id} updates",
                "timestamp": datetime.utcnow().isoformat()
            }
            await websocket.send_text(json.dumps(response))
    
    elif message_type == "ping":
        # Handle ping for connection keepalive
        manager.connection_metadata[connection_id]["last_ping"] = datetime.utcnow()
        
        response = {
            "type": "pong",
            "timestamp": datetime.utcnow().isoformat()
        }
        await websocket.send_text(json.dumps(response))
    
    elif message_type == "get_status":
        # Get current connection status
        response = {
            "type": "status",
            "connection_id": connection_id,
            "user_id": user_id,
            "connected_at": manager.connection_metadata[connection_id]["connected_at"].isoformat(),
            "total_connections": manager.get_total_connections(),
            "timestamp": datetime.utcnow().isoformat()
        }
        await websocket.send_text(json.dumps(response))
    
    else:
        # Unknown message type
        response = {
            "type": "error",
            "message": f"Unknown message type: {message_type}",
            "timestamp": datetime.utcnow().isoformat()
        }
        await websocket.send_text(json.dumps(response))


# Functions for sending updates from other parts of the application

async def send_job_progress_update(job_id: str, progress_data: dict):
    """Send job progress update to all subscribers."""
    message = {
        "type": "job_progress",
        "job_id": job_id,
        "data": progress_data,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    await manager.broadcast_job_update(job_id, message)


async def send_job_status_change(job_id: str, old_status: str, new_status: str, additional_data: dict = None):
    """Send job status change notification to all subscribers."""
    message = {
        "type": "job_status_change",
        "job_id": job_id,
        "old_status": old_status,
        "new_status": new_status,
        "data": additional_data or {},
        "timestamp": datetime.utcnow().isoformat()
    }
    
    await manager.broadcast_job_update(job_id, message)


async def send_job_completion(job_id: str, success: bool, result_data: dict = None):
    """Send job completion notification to all subscribers."""
    message = {
        "type": "job_completed",
        "job_id": job_id,
        "success": success,
        "data": result_data or {},
        "timestamp": datetime.utcnow().isoformat()
    }
    
    await manager.broadcast_job_update(job_id, message)


async def send_system_notification(user_id: str, notification_data: dict):
    """Send system notification to specific user."""
    message = {
        "type": "system_notification",
        "data": notification_data,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    await manager.send_personal_message(message, user_id)


# WebSocket connection statistics endpoint
@router.get("/stats")
async def get_websocket_stats():
    """Get WebSocket connection statistics."""
    return {
        "total_connections": manager.get_total_connections(),
        "active_users": len(manager.active_connections),
        "job_subscriptions": len(manager.job_subscriptions),
        "timestamp": datetime.utcnow().isoformat()
    }