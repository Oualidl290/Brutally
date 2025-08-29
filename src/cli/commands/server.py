"""
Server management CLI commands.
"""

import click
import asyncio
import subprocess
import signal
import sys
import time
from pathlib import Path
from typing import Optional

from ...config import settings
from ...config.logging_config import get_logger

logger = get_logger(__name__)


@click.group(name='server')
def server_group():
    """Server management commands."""
    pass


@server_group.command()
@click.option(
    '--host',
    default=settings.API_HOST,
    help=f'Host to bind to (default: {settings.API_HOST})'
)
@click.option(
    '--port',
    type=int,
    default=settings.API_PORT,
    help=f'Port to bind to (default: {settings.API_PORT})'
)
@click.option(
    '--workers',
    type=int,
    default=1,
    help='Number of worker processes'
)
@click.option(
    '--reload',
    is_flag=True,
    help='Enable auto-reload for development'
)
@click.option(
    '--log-level',
    type=click.Choice(['debug', 'info', 'warning', 'error']),
    default='info',
    help='Log level'
)
def start(host: str, port: int, workers: int, reload: bool, log_level: str):
    """Start the API server."""
    click.echo(f"🚀 Starting API server on {host}:{port}")
    
    try:
        import uvicorn
        
        # Configure uvicorn
        config = uvicorn.Config(
            app="src.api.main:app",
            host=host,
            port=port,
            workers=workers if not reload else 1,  # Reload doesn't work with multiple workers
            reload=reload,
            log_level=log_level,
            access_log=True,
            server_header=False,
            date_header=False
        )
        
        server = uvicorn.Server(config)
        
        # Handle graceful shutdown
        def signal_handler(signum, frame):
            click.echo("\n⚠️  Shutting down server...")
            server.should_exit = True
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Start server
        click.echo(f"📡 Server running at http://{host}:{port}")
        click.echo(f"📚 API docs available at http://{host}:{port}/docs")
        click.echo("Press Ctrl+C to stop")
        
        server.run()
        
    except ImportError:
        click.echo("❌ uvicorn not installed. Install with: pip install uvicorn[standard]", err=True)
        sys.exit(1)
    except Exception as exc:
        click.echo(f"❌ Failed to start server: {exc}", err=True)
        logger.error(f"Server start failed: {exc}", exc_info=True)
        sys.exit(1)


@server_group.command()
@click.option(
    '--host',
    default=settings.API_HOST,
    help='Server host'
)
@click.option(
    '--port',
    type=int,
    default=settings.API_PORT,
    help='Server port'
)
@click.option(
    '--timeout',
    type=int,
    default=30,
    help='Timeout in seconds'
)
def stop(host: str, port: int, timeout: int):
    """Stop the API server."""
    click.echo(f"🛑 Stopping API server on {host}:{port}")
    
    try:
        import requests
        
        # Try graceful shutdown via API
        try:
            response = requests.post(
                f"http://{host}:{port}/admin/shutdown",
                timeout=5
            )
            if response.status_code == 200:
                click.echo("✅ Server stopped gracefully")
                return
        except requests.exceptions.RequestException:
            pass
        
        # Fallback: find and kill process
        try:
            import psutil
            
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = proc.info['cmdline']
                    if cmdline and any('uvicorn' in arg for arg in cmdline) and str(port) in ' '.join(cmdline):
                        click.echo(f"🔍 Found server process: {proc.info['pid']}")
                        proc.terminate()
                        
                        # Wait for graceful termination
                        try:
                            proc.wait(timeout=timeout)
                            click.echo("✅ Server stopped")
                            return
                        except psutil.TimeoutExpired:
                            click.echo("⚠️  Forcing server shutdown...")
                            proc.kill()
                            click.echo("✅ Server force stopped")
                            return
                            
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            click.echo("❌ No running server found")
            
        except ImportError:
            click.echo("❌ psutil not installed. Cannot find server process.", err=True)
            
    except Exception as exc:
        click.echo(f"❌ Failed to stop server: {exc}", err=True)
        logger.error(f"Server stop failed: {exc}", exc_info=True)


@server_group.command()
@click.option(
    '--host',
    default=settings.API_HOST,
    help='Server host'
)
@click.option(
    '--port',
    type=int,
    default=settings.API_PORT,
    help='Server port'
)
def status(host: str, port: int):
    """Check server status."""
    click.echo(f"🔍 Checking server status at {host}:{port}")
    
    try:
        import requests
        
        # Check health endpoint
        try:
            response = requests.get(
                f"http://{host}:{port}/health",
                timeout=10
            )
            
            if response.status_code == 200:
                health_data = response.json()
                status = health_data.get('status', 'unknown')
                
                if status == 'healthy':
                    click.echo("✅ Server is running and healthy")
                elif status == 'degraded':
                    click.echo("⚠️  Server is running but degraded")
                else:
                    click.echo("❌ Server is running but unhealthy")
                
                # Show additional info
                if 'version' in health_data:
                    click.echo(f"   Version: {health_data['version']}")
                if 'uptime' in health_data:
                    uptime = int(health_data['uptime'])
                    hours, remainder = divmod(uptime, 3600)
                    minutes, seconds = divmod(remainder, 60)
                    click.echo(f"   Uptime: {hours:02d}:{minutes:02d}:{seconds:02d}")
                
                # Show check summary
                if 'summary' in health_data:
                    summary = health_data['summary']
                    total = summary.get('total_checks', 0)
                    healthy = summary.get('status_counts', {}).get('healthy', 0)
                    click.echo(f"   Health checks: {healthy}/{total} passing")
                
            else:
                click.echo(f"❌ Server responded with status {response.status_code}")
                
        except requests.exceptions.ConnectionError:
            click.echo("❌ Server is not running or not accessible")
        except requests.exceptions.Timeout:
            click.echo("❌ Server is not responding (timeout)")
        except requests.exceptions.RequestException as exc:
            click.echo(f"❌ Error checking server: {exc}")
            
    except ImportError:
        click.echo("❌ requests not installed. Cannot check server status.", err=True)
    except Exception as exc:
        click.echo(f"❌ Failed to check server status: {exc}", err=True)
        logger.error(f"Server status check failed: {exc}", exc_info=True)


@server_group.command()
@click.option(
    '--host',
    default=settings.API_HOST,
    help='Server host'
)
@click.option(
    '--port',
    type=int,
    default=settings.API_PORT,
    help='Server port'
)
@click.option(
    '--timeout',
    type=int,
    default=30,
    help='Restart timeout'
)
def restart(host: str, port: int, timeout: int):
    """Restart the API server."""
    click.echo(f"🔄 Restarting API server on {host}:{port}")
    
    # Stop server
    ctx = click.get_current_context()
    ctx.invoke(stop, host=host, port=port, timeout=timeout)
    
    # Wait a moment
    time.sleep(2)
    
    # Start server
    ctx.invoke(start, host=host, port=port)


@server_group.command()
@click.option(
    '--config-file',
    type=click.Path(exists=True),
    help='Gunicorn configuration file'
)
@click.option(
    '--workers',
    type=int,
    default=4,
    help='Number of worker processes'
)
@click.option(
    '--bind',
    default=f"{settings.API_HOST}:{settings.API_PORT}",
    help='Address to bind to'
)
@click.option(
    '--daemon',
    is_flag=True,
    help='Run as daemon'
)
def production(config_file: Optional[str], workers: int, bind: str, daemon: bool):
    """Start server in production mode with Gunicorn."""
    click.echo("🏭 Starting server in production mode...")
    
    try:
        # Build gunicorn command
        cmd = [
            "gunicorn",
            "src.api.main:app",
            "--worker-class", "uvicorn.workers.UvicornWorker",
            "--workers", str(workers),
            "--bind", bind,
            "--access-logfile", "-",
            "--error-logfile", "-",
            "--log-level", "info"
        ]
        
        if config_file:
            cmd.extend(["--config", config_file])
        
        if daemon:
            cmd.append("--daemon")
            click.echo(f"🚀 Starting {workers} workers as daemon on {bind}")
        else:
            click.echo(f"🚀 Starting {workers} workers on {bind}")
            click.echo("Press Ctrl+C to stop")
        
        # Start gunicorn
        subprocess.run(cmd, check=True)
        
    except FileNotFoundError:
        click.echo("❌ gunicorn not installed. Install with: pip install gunicorn", err=True)
        sys.exit(1)
    except subprocess.CalledProcessError as exc:
        click.echo(f"❌ Failed to start production server: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:
        click.echo(f"❌ Production server error: {exc}", err=True)
        logger.error(f"Production server failed: {exc}", exc_info=True)
        sys.exit(1)