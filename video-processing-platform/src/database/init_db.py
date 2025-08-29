"""
Database initialization script.
Creates tables and initial data.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings
from config.logging_config import setup_logging, get_logger
from database.connection import init_database, close_database
from database.models import User, UserRole
from database.repositories import UserRepository
from database import get_session

logger = get_logger(__name__)


async def create_admin_user():
    """Create default admin user if it doesn't exist."""
    async with get_session() as session:
        user_repo = UserRepository(session)
        
        # Check if admin user exists
        admin_user = await user_repo.get_by_username("admin")
        if admin_user:
            logger.info("Admin user already exists")
            return
        
        # Create admin user
        admin_user = await user_repo.create_user(
            username="admin",
            email="admin@videoprocessing.com",
            password="admin123",  # Change this in production!
            full_name="System Administrator",
            role=UserRole.ADMIN
        )
        
        await user_repo.verify_user(admin_user.id)
        
        logger.info(
            "Admin user created",
            extra={
                "user_id": admin_user.id,
                "username": admin_user.username,
                "email": admin_user.email
            }
        )


async def main():
    """Initialize database."""
    # Setup logging
    setup_logging()
    
    logger.info("Starting database initialization")
    
    try:
        # Initialize database
        await init_database()
        logger.info("Database tables created successfully")
        
        # Create admin user
        await create_admin_user()
        
        logger.info("Database initialization completed successfully")
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}", exc_info=True)
        sys.exit(1)
    
    finally:
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())