"""
Job management CLI commands.
"""

import click
import asyncio
import json
from typing import Optional
from datetime import datetime, timedelta
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel

from ...config.logging_config import get_logger
from ...database.connection import get_async_session
from ...database.repositories.job_repo import JobRepository
from ...database.models.job import JobStatus, JobPriority
from ...workers.job_manager import job_manager

logger = get_logger(__name__)
console = Console()


@click.group(name='jobs')
def jobs_group():
    """Job management commands."""
    pass


@jobs_group.command()
@click.option(
    '--status',
    type=click.Choice(['pending', 'processing', 'completed', 'failed', 'cancelled']),
    help='Filter by job status'
)
@click.option(
    '--job-type',
    type=click.Choice(['download', 'processing', 'merge', 'complete_workflow']),
    help='Filter by job type'
)
@click.option(
    '--limit', '-l',
    type=int,
    default=20,
    help='Maximum number of jobs to show'
)
@click.option(
    '--json-output',
    is_flag=True,
    help='Output in JSON format'
)
def list(status: Optional[str], job_type: Optional[str], limit: int, json_output: bool):
    """List jobs with optional filtering."""
    
    async def run_list():
        try:
            async with get_async_session() as session:
                job_repo = JobRepository(session)
                
                # Get jobs with filters
                jobs = await job_repo.get_jobs(
                    status=JobStatus(status.upper()) if status else None,
                    job_type=job_type,
                    limit=limit
                )
                
                if json_output:
                    # JSON output
                    jobs_data = []
                    for job in jobs:
                        jobs_data.append({
                            "id": job.id,
                            "name": job.name,
                            "job_type": job.job_type,
                            "status": job.status.value,
                            "priority": job.priority.value,
                            "progress_percentage": job.progress_percentage,
                            "created_at": job.created_at.isoformat() if job.created_at else None,
                            "started_at": job.started_at.isoformat() if job.started_at else None,
                            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                            "error_count": job.error_count
                        })
                    
                    click.echo(json.dumps(jobs_data, indent=2))
                else:
                    # Rich table output
                    if not jobs:
                        console.print("📭 No jobs found matching the criteria.")
                        return
                    
                    table = Table(title=f"Jobs ({len(jobs)} found)")
                    table.add_column("ID", style="cyan", no_wrap=True)
                    table.add_column("Name", style="white")
                    table.add_column("Type", style="blue")
                    table.add_column("Status", style="green")
                    table.add_column("Priority", style="yellow")
                    table.add_column("Progress", style="magenta")
                    table.add_column("Created", style="dim")
                    
                    for job in jobs:
                        # Status styling
                        status_style = {
                            'completed': '[green]✅ Completed[/green]',
                            'processing': '[yellow]⚡ Processing[/yellow]',
                            'pending': '[blue]⏳ Pending[/blue]',
                            'failed': '[red]❌ Failed[/red]',
                            'cancelled': '[dim]🚫 Cancelled[/dim]'
                        }.get(job.status.value, job.status.value)
                        
                        # Priority styling
                        priority_style = {
                            'urgent': '[red]🔥 Urgent[/red]',
                            'high': '[orange]⬆️ High[/orange]',
                            'normal': '[white]➡️ Normal[/white]',
                            'low': '[dim]⬇️ Low[/dim]'
                        }.get(job.priority.value, job.priority.value)
                        
                        progress = f"{job.progress_percentage}%" if job.progress_percentage else "0%"
                        created = job.created_at.strftime("%m/%d %H:%M") if job.created_at else "Unknown"
                        
                        table.add_row(
                            job.id[:8],
                            job.name[:30] + "..." if len(job.name) > 30 else job.name,
                            job.job_type,
                            status_style,
                            priority_style,
                            progress,
                            created
                        )
                    
                    console.print(table)
        
        except Exception as exc:
            click.echo(f"❌ Failed to list jobs: {exc}", err=True)
            logger.error(f"List jobs command failed: {exc}", exc_info=True)
            raise click.ClickException(str(exc))
    
    asyncio.run(run_list())


@jobs_group.command()
@click.argument('job_id')
@click.option(
    '--json-output',
    is_flag=True,
    help='Output in JSON format'
)
@click.option(
    '--follow', '-f',
    is_flag=True,
    help='Follow job progress in real-time'
)
def status(job_id: str, json_output: bool, follow: bool):
    """Show detailed job status."""
    
    async def run_status():
        try:
            if follow:
                # Real-time following
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console
                ) as progress:
                    task = progress.add_task("Monitoring job...", total=None)
                    
                    while True:
                        try:
                            # Get job status from job manager
                            job_status = await job_manager.get_job_status(job_id)
                            
                            # Update progress description
                            status_text = f"Job {job_id[:8]}: {job_status['status']} ({job_status['progress_percentage']}%)"
                            progress.update(task, description=status_text)
                            
                            # Check if job is complete
                            if job_status['status'] in ['completed', 'failed', 'cancelled']:
                                break
                            
                            await asyncio.sleep(2)  # Update every 2 seconds
                            
                        except KeyboardInterrupt:
                            console.print("\n⚠️  Monitoring stopped by user")
                            break
                        except Exception as exc:
                            console.print(f"\n❌ Error monitoring job: {exc}")
                            break
                
                # Show final status
                await show_job_status(job_id, json_output)
            else:
                # Single status check
                await show_job_status(job_id, json_output)
        
        except Exception as exc:
            click.echo(f"❌ Failed to get job status: {exc}", err=True)
            logger.error(f"Job status command failed: {exc}", exc_info=True)
            raise click.ClickException(str(exc))
    
    asyncio.run(run_status())


async def show_job_status(job_id: str, json_output: bool):
    """Show job status details."""
    try:
        # Get job status from job manager (includes task info)
        job_status = await job_manager.get_job_status(job_id)
        
        if json_output:
            click.echo(json.dumps(job_status, indent=2, default=str))
        else:
            # Rich formatted output
            status_color = {
                'completed': 'green',
                'processing': 'yellow',
                'pending': 'blue',
                'failed': 'red',
                'cancelled': 'dim'
            }.get(job_status['status'], 'white')
            
            # Create status panel
            status_content = f"""
[bold]Job ID:[/bold] {job_status['job_id']}
[bold]Status:[/bold] [{status_color}]{job_status['status'].upper()}[/{status_color}]
[bold]Progress:[/bold] {job_status['progress_percentage']}%
[bold]Current Stage:[/bold] {job_status.get('current_stage', 'N/A')}
[bold]Created:[/bold] {job_status.get('created_at', 'Unknown')}
[bold]Started:[/bold] {job_status.get('started_at', 'Not started')}
[bold]Completed:[/bold] {job_status.get('completed_at', 'Not completed')}
[bold]Errors:[/bold] {job_status.get('error_count', 0)}
            """.strip()
            
            console.print(Panel(status_content, title="Job Status", border_style=status_color))
            
            # Show task status if available
            if job_status.get('task_status'):
                task_status = job_status['task_status']
                task_content = f"""
[bold]Task ID:[/bold] {task_status['task_id']}
[bold]State:[/bold] {task_status['state']}
[bold]Ready:[/bold] {task_status['ready']}
[bold]Successful:[/bold] {task_status.get('successful', 'N/A')}
[bold]Failed:[/bold] {task_status.get('failed', 'N/A')}
                """.strip()
                
                if task_status.get('error'):
                    task_content += f"\n[bold red]Error:[/bold red] {task_status['error']}"
                
                console.print(Panel(task_content, title="Task Status", border_style="blue"))
            
            # Show recent errors if any
            if job_status.get('errors'):
                console.print("\n[bold red]Recent Errors:[/bold red]")
                for error in job_status['errors']:
                    console.print(f"  • {error}")
    
    except Exception as exc:
        # Fallback to database-only status
        async with get_async_session() as session:
            job_repo = JobRepository(session)
            job = await job_repo.get(job_id)
            
            if not job:
                raise click.ClickException(f"Job {job_id} not found")
            
            if json_output:
                job_data = {
                    "id": job.id,
                    "name": job.name,
                    "job_type": job.job_type,
                    "status": job.status.value,
                    "priority": job.priority.value,
                    "progress_percentage": job.progress_percentage,
                    "current_stage": job.current_stage,
                    "created_at": job.created_at.isoformat() if job.created_at else None,
                    "started_at": job.started_at.isoformat() if job.started_at else None,
                    "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                    "error_count": job.error_count,
                    "errors": job.errors[-5:] if job.errors else []
                }
                click.echo(json.dumps(job_data, indent=2))
            else:
                console.print(f"[yellow]⚠️  Using database status (job manager unavailable)[/yellow]")
                console.print(f"Job {job.id}: {job.status.value} ({job.progress_percentage}%)")


@jobs_group.command()
@click.argument('job_id')
@click.confirmation_option(prompt='Are you sure you want to cancel this job?')
def cancel(job_id: str):
    """Cancel a running job."""
    
    async def run_cancel():
        try:
            result = await job_manager.cancel_job(job_id)
            
            if result["success"]:
                console.print(f"✅ Job {job_id} cancelled successfully")
            else:
                console.print(f"❌ Failed to cancel job: {result.get('error')}")
        
        except Exception as exc:
            click.echo(f"❌ Failed to cancel job: {exc}", err=True)
            logger.error(f"Cancel job command failed: {exc}", exc_info=True)
            raise click.ClickException(str(exc))
    
    asyncio.run(run_cancel())


@jobs_group.command()
@click.argument('job_id')
@click.option(
    '--priority',
    type=click.Choice(['low', 'normal', 'high', 'urgent']),
    help='New priority for retry'
)
def retry(job_id: str, priority: Optional[str]):
    """Retry a failed job."""
    
    async def run_retry():
        try:
            retry_config = {}
            if priority:
                retry_config['priority'] = priority
            
            result = await job_manager.retry_job(job_id, retry_config)
            
            if result["success"]:
                console.print(f"✅ Job {job_id} queued for retry")
                console.print(f"   New Task ID: {result['task_id']}")
            else:
                console.print(f"❌ Failed to retry job: {result.get('error')}")
        
        except Exception as exc:
            click.echo(f"❌ Failed to retry job: {exc}", err=True)
            logger.error(f"Retry job command failed: {exc}", exc_info=True)
            raise click.ClickException(str(exc))
    
    asyncio.run(run_retry())


@jobs_group.command()
@click.option(
    '--days',
    type=int,
    default=7,
    help='Delete jobs older than N days'
)
@click.option(
    '--status',
    type=click.Choice(['completed', 'failed', 'cancelled']),
    multiple=True,
    default=['completed', 'failed', 'cancelled'],
    help='Job statuses to clean up'
)
@click.option(
    '--dry-run',
    is_flag=True,
    help='Show what would be deleted without actually deleting'
)
@click.confirmation_option(prompt='Are you sure you want to clean up old jobs?')
def cleanup(days: int, status: tuple, dry_run: bool):
    """Clean up old completed/failed jobs."""
    
    async def run_cleanup():
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            async with get_async_session() as session:
                job_repo = JobRepository(session)
                
                # Find jobs to delete
                jobs_to_delete = []
                for status_filter in status:
                    jobs = await job_repo.get_jobs_before_date(
                        cutoff_date,
                        status=JobStatus(status_filter.upper())
                    )
                    jobs_to_delete.extend(jobs)
                
                if not jobs_to_delete:
                    console.print("📭 No jobs found matching cleanup criteria")
                    return
                
                if dry_run:
                    console.print(f"🔍 Would delete {len(jobs_to_delete)} jobs:")
                    for job in jobs_to_delete[:10]:  # Show first 10
                        console.print(f"  • {job.id} - {job.name} ({job.status.value})")
                    if len(jobs_to_delete) > 10:
                        console.print(f"  ... and {len(jobs_to_delete) - 10} more")
                else:
                    # Actually delete jobs
                    deleted_count = 0
                    for job in jobs_to_delete:
                        await job_repo.delete(job.id)
                        deleted_count += 1
                    
                    console.print(f"✅ Deleted {deleted_count} old jobs")
        
        except Exception as exc:
            click.echo(f"❌ Failed to cleanup jobs: {exc}", err=True)
            logger.error(f"Cleanup jobs command failed: {exc}", exc_info=True)
            raise click.ClickException(str(exc))
    
    asyncio.run(run_cleanup())


@jobs_group.command()
def active():
    """Show currently active jobs."""
    
    async def run_active():
        try:
            active_jobs = await job_manager.get_active_jobs()
            
            if not active_jobs:
                console.print("📭 No active jobs found")
                return
            
            table = Table(title=f"Active Jobs ({len(active_jobs)})")
            table.add_column("ID", style="cyan", no_wrap=True)
            table.add_column("Name", style="white")
            table.add_column("Status", style="green")
            table.add_column("Progress", style="magenta")
            table.add_column("Stage", style="blue")
            table.add_column("Started", style="dim")
            
            for job in active_jobs:
                progress = f"{job['progress_percentage']}%" if job['progress_percentage'] else "0%"
                started = job.get('started_at', 'Unknown')
                if started != 'Unknown' and started:
                    started = datetime.fromisoformat(started.replace('Z', '+00:00')).strftime("%H:%M:%S")
                
                table.add_row(
                    job['job_id'][:8],
                    job.get('name', 'Unknown')[:25],
                    job['status'],
                    progress,
                    job.get('current_stage', 'N/A'),
                    started
                )
            
            console.print(table)
        
        except Exception as exc:
            click.echo(f"❌ Failed to get active jobs: {exc}", err=True)
            logger.error(f"Active jobs command failed: {exc}", exc_info=True)
            raise click.ClickException(str(exc))
    
    asyncio.run(run_active())