"""
Example usage of the database system.

This example demonstrates how to use the database models, repositories,
and service layer for common operations.
"""

import asyncio
from datetime import datetime
from typing import List

from src.database.service import get_database_service, DatabaseService
from src.database.models import (
    User, UserRole, Job, JobStatus, JobPriority,
    VideoMetadata, AuditAction, StorageBackend, AccessLevel
)


async def create_sample_user(db: DatabaseService) -> User:
    """Create a sample user."""
    print("Creating sample user...")
    
    user = await db.users.create_user(
        username="demo_user",
        email="demo@example.com",
        password="secure_password123",
        full_name="Demo User",
        role=UserRole.USER
    )
    
    print(f"Created user: {user.username} (ID: {user.id})")
    return user


async def create_sample_job(db: DatabaseService, user: User) -> Job:
    """Create a sample job."""
    print("Creating sample job...")
    
    job = await db.jobs.create_job(
        user_id=user.id,
        season_name="Demo Season 1",
        video_urls=[
            "https://example.com/episode1.mp4",
            "https://example.com/episode2.mp4",
            "https://example.com/episode3.mp4"
        ],
        request_data={
            "quality": "1080p",
            "format": "mp4",
            "compression": "medium"
        },
        priority=JobPriority.HIGH,
        video_quality="1080p",
        compression_preset="medium",
        use_gpu=True
    )
    
    print(f"Created job: {job.season_name} (ID: {job.id})")
    return job


async def create_video_metadata(db: DatabaseService, job: Job) -> List[VideoMetadata]:
    """Create video metadata for the job."""
    print("Creating video metadata...")
    
    videos = []
    for i, url in enumerate(job.video_urls, 1):
        video = await db.videos.create_video_metadata(
            job_id=job.id,
            url=url,
            episode_number=i,
            title=f"Episode {i}",
            duration=2400.0,  # 40 minutes
            filesize=1500000000,  # ~1.5GB
            format="mp4",
            codec="h264",
            resolution="1920x1080",
            fps=23.976
        )
        videos.append(video)
        print(f"  Created video metadata for Episode {i}")
    
    return videos


async def simulate_job_processing(db: DatabaseService, job: Job, videos: List[VideoMetadata]):
    """Simulate job processing workflow."""
    print("Simulating job processing workflow...")
    
    # Start job
    await db.jobs.update_status(job.id, JobStatus.INITIALIZING)
    await db.audit.log_action(
        AuditAction.JOB_STARTED,
        f"Job {job.id} started processing",
        user_id=job.user_id,
        resource_type="job",
        resource_id=job.id
    )
    
    # Download phase
    await db.jobs.update_status(job.id, JobStatus.DOWNLOADING)
    await db.jobs.update_progress(job.id, "downloading", 0)
    
    for i, video in enumerate(videos):
        print(f"  Downloading Episode {video.episode_number}...")
        
        # Start download
        await db.videos.start_download(video.id)
        
        # Simulate download progress
        for progress in [25, 50, 75, 100]:
            await db.videos.update_download_progress(video.id, progress)
            await asyncio.sleep(0.1)  # Simulate time
        
        # Create storage file for downloaded video
        storage_file = await db.storage.create_storage_file(
            filename=f"episode_{video.episode_number}_original.mp4",
            file_path=f"/tmp/downloads/episode_{video.episode_number}.mp4",
            file_size=video.filesize,
            storage_backend=StorageBackend.LOCAL,
            storage_path=f"/storage/originals/episode_{video.episode_number}.mp4",
            job_id=job.id,
            video_id=video.id,
            file_category="original",
            file_type="video",
            content_type="video/mp4"
        )
        
        print(f"    Downloaded and stored: {storage_file.filename}")
    
    # Update overall job progress
    await db.jobs.update_progress(job.id, "downloading", 100)
    
    # Processing phase
    await db.jobs.update_status(job.id, JobStatus.PROCESSING)
    await db.jobs.update_progress(job.id, "processing", 0)
    
    for i, video in enumerate(videos):
        print(f"  Processing Episode {video.episode_number}...")
        
        # Start processing
        await db.videos.start_processing(video.id)
        
        # Simulate processing progress
        for progress in [20, 40, 60, 80, 100]:
            await db.videos.update_processing_progress(video.id, progress)
            await asyncio.sleep(0.1)  # Simulate time
        
        # Create storage file for processed video
        processed_size = int(video.filesize * 0.7)  # 30% compression
        processed_file = await db.storage.create_storage_file(
            filename=f"episode_{video.episode_number}_processed.mp4",
            file_path=f"/tmp/processed/episode_{video.episode_number}.mp4",
            file_size=processed_size,
            storage_backend=StorageBackend.LOCAL,
            storage_path=f"/storage/processed/episode_{video.episode_number}.mp4",
            job_id=job.id,
            video_id=video.id,
            file_category="processed",
            file_type="video",
            content_type="video/mp4"
        )
        
        print(f"    Processed: {processed_file.filename} ({processed_file.file_size_mb:.1f}MB)")
    
    # Complete job
    await db.jobs.update_status(job.id, JobStatus.COMPLETED)
    await db.jobs.update_progress(job.id, "completed", 100)
    
    await db.audit.log_action(
        AuditAction.JOB_COMPLETED,
        f"Job {job.id} completed successfully",
        user_id=job.user_id,
        resource_type="job",
        resource_id=job.id,
        details={
            "total_videos": len(videos),
            "processing_time": "simulated"
        }
    )
    
    print("Job processing completed!")


async def demonstrate_queries(db: DatabaseService, user: User, job: Job):
    """Demonstrate various database queries."""
    print("\nDemonstrating database queries...")
    
    # User queries
    print("User queries:")
    user_jobs = await db.users.get_user_jobs(user.id)
    print(f"  User has {len(user_jobs)} jobs")
    
    user_stats = await db.users.get_user_stats()
    print(f"  Total users in system: {user_stats['total_users']}")
    
    # Job queries
    print("Job queries:")
    job_with_videos = await db.jobs.get_with_videos(job.id)
    print(f"  Job has {len(job_with_videos.videos)} videos")
    
    active_jobs = await db.jobs.get_active_jobs()
    print(f"  Active jobs in system: {len(active_jobs)}")
    
    job_stats = await db.jobs.get_job_stats()
    print(f"  Job statistics: {job_stats}")
    
    # Video queries
    print("Video queries:")
    job_videos = await db.videos.get_job_videos(job.id)
    print(f"  Videos for job: {len(job_videos)}")
    
    completed_videos = await db.videos.get_by_status(processing_status="completed")
    print(f"  Completed videos: {len(completed_videos)}")
    
    # Storage queries
    print("Storage queries:")
    job_files = await db.storage.get_job_files(job.id)
    print(f"  Storage files for job: {len(job_files)}")
    
    original_files = await db.storage.get_files_by_category("original")
    print(f"  Original files: {len(original_files)}")
    
    storage_stats = await db.storage.get_storage_stats()
    print(f"  Storage statistics: {storage_stats}")
    
    # Audit queries
    print("Audit queries:")
    user_actions = await db.audit.get_user_actions(user.id)
    print(f"  User actions logged: {len(user_actions)}")
    
    job_actions = await db.audit.get_resource_actions("job", job.id)
    print(f"  Job actions logged: {len(job_actions)}")


async def demonstrate_advanced_features(db: DatabaseService, user: User):
    """Demonstrate advanced database features."""
    print("\nDemonstrating advanced features...")
    
    # API key management
    print("API key management:")
    api_key = await db.users.generate_api_key(user.id)
    print(f"  Generated API key: {api_key[:10]}...")
    
    user_by_api = await db.users.get_by_api_key(api_key)
    print(f"  Found user by API key: {user_by_api.username}")
    
    # File expiry and cleanup
    print("File expiry and cleanup:")
    temp_file = await db.storage.create_storage_file(
        filename="temp_file.tmp",
        file_path="/tmp/temp_file.tmp",
        file_size=1000,
        storage_backend=StorageBackend.LOCAL,
        storage_path="/storage/temp/temp_file.tmp",
        is_temporary=True
    )
    
    await db.storage.set_expiry(temp_file.id, 1)  # 1 hour expiry
    print(f"  Created temporary file with expiry: {temp_file.filename}")
    
    # Search functionality
    print("Search functionality:")
    search_results = await db.storage.search_files("episode", file_type="video")
    print(f"  Found {len(search_results)} files matching 'episode'")
    
    user_search = await db.users.search_users("demo")
    print(f"  Found {len(user_search)} users matching 'demo'")
    
    # Duplicate detection
    print("Duplicate detection:")
    duplicates = await db.storage.find_duplicates()
    print(f"  Found {len(duplicates)} sets of duplicate files")


async def main():
    """Main example function."""
    print("Database Usage Example")
    print("=" * 50)
    
    async with get_database_service() as db:
        try:
            # Create sample data
            user = await create_sample_user(db)
            job = await create_sample_job(db, user)
            videos = await create_video_metadata(db, job)
            
            # Commit initial data
            await db.commit()
            
            # Simulate processing
            await simulate_job_processing(db, job, videos)
            
            # Commit processing updates
            await db.commit()
            
            # Demonstrate queries
            await demonstrate_queries(db, user, job)
            
            # Demonstrate advanced features
            await demonstrate_advanced_features(db, user)
            
            # Final commit
            await db.commit()
            
            print("\nExample completed successfully!")
            
        except Exception as e:
            print(f"Error occurred: {e}")
            await db.rollback()
            raise


if __name__ == "__main__":
    asyncio.run(main())