"""
Worker management CLI commands.
"""

import click
import subprocess
import signal
import sys
import time
from typing import Optional, List

from ...config import settings
from ...config.logging_config import get_logger

logger = get_logger(__name__)


@click.group(name='worker')
def worker_group():
    """Worker management commands."""
    pass


@worker_group.command()
@click.option(
    '--queues', '-q',
    multiple=True,
    default=['processing', 'download', 'merge'],
    help='Queues to process (can specify multiple)'
)
@click.option(
    '--concurrency', '-c',
    type=int,
    default=4,
    help='Number of concurrent tasks'
)
@click.option(
    '--loglevel',
    type=click.Choice(['debug', 'info', 'warning', 'error']),
    default='info',
    help='Log level'
)
@click.option(
    '--hostname',
    type=str,
    help='Custom hostname for worker'
)
@click.option(
    '--autoscale',
    type=str,
    help='Autoscale settings (e.g., "10,3" for max 10, min 3)'
)
@click.option(
    '--max-tasks-per-child',
    type=int,
    default=1000,
    help='Max tasks per worker child process'
)
def start(
    queues: tuple,
    concurrency: int,
    loglevel: str,
    hostname: Optional[str],
    autoscale: Optional[str],
    max_tasks_per_child: int
):
    """Start Celery workers."""
    click.echo(f"🔧 Starting Celery workers for queues: {', '.join(queues)}")
    
    try:
        # Build celery command
        cmd = [
            "celery",
            "-A", "src.celery_app.app",
            "worker",
            "--queues", ",".join(queues),
            "--loglevel", loglevel,
            "--max-tasks-per-child", str(max_tasks_per_child)
        ]
        
        if autoscale:
            cmd.extend(["--autoscale", autoscale])
        else:
            cmd.extend(["--concurrency", str(concurrency)])
        
        if hostname:
            cmd.extend(["--hostname", hostname])
        
        # Handle graceful shutdown
        def signal_handler(signum, frame):
            click.echo("\n⚠️  Shutting down workers...")
            # Celery will handle graceful shutdown
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        click.echo("🚀 Workers started. Press Ctrl+C to stop")
        
        # Start workers
        subprocess.run(cmd, check=True)
        
    except FileNotFoundError:
        click.echo("❌ celery not installed or not in PATH", err=True)
        sys.exit(1)
    except subprocess.CalledProcessError as exc:
        click.echo(f"❌ Failed to start workers: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:
        click.echo(f"❌ Worker error: {exc}", err=True)
        logger.error(f"Worker start failed: {exc}", exc_info=True)
        sys.exit(1)


@worker_group.command()
@click.option(
    '--timeout',
    type=int,
    default=30,
    help='Shutdown timeout in seconds'
)
def stop(timeout: int):
    """Stop all Celery workers."""
    click.echo("🛑 Stopping Celery workers...")
    
    try:
        import psutil
        
        workers_found = False
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info['cmdline']
                if cmdline and any('celery' in arg and 'worker' in ' '.join(cmdline) for arg in cmdline):
                    workers_found = True
                    click.echo(f"🔍 Found worker process: {proc.info['pid']}")
                    
                    # Send TERM signal for graceful shutdown
                    proc.terminate()
                    
                    try:
                        proc.wait(timeout=timeout)
                        click.echo(f"✅ Worker {proc.info['pid']} stopped gracefully")
                    except psutil.TimeoutExpired:
                        click.echo(f"⚠️  Force stopping worker {proc.info['pid']}")
                        proc.kill()
                        click.echo(f"✅ Worker {proc.info['pid']} force stopped")
                        
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        if not workers_found:
            click.echo("❌ No running workers found")
        else:
            click.echo("✅ All workers stopped")
            
    except ImportError:
        click.echo("❌ psutil not installed. Cannot find worker processes.", err=True)
        
        # Fallback: try celery control
        try:
            subprocess.run([
                "celery", "-A", "src.celery_app.app", "control", "shutdown"
            ], check=True, timeout=timeout)
            click.echo("✅ Workers stopped via celery control")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            click.echo("❌ Failed to stop workers", err=True)
            
    except Exception as exc:
        click.echo(f"❌ Failed to stop workers: {exc}", err=True)
        logger.error(f"Worker stop failed: {exc}", exc_info=True)


@worker_group.command()
def status():
    """Show worker status."""
    click.echo("🔍 Checking worker status...")
    
    try:
        # Use celery inspect
        result = subprocess.run([
            "celery", "-A", "src.celery_app.app", "inspect", "active"
        ], capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            output = result.stdout.strip()
            if output and "Empty" not in output:
                click.echo("✅ Workers are running:")
                click.echo(output)
            else:
                click.echo("📭 No active workers found")
        else:
            click.echo("❌ Failed to get worker status")
            if result.stderr:
                click.echo(f"Error: {result.stderr}")
                
    except subprocess.TimeoutExpired:
        click.echo("❌ Worker status check timed out")
    except FileNotFoundError:
        click.echo("❌ celery not installed or not in PATH", err=True)
    except Exception as exc:
        click.echo(f"❌ Failed to check worker status: {exc}", err=True)
        logger.error(f"Worker status check failed: {exc}", exc_info=True)


@worker_group.command()
def stats():
    """Show detailed worker statistics."""
    click.echo("📊 Getting worker statistics...")
    
    try:
        # Get worker stats
        result = subprocess.run([
            "celery", "-A", "src.celery_app.app", "inspect", "stats"
        ], capture_output=True, text=True, timeout=15)
        
        if result.returncode == 0:
            click.echo(result.stdout)
        else:
            click.echo("❌ Failed to get worker statistics")
            if result.stderr:
                click.echo(f"Error: {result.stderr}")
                
    except subprocess.TimeoutExpired:
        click.echo("❌ Worker stats check timed out")
    except FileNotFoundError:
        click.echo("❌ celery not installed or not in PATH", err=True)
    except Exception as exc:
        click.echo(f"❌ Failed to get worker stats: {exc}", err=True)


@worker_group.command()
@click.option(
    '--timeout',
    type=int,
    default=30,
    help='Restart timeout'
)
def restart(timeout: int):
    """Restart all workers."""
    click.echo("🔄 Restarting workers...")
    
    # Stop workers
    ctx = click.get_current_context()
    ctx.invoke(stop, timeout=timeout)
    
    # Wait a moment
    time.sleep(2)
    
    # Start workers with default settings
    ctx.invoke(start)


@worker_group.command()
@click.argument('worker_name')
def purge(worker_name: str):
    """Purge tasks from a specific worker."""
    click.echo(f"🧹 Purging tasks from worker: {worker_name}")
    
    try:
        result = subprocess.run([
            "celery", "-A", "src.celery_app.app", "purge", "-f"
        ], capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            click.echo("✅ Tasks purged successfully")
        else:
            click.echo("❌ Failed to purge tasks")
            if result.stderr:
                click.echo(f"Error: {result.stderr}")
                
    except subprocess.TimeoutExpired:
        click.echo("❌ Purge operation timed out")
    except FileNotFoundError:
        click.echo("❌ celery not installed or not in PATH", err=True)
    except Exception as exc:
        click.echo(f"❌ Failed to purge tasks: {exc}", err=True)


@worker_group.command()
def monitor():
    """Start Celery monitoring (flower)."""
    click.echo("🌸 Starting Celery monitoring (Flower)...")
    
    try:
        cmd = [
            "celery", "-A", "src.celery_app.app", "flower",
            "--port=5555",
            "--broker", settings.REDIS_URL
        ]
        
        click.echo("🚀 Flower monitoring started at http://localhost:5555")
        click.echo("Press Ctrl+C to stop")
        
        subprocess.run(cmd, check=True)
        
    except FileNotFoundError:
        click.echo("❌ flower not installed. Install with: pip install flower", err=True)
        sys.exit(1)
    except subprocess.CalledProcessError as exc:
        click.echo(f"❌ Failed to start monitoring: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:
        click.echo(f"❌ Monitoring error: {exc}", err=True)
        logger.error(f"Worker monitoring failed: {exc}", exc_info=True)
        sys.exit(1)


@worker_group.command()
@click.option(
    '--queue',
    type=str,
    help='Specific queue to inspect'
)
def inspect(queue: Optional[str]):
    """Inspect worker queues and tasks."""
    click.echo("🔍 Inspecting workers...")
    
    commands = [
        ("Active tasks", ["celery", "-A", "src.celery_app.app", "inspect", "active"]),
        ("Scheduled tasks", ["celery", "-A", "src.celery_app.app", "inspect", "scheduled"]),
        ("Reserved tasks", ["celery", "-A", "src.celery_app.app", "inspect", "reserved"]),
    ]
    
    if queue:
        click.echo(f"Focusing on queue: {queue}")
    
    for title, cmd in commands:
        try:
            click.echo(f"\n📋 {title}:")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                output = result.stdout.strip()
                if output and "Empty" not in output:
                    # Filter by queue if specified
                    if queue:
                        lines = output.split('\n')
                        filtered_lines = [line for line in lines if queue in line or not any(q in line for q in ['processing', 'download', 'merge'] if q != queue)]
                        output = '\n'.join(filtered_lines)
                    
                    click.echo(output)
                else:
                    click.echo("  (Empty)")
            else:
                click.echo(f"  ❌ Failed to get {title.lower()}")
                
        except subprocess.TimeoutExpired:
            click.echo(f"  ❌ {title} check timed out")
        except Exception as exc:
            click.echo(f"  ❌ Error getting {title.lower()}: {exc}")


@worker_group.command()
@click.option(
    '--workers', '-w',
    type=int,
    default=2,
    help='Number of worker processes to start'
)
@click.option(
    '--beat',
    is_flag=True,
    help='Also start beat scheduler'
)
def multi(workers: int, beat: bool):
    """Start multiple workers with different configurations."""
    click.echo(f"🚀 Starting {workers} worker processes...")
    
    try:
        # Start processing workers
        for i in range(workers):
            hostname = f"worker{i+1}@%h"
            
            if i == 0:
                # First worker handles all queues
                queues = "processing,download,merge,notifications"
            elif i == 1:
                # Second worker focuses on processing
                queues = "processing"
            else:
                # Additional workers handle download and merge
                queues = "download,merge"
            
            click.echo(f"Starting worker {i+1} with queues: {queues}")
            
            # This would typically be done with a process manager like supervisor
            # For now, we'll show the command that would be run
            cmd = [
                "celery", "-A", "src.celery_app.app", "worker",
                "--hostname", hostname,
                "--queues", queues,
                "--concurrency", "4",
                "--loglevel", "info"
            ]
            
            click.echo(f"Command: {' '.join(cmd)}")
        
        if beat:
            click.echo("Starting beat scheduler...")
            beat_cmd = ["celery", "-A", "src.celery_app.app", "beat", "--loglevel", "info"]
            click.echo(f"Beat command: {' '.join(beat_cmd)}")
        
        click.echo("\n💡 For production, use a process manager like supervisor or systemd")
        click.echo("   Example supervisor config files can be generated with:")
        click.echo("   video-processor config generate-supervisor")
        
    except Exception as exc:
        click.echo(f"❌ Multi-worker setup error: {exc}", err=True)
        logger.error(f"Multi-worker setup failed: {exc}", exc_info=True)