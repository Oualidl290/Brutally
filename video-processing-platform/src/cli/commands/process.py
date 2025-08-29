"""
Video processing CLI commands.
"""

import click
import asyncio
import json
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from ...config.logging_config import get_logger
from ...services.processing_service import ProcessingService
from ...core.downloader import DownloadManager
from ...core.processor import VideoProcessor, ProcessingConfig
from ...core.compressor import IntelligentCompressor, CompressionProfile
from ...core.merger import VideoMerger, MergeConfig
from ...hardware.hardware_manager import HardwareManager
from ...database.connection import get_async_session
from ...database.repositories.job_repo import JobRepository
from ...database.models.job import Job, JobStatus, JobPriority
from ...workers.job_manager import JobManager, JobExecutionPlan, JobStage

logger = get_logger(__name__)


@click.group(name='process')
def process_group():
    """Video processing commands."""
    pass


@process_group.command()
@click.argument('urls', nargs=-1, required=True)
@click.option(
    '--output-dir', '-o',
    type=click.Path(),
    default='./output',
    help='Output directory for downloaded videos'
)
@click.option(
    '--quality',
    type=click.Choice(['480p', '720p', '1080p', '2160p']),
    default='1080p',
    help='Video quality to download'
)
@click.option(
    '--format',
    type=click.Choice(['mp4', 'mkv', 'webm']),
    default='mp4',
    help='Output video format'
)
@click.option(
    '--concurrent', '-c',
    type=int,
    default=3,
    help='Number of concurrent downloads'
)
@click.option(
    '--job-name',
    type=str,
    help='Custom job name'
)
@click.option(
    '--priority',
    type=click.Choice(['low', 'normal', 'high', 'urgent']),
    default='normal',
    help='Job priority'
)
def download(
    urls: tuple,
    output_dir: str,
    quality: str,
    format: str,
    concurrent: int,
    job_name: Optional[str],
    priority: str
):
    """Download videos from URLs."""
    click.echo(f"📥 Downloading {len(urls)} video(s)...")
    
    async def run_download():
        try:
            # Create output directory
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            
            # Initialize download manager
            download_manager = DownloadManager()
            
            # Create job in database
            async with get_async_session() as session:
                job_repo = JobRepository(session)
                
                job = Job(
                    name=job_name or f"Download {len(urls)} videos",
                    job_type="download",
                    priority=JobPriority(priority.upper()),
                    status=JobStatus.PENDING,
                    config={
                        "urls": list(urls),
                        "output_dir": str(output_path),
                        "quality": quality,
                        "format": format,
                        "concurrent": concurrent
                    }
                )
                
                job = await job_repo.create(job)
                job_id = job.id
                
                click.echo(f"📋 Created job: {job_id}")
            
            # Progress callback
            def progress_callback(url_index, progress):
                percentage = int(progress.progress_percent or 0)
                url = urls[url_index]
                click.echo(f"  📥 [{url_index+1}/{len(urls)}] {url}: {percentage}%")
            
            # Download videos
            results = await download_manager.download_batch(
                urls=list(urls),
                output_directory=str(output_path),
                progress_callback=progress_callback,
                quality=quality,
                format=format,
                max_concurrent=concurrent
            )
            
            # Update job status
            async with get_async_session() as session:
                job_repo = JobRepository(session)
                
                successful = sum(1 for r in results if r.get('success'))
                failed = len(results) - successful
                
                if failed == 0:
                    await job_repo.update_status(job_id, JobStatus.COMPLETED)
                    click.echo(f"✅ All {successful} downloads completed successfully!")
                else:
                    await job_repo.update_status(job_id, JobStatus.FAILED)
                    click.echo(f"⚠️  {successful} successful, {failed} failed downloads")
                
                # Show results
                for i, result in enumerate(results):
                    if result.get('success'):
                        click.echo(f"  ✅ {urls[i]} -> {result.get('output_path')}")
                    else:
                        click.echo(f"  ❌ {urls[i]}: {result.get('error')}")
        
        except Exception as exc:
            click.echo(f"❌ Download failed: {exc}", err=True)
            logger.error(f"Download command failed: {exc}", exc_info=True)
            raise click.ClickException(str(exc))
    
    asyncio.run(run_download())


@process_group.command()
@click.argument('input_files', nargs=-1, required=True)
@click.option(
    '--output-dir', '-o',
    type=click.Path(),
    default='./output',
    help='Output directory for processed videos'
)
@click.option(
    '--quality',
    type=click.Choice(['480p', '720p', '1080p', '2160p']),
    default='1080p',
    help='Output video quality'
)
@click.option(
    '--codec',
    type=click.Choice(['h264', 'h265', 'vp9']),
    default='h264',
    help='Video codec'
)
@click.option(
    '--preset',
    type=click.Choice(['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow']),
    default='medium',
    help='Encoding preset (speed vs quality)'
)
@click.option(
    '--use-gpu/--no-gpu',
    default=True,
    help='Use GPU acceleration if available'
)
@click.option(
    '--job-name',
    type=str,
    help='Custom job name'
)
@click.option(
    '--priority',
    type=click.Choice(['low', 'normal', 'high', 'urgent']),
    default='normal',
    help='Job priority'
)
def video(
    input_files: tuple,
    output_dir: str,
    quality: str,
    codec: str,
    preset: str,
    use_gpu: bool,
    job_name: Optional[str],
    priority: str
):
    """Process video files with quality optimization."""
    click.echo(f"🎬 Processing {len(input_files)} video file(s)...")
    
    async def run_processing():
        try:
            # Validate input files
            input_paths = []
            for file_path in input_files:
                path = Path(file_path)
                if not path.exists():
                    raise click.ClickException(f"Input file not found: {file_path}")
                input_paths.append(path)
            
            # Create output directory
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            
            # Initialize hardware manager and processor
            hardware_manager = HardwareManager()
            await hardware_manager.initialize()
            
            processor = VideoProcessor(hardware_manager)
            
            # Create processing configuration
            config = ProcessingConfig(
                video_quality=quality,
                video_codec=codec,
                preset=preset,
                use_gpu=use_gpu,
                use_hardware_accel=use_gpu
            )
            
            # Create job in database
            async with get_async_session() as session:
                job_repo = JobRepository(session)
                
                job = Job(
                    name=job_name or f"Process {len(input_files)} videos",
                    job_type="processing",
                    priority=JobPriority(priority.upper()),
                    status=JobStatus.PENDING,
                    config={
                        "input_files": [str(p) for p in input_paths],
                        "output_dir": str(output_path),
                        "quality": quality,
                        "codec": codec,
                        "preset": preset,
                        "use_gpu": use_gpu
                    }
                )
                
                job = await job_repo.create(job)
                job_id = job.id
                
                click.echo(f"📋 Created job: {job_id}")
            
            # Process each video
            results = []
            for i, input_path in enumerate(input_paths):
                click.echo(f"🎬 Processing [{i+1}/{len(input_paths)}]: {input_path.name}")
                
                output_file = output_path / f"{input_path.stem}_processed{input_path.suffix}"
                
                # Progress callback
                async def progress_callback(progress):
                    percentage = int(progress.progress_percent or 0)
                    click.echo(f"  Progress: {percentage}% (FPS: {progress.fps}, Speed: {progress.speed})")
                
                try:
                    result = await processor.process_video(
                        input_path=input_path,
                        output_path=output_file,
                        config=config,
                        progress_callback=progress_callback
                    )
                    
                    results.append({
                        'success': True,
                        'input_path': str(input_path),
                        'output_path': str(result.output_path),
                        'file_size': result.file_size,
                        'duration': result.duration
                    })
                    
                    click.echo(f"  ✅ Completed: {result.output_path}")
                    
                except Exception as exc:
                    results.append({
                        'success': False,
                        'input_path': str(input_path),
                        'error': str(exc)
                    })
                    click.echo(f"  ❌ Failed: {exc}")
            
            # Update job status
            async with get_async_session() as session:
                job_repo = JobRepository(session)
                
                successful = sum(1 for r in results if r.get('success'))
                failed = len(results) - successful
                
                if failed == 0:
                    await job_repo.update_status(job_id, JobStatus.COMPLETED)
                    click.echo(f"✅ All {successful} videos processed successfully!")
                else:
                    await job_repo.update_status(job_id, JobStatus.FAILED)
                    click.echo(f"⚠️  {successful} successful, {failed} failed processing")
        
        except Exception as exc:
            click.echo(f"❌ Processing failed: {exc}", err=True)
            logger.error(f"Processing command failed: {exc}", exc_info=True)
            raise click.ClickException(str(exc))
    
    asyncio.run(run_processing())


@process_group.command()
@click.argument('input_files', nargs=-1, required=True)
@click.option(
    '--output', '-o',
    type=click.Path(),
    required=True,
    help='Output file path for merged video'
)
@click.option(
    '--quality',
    type=click.Choice(['480p', '720p', '1080p', '2160p']),
    default='1080p',
    help='Output video quality'
)
@click.option(
    '--create-chapters/--no-chapters',
    default=True,
    help='Create chapter markers for each input file'
)
@click.option(
    '--chapter-template',
    type=str,
    default='Episode {episode}',
    help='Chapter title template'
)
@click.option(
    '--use-gpu/--no-gpu',
    default=True,
    help='Use GPU acceleration if available'
)
@click.option(
    '--job-name',
    type=str,
    help='Custom job name'
)
def merge(
    input_files: tuple,
    output: str,
    quality: str,
    create_chapters: bool,
    chapter_template: str,
    use_gpu: bool,
    job_name: Optional[str]
):
    """Merge multiple video files into one."""
    click.echo(f"🔗 Merging {len(input_files)} video file(s)...")
    
    async def run_merge():
        try:
            # Validate input files
            input_paths = []
            for file_path in input_files:
                path = Path(file_path)
                if not path.exists():
                    raise click.ClickException(f"Input file not found: {file_path}")
                input_paths.append(path)
            
            # Create output directory
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Initialize hardware manager and merger
            hardware_manager = HardwareManager()
            await hardware_manager.initialize()
            
            merger = VideoMerger(hardware_manager)
            
            # Create merge configuration
            config = MergeConfig(
                output_quality=quality,
                use_gpu=use_gpu,
                use_hardware_accel=use_gpu,
                create_chapters=create_chapters,
                chapter_title_template=chapter_template
            )
            
            # Create job in database
            async with get_async_session() as session:
                job_repo = JobRepository(session)
                
                job = Job(
                    name=job_name or f"Merge {len(input_files)} videos",
                    job_type="merge",
                    priority=JobPriority.NORMAL,
                    status=JobStatus.PENDING,
                    config={
                        "input_files": [str(p) for p in input_paths],
                        "output_file": str(output_path),
                        "quality": quality,
                        "create_chapters": create_chapters,
                        "use_gpu": use_gpu
                    }
                )
                
                job = await job_repo.create(job)
                job_id = job.id
                
                click.echo(f"📋 Created job: {job_id}")
            
            # Progress callback
            async def progress_callback(stage, percentage, details):
                click.echo(f"  {stage}: {percentage}%")
            
            # Merge videos
            if create_chapters:
                # Prepare files with chapter info
                prepared_files = []
                for i, path in enumerate(input_paths):
                    prepared_files.append({
                        "path": path,
                        "title": chapter_template.format(episode=i+1),
                        "episode_number": i+1
                    })
                
                result = await merger.merge_with_chapters(
                    input_files=prepared_files,
                    output_path=output_path,
                    config=config,
                    progress_callback=progress_callback
                )
            else:
                result = await merger.merge_videos(
                    input_files=input_paths,
                    output_path=output_path,
                    config=config,
                    progress_callback=progress_callback
                )
            
            # Update job status
            async with get_async_session() as session:
                job_repo = JobRepository(session)
                await job_repo.update_status(job_id, JobStatus.COMPLETED)
            
            click.echo(f"✅ Merge completed: {result.output_path}")
            click.echo(f"   File size: {result.file_size / (1024*1024):.1f} MB")
            click.echo(f"   Duration: {result.total_duration:.1f} seconds")
            
            if result.chapters:
                click.echo(f"   Chapters: {len(result.chapters)}")
        
        except Exception as exc:
            click.echo(f"❌ Merge failed: {exc}", err=True)
            logger.error(f"Merge command failed: {exc}", exc_info=True)
            raise click.ClickException(str(exc))
    
    asyncio.run(run_merge())


@process_group.command()
@click.argument('urls', nargs=-1, required=True)
@click.option(
    '--output-dir', '-o',
    type=click.Path(),
    default='./output',
    help='Output directory'
)
@click.option(
    '--quality',
    type=click.Choice(['480p', '720p', '1080p', '2160p']),
    default='1080p',
    help='Video quality'
)
@click.option(
    '--merge-output',
    type=click.Path(),
    help='Path for final merged video (optional)'
)
@click.option(
    '--create-chapters/--no-chapters',
    default=True,
    help='Create chapter markers when merging'
)
@click.option(
    '--use-gpu/--no-gpu',
    default=True,
    help='Use GPU acceleration'
)
@click.option(
    '--job-name',
    type=str,
    help='Custom job name'
)
@click.option(
    '--priority',
    type=click.Choice(['low', 'normal', 'high', 'urgent']),
    default='normal',
    help='Job priority'
)
def complete(
    urls: tuple,
    output_dir: str,
    quality: str,
    merge_output: Optional[str],
    create_chapters: bool,
    use_gpu: bool,
    job_name: Optional[str],
    priority: str
):
    """Complete workflow: download, process, and optionally merge videos."""
    click.echo(f"🚀 Starting complete workflow for {len(urls)} video(s)...")
    
    async def run_complete_workflow():
        try:
            # Create output directory
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            
            # Create job manager and execution plan
            job_manager = JobManager()
            
            stages = [JobStage.DOWNLOAD, JobStage.PROCESS]
            if merge_output:
                stages.append(JobStage.MERGE)
            
            # Create job in database first
            async with get_async_session() as session:
                job_repo = JobRepository(session)
                
                job = Job(
                    name=job_name or f"Complete workflow: {len(urls)} videos",
                    job_type="complete_workflow",
                    priority=JobPriority(priority.upper()),
                    status=JobStatus.PENDING,
                    config={
                        "urls": list(urls),
                        "output_dir": str(output_path),
                        "quality": quality,
                        "merge_output": merge_output,
                        "create_chapters": create_chapters,
                        "use_gpu": use_gpu
                    }
                )
                
                job = await job_repo.create(job)
                job_id = job.id
                
                click.echo(f"📋 Created workflow job: {job_id}")
            
            # Create execution plan
            execution_plan = JobExecutionPlan(
                job_id=job_id,
                stages=stages,
                task_configs={
                    JobStage.DOWNLOAD: {
                        "video_urls": list(urls),
                        "output_directory": str(output_path),
                        "download_options": {"quality": quality}
                    },
                    JobStage.PROCESS: {
                        "batch_processing": True,
                        "processing_config": {
                            "video_quality": quality,
                            "use_gpu": use_gpu
                        }
                    },
                    JobStage.MERGE: {
                        "output_path": merge_output,
                        "with_chapters": create_chapters,
                        "chapter_config": {
                            "output_quality": quality,
                            "use_gpu": use_gpu
                        }
                    } if merge_output else {}
                },
                priority=JobPriority(priority.upper()),
                resource_requirements={"gpu": use_gpu}
            )
            
            # Submit job
            result = await job_manager.submit_job(job_id, execution_plan)
            
            if result["success"]:
                click.echo(f"✅ Workflow submitted successfully!")
                click.echo(f"   Job ID: {job_id}")
                click.echo(f"   Task ID: {result['task_id']}")
                click.echo(f"   Stages: {' -> '.join(result['stages'])}")
                click.echo("\n💡 Use 'video-processor jobs status <job_id>' to monitor progress")
            else:
                click.echo(f"❌ Failed to submit workflow: {result.get('error')}")
        
        except Exception as exc:
            click.echo(f"❌ Complete workflow failed: {exc}", err=True)
            logger.error(f"Complete workflow command failed: {exc}", exc_info=True)
            raise click.ClickException(str(exc))
    
    asyncio.run(run_complete_workflow())