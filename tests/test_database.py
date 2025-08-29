"""
Tests for database models and repositories.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.database.connection import Base
from src.database.models import (
    User, UserRole, Job, JobStatus, JobPriority,
    VideoMetadata, AuditLog, AuditAction,
    StorageFile, StorageBackend, AccessLevel
)
from src.database.repositories import (
    UserRepository, JobRepository, VideoRepository,
    AuditRepository, StorageRepository
)
from src.database.service import DatabaseService


# Test database URL (in-memory SQLite for testing)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_engine():
    """Create test database engine."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Clean up
    await engine.dispose()


@pytest.fixture
async def test_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create test database session."""
    async_session = sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def db_service(test_session) -> DatabaseService:
    """Create database service for testing."""
    return DatabaseService(test_session)


@pytest.fixture
async def test_user(db_service) -> User:
    """Create test user."""
    user = await db_service.users.create_user(
        username="testuser",
        email="test@example.com",
        password="testpassword123",
        full_name="Test User"
    )
    await db_service.commit()
    return user


@pytest.fixture
async def test_job(db_service, test_user) -> Job:
    """Create test job."""
    job = await db_service.jobs.create_job(
        user_id=test_user.id,
        season_name="Test Season",
        video_urls=["http://example.com/video1.mp4", "http://example.com/video2.mp4"],
        request_data={"quality": "1080p", "format": "mp4"}
    )
    await db_service.commit()
    return job


class TestUserRepository:
    """Test user repository operations."""
    
    async def test_create_user(self, db_service):
        """Test user creation."""
        user = await db_service.users.create_user(
            username="newuser",
            email="newuser@example.com",
            password="password123",
            full_name="New User",
            role=UserRole.USER
        )
        
        assert user.id is not None
        assert user.username == "newuser"
        assert user.email == "newuser@example.com"
        assert user.full_name == "New User"
        assert user.role == UserRole.USER
        assert user.is_active is True
        assert user.is_verified is False
        assert user.verify_password("password123") is True
    
    async def test_get_by_username(self, db_service, test_user):
        """Test getting user by username."""
        user = await db_service.users.get_by_username("testuser")
        
        assert user is not None
        assert user.id == test_user.id
        assert user.username == "testuser"
    
    async def test_get_by_email(self, db_service, test_user):
        """Test getting user by email."""
        user = await db_service.users.get_by_email("test@example.com")
        
        assert user is not None
        assert user.id == test_user.id
        assert user.email == "test@example.com"
    
    async def test_authenticate(self, db_service, test_user):
        """Test user authentication."""
        # Valid credentials
        user = await db_service.users.authenticate("testuser", "testpassword123")
        assert user is not None
        assert user.id == test_user.id
        
        # Invalid password
        user = await db_service.users.authenticate("testuser", "wrongpassword")
        assert user is None
        
        # Invalid username
        user = await db_service.users.authenticate("wronguser", "testpassword123")
        assert user is None
    
    async def test_update_password(self, db_service, test_user):
        """Test password update."""
        updated_user = await db_service.users.update_password(test_user.id, "newpassword123")
        
        assert updated_user is not None
        assert updated_user.verify_password("newpassword123") is True
        assert updated_user.verify_password("testpassword123") is False
    
    async def test_generate_api_key(self, db_service, test_user):
        """Test API key generation."""
        api_key = await db_service.users.generate_api_key(test_user.id)
        
        assert api_key is not None
        assert len(api_key) > 20  # Should be a reasonable length
        
        # Verify user has the API key
        user = await db_service.users.get(test_user.id)
        assert user.api_key == api_key


class TestJobRepository:
    """Test job repository operations."""
    
    async def test_create_job(self, db_service, test_user):
        """Test job creation."""
        job = await db_service.jobs.create_job(
            user_id=test_user.id,
            season_name="New Season",
            video_urls=["http://example.com/video.mp4"],
            request_data={"quality": "720p"}
        )
        
        assert job.id is not None
        assert job.user_id == test_user.id
        assert job.season_name == "New Season"
        assert job.video_urls == ["http://example.com/video.mp4"]
        assert job.status == JobStatus.PENDING
        assert job.priority == JobPriority.NORMAL
    
    async def test_get_user_jobs(self, db_service, test_user, test_job):
        """Test getting user jobs."""
        jobs = await db_service.jobs.get_user_jobs(test_user.id)
        
        assert len(jobs) >= 1
        assert any(job.id == test_job.id for job in jobs)
    
    async def test_update_status(self, db_service, test_job):
        """Test job status update."""
        updated_job = await db_service.jobs.update_status(
            test_job.id, 
            JobStatus.DOWNLOADING
        )
        
        assert updated_job is not None
        assert updated_job.status == JobStatus.DOWNLOADING
        assert updated_job.started_at is not None
    
    async def test_update_progress(self, db_service, test_job):
        """Test job progress update."""
        updated_job = await db_service.jobs.update_progress(
            test_job.id,
            "downloading",
            50,
            {"current_file": "video1.mp4"}
        )
        
        assert updated_job is not None
        assert updated_job.current_stage == "downloading"
        assert updated_job.progress_percentage == 50
        assert "downloading" in updated_job.progress
    
    async def test_get_active_jobs(self, db_service, test_job):
        """Test getting active jobs."""
        # Update job to active status
        await db_service.jobs.update_status(test_job.id, JobStatus.DOWNLOADING)
        
        active_jobs = await db_service.jobs.get_active_jobs()
        
        assert len(active_jobs) >= 1
        assert any(job.id == test_job.id for job in active_jobs)


class TestVideoRepository:
    """Test video repository operations."""
    
    async def test_create_video_metadata(self, db_service, test_job):
        """Test video metadata creation."""
        video = await db_service.videos.create_video_metadata(
            job_id=test_job.id,
            url="http://example.com/video.mp4",
            episode_number=1,
            title="Test Episode"
        )
        
        assert video.id is not None
        assert video.job_id == test_job.id
        assert video.url == "http://example.com/video.mp4"
        assert video.episode_number == 1
        assert video.title == "Test Episode"
        assert video.download_status == "pending"
        assert video.processing_status == "pending"
    
    async def test_get_job_videos(self, db_service, test_job):
        """Test getting videos for a job."""
        # Create test videos
        video1 = await db_service.videos.create_video_metadata(
            job_id=test_job.id,
            url="http://example.com/video1.mp4",
            episode_number=1
        )
        video2 = await db_service.videos.create_video_metadata(
            job_id=test_job.id,
            url="http://example.com/video2.mp4",
            episode_number=2
        )
        
        videos = await db_service.videos.get_job_videos(test_job.id)
        
        assert len(videos) == 2
        assert videos[0].episode_number == 1  # Should be ordered by episode
        assert videos[1].episode_number == 2
    
    async def test_update_download_progress(self, db_service, test_job):
        """Test updating download progress."""
        video = await db_service.videos.create_video_metadata(
            job_id=test_job.id,
            url="http://example.com/video.mp4",
            episode_number=1
        )
        
        updated_video = await db_service.videos.update_download_progress(
            video.id, 75, "downloading"
        )
        
        assert updated_video is not None
        assert updated_video.download_progress == 75
        assert updated_video.download_status == "downloading"
    
    async def test_start_download(self, db_service, test_job):
        """Test starting download."""
        video = await db_service.videos.create_video_metadata(
            job_id=test_job.id,
            url="http://example.com/video.mp4",
            episode_number=1
        )
        
        updated_video = await db_service.videos.start_download(video.id)
        
        assert updated_video is not None
        assert updated_video.download_status == "downloading"
        assert updated_video.download_started_at is not None
        assert updated_video.download_progress == 0


class TestAuditRepository:
    """Test audit repository operations."""
    
    async def test_log_action(self, db_service, test_user):
        """Test logging audit action."""
        audit_log = await db_service.audit.log_action(
            action=AuditAction.USER_LOGIN,
            description="User logged in successfully",
            user_id=test_user.id,
            ip_address="192.168.1.1",
            details={"browser": "Chrome"}
        )
        
        assert audit_log.id is not None
        assert audit_log.action == AuditAction.USER_LOGIN
        assert audit_log.user_id == test_user.id
        assert audit_log.ip_address == "192.168.1.1"
        assert audit_log.success is True
        assert audit_log.details["browser"] == "Chrome"
    
    async def test_get_user_actions(self, db_service, test_user):
        """Test getting user actions."""
        # Create test audit logs
        await db_service.audit.log_action(
            AuditAction.USER_LOGIN,
            "Login 1",
            user_id=test_user.id
        )
        await db_service.audit.log_action(
            AuditAction.USER_LOGOUT,
            "Logout 1",
            user_id=test_user.id
        )
        
        actions = await db_service.audit.get_user_actions(test_user.id)
        
        assert len(actions) >= 2
        assert all(action.user_id == test_user.id for action in actions)
    
    async def test_get_failed_actions(self, db_service, test_user):
        """Test getting failed actions."""
        # Create failed action
        await db_service.audit.log_action(
            AuditAction.AUTH_FAILED,
            "Authentication failed",
            user_id=test_user.id,
            success=False,
            error_message="Invalid password"
        )
        
        failed_actions = await db_service.audit.get_failed_actions()
        
        assert len(failed_actions) >= 1
        assert all(not action.success for action in failed_actions)


class TestStorageRepository:
    """Test storage repository operations."""
    
    async def test_create_storage_file(self, db_service, test_job):
        """Test storage file creation."""
        storage_file = await db_service.storage.create_storage_file(
            filename="test_video.mp4",
            file_path="/tmp/test_video.mp4",
            file_size=1024000,
            storage_backend=StorageBackend.LOCAL,
            storage_path="/storage/test_video.mp4",
            job_id=test_job.id,
            file_category="original",
            file_type="video"
        )
        
        assert storage_file.id is not None
        assert storage_file.filename == "test_video.mp4"
        assert storage_file.file_size == 1024000
        assert storage_file.storage_backend == StorageBackend.LOCAL
        assert storage_file.job_id == test_job.id
        assert storage_file.file_category == "original"
        assert storage_file.file_type == "video"
        assert storage_file.file_extension == ".mp4"
    
    async def test_get_job_files(self, db_service, test_job):
        """Test getting files for a job."""
        # Create test files
        file1 = await db_service.storage.create_storage_file(
            filename="original.mp4",
            file_path="/tmp/original.mp4",
            file_size=1000000,
            storage_backend=StorageBackend.LOCAL,
            storage_path="/storage/original.mp4",
            job_id=test_job.id,
            file_category="original"
        )
        file2 = await db_service.storage.create_storage_file(
            filename="processed.mp4",
            file_path="/tmp/processed.mp4",
            file_size=800000,
            storage_backend=StorageBackend.LOCAL,
            storage_path="/storage/processed.mp4",
            job_id=test_job.id,
            file_category="processed"
        )
        
        all_files = await db_service.storage.get_job_files(test_job.id)
        original_files = await db_service.storage.get_job_files(
            test_job.id, file_category="original"
        )
        
        assert len(all_files) == 2
        assert len(original_files) == 1
        assert original_files[0].file_category == "original"
    
    async def test_set_expiry(self, db_service, test_job):
        """Test setting file expiry."""
        storage_file = await db_service.storage.create_storage_file(
            filename="temp.mp4",
            file_path="/tmp/temp.mp4",
            file_size=500000,
            storage_backend=StorageBackend.LOCAL,
            storage_path="/storage/temp.mp4",
            job_id=test_job.id,
            is_temporary=True
        )
        
        updated_file = await db_service.storage.set_expiry(storage_file.id, 24)
        
        assert updated_file is not None
        assert updated_file.expires_at is not None
        assert updated_file.expires_at > datetime.utcnow()
    
    async def test_get_expired_files(self, db_service, test_job):
        """Test getting expired files."""
        # Create expired file
        storage_file = await db_service.storage.create_storage_file(
            filename="expired.mp4",
            file_path="/tmp/expired.mp4",
            file_size=500000,
            storage_backend=StorageBackend.LOCAL,
            storage_path="/storage/expired.mp4",
            job_id=test_job.id
        )
        
        # Set expiry to past date
        past_date = datetime.utcnow() - timedelta(hours=1)
        await db_service.storage.update(storage_file.id, expires_at=past_date)
        
        expired_files = await db_service.storage.get_expired_files()
        
        assert len(expired_files) >= 1
        assert any(f.id == storage_file.id for f in expired_files)


class TestDatabaseService:
    """Test database service integration."""
    
    async def test_service_properties(self, db_service):
        """Test service repository properties."""
        assert isinstance(db_service.users, UserRepository)
        assert isinstance(db_service.jobs, JobRepository)
        assert isinstance(db_service.videos, VideoRepository)
        assert isinstance(db_service.audit, AuditRepository)
        assert isinstance(db_service.storage, StorageRepository)
    
    async def test_transaction_management(self, db_service):
        """Test transaction commit and rollback."""
        # Test commit
        user = await db_service.users.create_user(
            username="txtest",
            email="txtest@example.com",
            password="password123"
        )
        await db_service.commit()
        
        # Verify user exists
        found_user = await db_service.users.get_by_username("txtest")
        assert found_user is not None
        
        # Test rollback
        await db_service.users.create_user(
            username="rollbacktest",
            email="rollbacktest@example.com",
            password="password123"
        )
        await db_service.rollback()
        
        # Verify user doesn't exist after rollback
        not_found_user = await db_service.users.get_by_username("rollbacktest")
        assert not_found_user is None


# Integration tests
class TestDatabaseIntegration:
    """Test database integration scenarios."""
    
    async def test_complete_job_workflow(self, db_service):
        """Test complete job processing workflow."""
        # Create user
        user = await db_service.users.create_user(
            username="workflowuser",
            email="workflow@example.com",
            password="password123"
        )
        
        # Create job
        job = await db_service.jobs.create_job(
            user_id=user.id,
            season_name="Workflow Test",
            video_urls=["http://example.com/ep1.mp4", "http://example.com/ep2.mp4"],
            request_data={"quality": "1080p"}
        )
        
        # Create video metadata
        video1 = await db_service.videos.create_video_metadata(
            job_id=job.id,
            url="http://example.com/ep1.mp4",
            episode_number=1,
            title="Episode 1"
        )
        video2 = await db_service.videos.create_video_metadata(
            job_id=job.id,
            url="http://example.com/ep2.mp4",
            episode_number=2,
            title="Episode 2"
        )
        
        # Create storage files
        storage1 = await db_service.storage.create_storage_file(
            filename="ep1_original.mp4",
            file_path="/tmp/ep1_original.mp4",
            file_size=2000000,
            storage_backend=StorageBackend.LOCAL,
            storage_path="/storage/ep1_original.mp4",
            job_id=job.id,
            video_id=video1.id,
            file_category="original"
        )
        
        # Log audit actions
        await db_service.audit.log_action(
            AuditAction.JOB_CREATED,
            f"Job {job.id} created",
            user_id=user.id,
            resource_type="job",
            resource_id=job.id
        )
        
        await db_service.commit()
        
        # Verify complete workflow
        job_with_videos = await db_service.jobs.get_with_videos(job.id)
        assert job_with_videos is not None
        assert len(job_with_videos.videos) == 2
        
        job_files = await db_service.storage.get_job_files(job.id)
        assert len(job_files) == 1
        
        user_actions = await db_service.audit.get_user_actions(user.id)
        assert len(user_actions) >= 1
        
        # Update job progress
        await db_service.jobs.update_status(job.id, JobStatus.DOWNLOADING)
        await db_service.videos.start_download(video1.id)
        await db_service.videos.update_download_progress(video1.id, 100)
        
        await db_service.commit()
        
        # Verify updates
        updated_job = await db_service.jobs.get(job.id)
        assert updated_job.status == JobStatus.DOWNLOADING
        
        updated_video = await db_service.videos.get(video1.id)
        assert updated_video.download_progress == 100
        assert updated_video.download_status == "completed"