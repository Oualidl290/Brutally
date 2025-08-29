"""
Health check and monitoring CLI commands.
"""

import click
import asyncio
import json
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from ...config.logging_config import get_logger
from ...monitoring.health import health_checker
from ...monitoring.metrics import metrics_manager

logger = get_logger(__name__)
console = Console()


@click.group(name='health')
def health_group():
    """Health check and monitoring commands."""
    pass


@health_group.command()
@click.option(
    '--json-output',
    is_flag=True,
    help='Output in JSON format'
)
def check(json_output: bool):
    """Run comprehensive health checks."""
    
    async def run_health_check():
        try:
            health_summary = await health_checker.get_health_summary()
            
            if json_output:
                click.echo(json.dumps(health_summary, indent=2, default=str))
            else:
                # Rich formatted output
                status = health_summary['status']
                status_color = {
                    'healthy': 'green',
                    'degraded': 'yellow',
                    'unhealthy': 'red'
                }.get(status, 'white')
                
                # Overall status panel
                overall_content = f"""
[bold]Overall Status:[/bold] [{status_color}]{status.upper()}[/{status_color}]
[bold]Timestamp:[/bold] {health_summary['timestamp']}
[bold]Total Checks:[/bold] {health_summary['summary']['total_checks']}
                """.strip()
                
                console.print(Panel(overall_content, title="Health Summary", border_style=status_color))
                
                # Individual checks table
                table = Table(title="Health Check Details")
                table.add_column("Check", style="cyan")
                table.add_column("Status", style="white")
                table.add_column("Message", style="white")
                table.add_column("Duration", style="dim")
                
                for check_name, check_result in health_summary['checks'].items():
                    check_status = check_result['status']
                    status_icon = {
                        'healthy': '✅',
                        'degraded': '⚠️',
                        'unhealthy': '❌',
                        'unknown': '❓'
                    }.get(check_status, '❓')
                    
                    duration = f"{check_result['duration']:.3f}s"
                    
                    table.add_row(
                        check_name,
                        f"{status_icon} {check_status}",
                        check_result['message'][:50] + "..." if len(check_result['message']) > 50 else check_result['message'],
                        duration
                    )
                
                console.print(table)
                
                # Status counts
                counts = health_summary['summary']['status_counts']
                console.print(f"\n📊 Status Summary: {counts['healthy']} healthy, {counts['degraded']} degraded, {counts['unhealthy']} unhealthy")
        
        except Exception as exc:
            click.echo(f"❌ Health check failed: {exc}", err=True)
            logger.error(f"Health check command failed: {exc}", exc_info=True)
            raise click.ClickException(str(exc))
    
    asyncio.run(run_health_check())


@health_group.command()
@click.argument('check_name')
@click.option(
    '--json-output',
    is_flag=True,
    help='Output in JSON format'
)
def run(check_name: str, json_output: bool):
    """Run a specific health check."""
    
    async def run_specific_check():
        try:
            result = await health_checker.run_check(check_name)
            
            if json_output:
                click.echo(json.dumps(result.to_dict(), indent=2, default=str))
            else:
                status_color = {
                    'healthy': 'green',
                    'degraded': 'yellow',
                    'unhealthy': 'red',
                    'unknown': 'dim'
                }.get(result.status.value, 'white')
                
                content = f"""
[bold]Check:[/bold] {result.name}
[bold]Status:[/bold] [{status_color}]{result.status.value.upper()}[/{status_color}]
[bold]Message:[/bold] {result.message}
[bold]Duration:[/bold] {result.duration:.3f}s
[bold]Timestamp:[/bold] {result.timestamp}
                """.strip()
                
                if result.details:
                    content += f"\n[bold]Details:[/bold] {json.dumps(result.details, indent=2)}"
                
                console.print(Panel(content, title=f"Health Check: {check_name}", border_style=status_color))
        
        except Exception as exc:
            click.echo(f"❌ Health check '{check_name}' failed: {exc}", err=True)
            logger.error(f"Specific health check failed: {exc}", exc_info=True)
            raise click.ClickException(str(exc))
    
    asyncio.run(run_specific_check())


@health_group.command()
def list():
    """List available health checks."""
    
    checks = list(health_checker.checks.keys())
    intervals = health_checker.check_intervals
    
    if not checks:
        console.print("📭 No health checks registered")
        return
    
    table = Table(title=f"Available Health Checks ({len(checks)})")
    table.add_column("Check Name", style="cyan")
    table.add_column("Interval", style="yellow")
    table.add_column("Description", style="white")
    
    descriptions = {
        'database': 'Database connectivity and performance',
        'system_resources': 'CPU, memory, and disk usage',
        'disk_space': 'Available disk space',
        'memory_usage': 'Memory utilization',
        'cpu_usage': 'CPU utilization',
        'job_queue': 'Job queue health and backlog',
        'worker_processes': 'Celery worker process status'
    }
    
    for check in sorted(checks):
        interval = intervals.get(check, 60)
        description = descriptions.get(check, 'Custom health check')
        
        table.add_row(
            check,
            f"{interval}s",
            description
        )
    
    console.print(table)


@health_group.command()
@click.option(
    '--interval',
    type=int,
    default=5,
    help='Update interval in seconds'
)
@click.option(
    '--count',
    type=int,
    help='Number of checks to run (default: infinite)'
)
def monitor(interval: int, count: int):
    """Monitor health status continuously."""
    
    async def run_monitor():
        try:
            check_count = 0
            
            while True:
                if count and check_count >= count:
                    break
                
                # Clear screen
                console.clear()
                
                # Run health check
                health_summary = await health_checker.get_health_summary()
                
                # Display status
                status = health_summary['status']
                status_color = {
                    'healthy': 'green',
                    'degraded': 'yellow',
                    'unhealthy': 'red'
                }.get(status, 'white')
                
                console.print(f"[{status_color}]● {status.upper()}[/{status_color}] - {health_summary['timestamp']}")
                
                # Show quick summary
                counts = health_summary['summary']['status_counts']
                console.print(f"Checks: {counts['healthy']} ✅ {counts['degraded']} ⚠️ {counts['unhealthy']} ❌")
                
                # Show failing checks
                failing_checks = [
                    name for name, result in health_summary['checks'].items()
                    if result['status'] in ['unhealthy', 'degraded']
                ]
                
                if failing_checks:
                    console.print(f"\n[red]Issues:[/red] {', '.join(failing_checks)}")
                
                check_count += 1
                
                if count and check_count >= count:
                    break
                
                # Wait for next check
                await asyncio.sleep(interval)
        
        except KeyboardInterrupt:
            console.print("\n⚠️  Monitoring stopped by user")
        except Exception as exc:
            click.echo(f"❌ Health monitoring failed: {exc}", err=True)
            logger.error(f"Health monitoring failed: {exc}", exc_info=True)
    
    console.print(f"🔍 Starting health monitoring (interval: {interval}s)")
    console.print("Press Ctrl+C to stop")
    
    asyncio.run(run_monitor())


@health_group.command()
@click.option(
    '--format',
    type=click.Choice(['prometheus', 'json']),
    default='prometheus',
    help='Metrics output format'
)
def metrics(format: str):
    """Show system metrics."""
    
    try:
        if format == 'prometheus':
            metrics_data = metrics_manager.get_metrics()
            click.echo(metrics_data)
        elif format == 'json':
            # This would require parsing Prometheus format back to structured data
            # For now, show a simplified version
            click.echo('{"message": "JSON metrics format not yet implemented"}')
    
    except Exception as exc:
        click.echo(f"❌ Failed to get metrics: {exc}", err=True)
        logger.error(f"Metrics command failed: {exc}", exc_info=True)
        raise click.ClickException(str(exc))


@health_group.command()
@click.option(
    '--host',
    default='localhost',
    help='API server host'
)
@click.option(
    '--port',
    type=int,
    default=8000,
    help='API server port'
)
def ping(host: str, port: int):
    """Ping the API server."""
    
    try:
        import requests
        
        url = f"http://{host}:{port}/ping"
        
        start_time = time.time()
        response = requests.get(url, timeout=10)
        duration = time.time() - start_time
        
        if response.status_code == 200:
            console.print(f"✅ Server is responding ({duration*1000:.1f}ms)")
            
            try:
                data = response.json()
                if 'timestamp' in data:
                    console.print(f"   Server time: {data['timestamp']}")
            except:
                pass
        else:
            console.print(f"❌ Server responded with status {response.status_code}")
    
    except requests.exceptions.ConnectionError:
        console.print(f"❌ Cannot connect to server at {host}:{port}")
    except requests.exceptions.Timeout:
        console.print(f"❌ Server at {host}:{port} is not responding (timeout)")
    except ImportError:
        click.echo("❌ requests library not installed", err=True)
    except Exception as exc:
        click.echo(f"❌ Ping failed: {exc}", err=True)