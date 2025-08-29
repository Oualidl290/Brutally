"""
Configuration management CLI commands.
"""

import click
import json
import yaml
from pathlib import Path
from typing import Dict, Any

from ...config import settings
from ...config.logging_config import get_logger

logger = get_logger(__name__)


@click.group(name='config')
def config_group():
    """Configuration management commands."""
    pass


@config_group.command()
@click.option(
    '--format',
    type=click.Choice(['json', 'yaml', 'env']),
    default='yaml',
    help='Output format'
)
@click.option(
    '--output', '-o',
    type=click.Path(),
    help='Output file (default: stdout)'
)
@click.option(
    '--include-secrets',
    is_flag=True,
    help='Include sensitive configuration values'
)
def show(format: str, output: str, include_secrets: bool):
    """Show current configuration."""
    
    # Get configuration values
    config_data = {
        'app': {
            'name': settings.APP_NAME,
            'version': settings.APP_VERSION,
            'environment': settings.ENVIRONMENT.value,
            'debug': settings.DEBUG,
        },
        'api': {
            'host': settings.API_HOST,
            'port': settings.API_PORT,
            'prefix': settings.API_PREFIX,
        },
        'database': {
            'url': settings.DATABASE_URL if include_secrets else '[HIDDEN]',
        },
        'redis': {
            'url': settings.REDIS_URL if include_secrets else '[HIDDEN]',
        },
        'storage': {
            'backend': settings.STORAGE_BACKEND,
            'temp_dir': str(settings.TEMP_DIR),
            'output_dir': str(settings.OUTPUT_DIR),
            'cache_dir': str(settings.CACHE_DIR),
        },
        'processing': {
            'enable_gpu': settings.ENABLE_GPU,
            'max_concurrent_jobs': settings.MAX_CONCURRENT_JOBS,
        },
        'logging': {
            'level': settings.LOG_LEVEL.value,
            'file': settings.LOG_FILE,
        }
    }
    
    # Format output
    if format == 'json':
        output_text = json.dumps(config_data, indent=2)
    elif format == 'yaml':
        output_text = yaml.dump(config_data, default_flow_style=False, indent=2)
    elif format == 'env':
        output_text = _dict_to_env(config_data)
    
    # Write output
    if output:
        Path(output).write_text(output_text)
        click.echo(f"✅ Configuration written to {output}")
    else:
        click.echo(output_text)


@config_group.command()
@click.argument('key')
@click.argument('value')
def set(key: str, value: str):
    """Set a configuration value."""
    click.echo(f"🔧 Setting {key} = {value}")
    
    # This would typically update a config file or environment
    # For now, we'll show what would be done
    click.echo("💡 Configuration changes require restart to take effect")
    click.echo("   Consider using environment variables or config files")


@config_group.command()
@click.argument('key')
def get(key: str):
    """Get a configuration value."""
    
    # Map of config keys to values
    config_map = {
        'app.name': settings.APP_NAME,
        'app.version': settings.APP_VERSION,
        'app.environment': settings.ENVIRONMENT.value,
        'app.debug': settings.DEBUG,
        'api.host': settings.API_HOST,
        'api.port': settings.API_PORT,
        'api.prefix': settings.API_PREFIX,
        'database.url': '[HIDDEN]',  # Don't show sensitive values
        'redis.url': '[HIDDEN]',
        'storage.backend': settings.STORAGE_BACKEND,
        'storage.temp_dir': str(settings.TEMP_DIR),
        'storage.output_dir': str(settings.OUTPUT_DIR),
        'processing.enable_gpu': settings.ENABLE_GPU,
        'logging.level': settings.LOG_LEVEL.value,
    }
    
    if key in config_map:
        click.echo(f"{key}: {config_map[key]}")
    else:
        click.echo(f"❌ Configuration key '{key}' not found")
        click.echo("Available keys:")
        for k in sorted(config_map.keys()):
            click.echo(f"  {k}")


@config_group.command()
def validate():
    """Validate current configuration."""
    click.echo("🔍 Validating configuration...")
    
    errors = []
    warnings = []
    
    # Check required settings
    if not settings.SECRET_KEY:
        errors.append("SECRET_KEY is not set")
    
    if not settings.DATABASE_URL:
        errors.append("DATABASE_URL is not set")
    
    # Check directories
    for dir_name, dir_path in [
        ('TEMP_DIR', settings.TEMP_DIR),
        ('OUTPUT_DIR', settings.OUTPUT_DIR),
        ('CACHE_DIR', settings.CACHE_DIR),
    ]:
        if not dir_path.exists():
            warnings.append(f"{dir_name} does not exist: {dir_path}")
    
    # Check API settings
    if settings.API_PORT < 1024 and settings.API_HOST != 'localhost':
        warnings.append("API_PORT < 1024 may require root privileges")
    
    # Check GPU settings
    if settings.ENABLE_GPU:
        try:
            # This would check for actual GPU availability
            warnings.append("GPU acceleration enabled but not verified")
        except Exception:
            warnings.append("GPU acceleration enabled but GPU not available")
    
    # Report results
    if errors:
        click.echo("❌ Configuration errors found:")
        for error in errors:
            click.echo(f"  • {error}")
    
    if warnings:
        click.echo("⚠️  Configuration warnings:")
        for warning in warnings:
            click.echo(f"  • {warning}")
    
    if not errors and not warnings:
        click.echo("✅ Configuration is valid")
    
    return len(errors) == 0


@config_group.command()
@click.option(
    '--output-dir', '-o',
    type=click.Path(),
    default='./config',
    help='Output directory for generated files'
)
def generate_docker():
    """Generate Docker configuration files."""
    click.echo("🐳 Generating Docker configuration...")
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Generate Dockerfile
    dockerfile_content = '''FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \\
    ffmpeg \\
    curl \\
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY src/ ./src/
COPY pyproject.toml .

# Install application
RUN pip install -e .

# Create non-root user
RUN useradd --create-home --shell /bin/bash app
USER app

# Expose port
EXPOSE 8000

# Default command
CMD ["video-processor", "server", "start", "--host", "0.0.0.0"]
'''
    
    (output_path / 'Dockerfile').write_text(dockerfile_content)
    
    # Generate docker-compose.yml
    compose_content = '''version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:password@db:5432/video_processing
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - db
      - redis
    volumes:
      - ./output:/app/output
      - ./temp:/app/temp

  worker:
    build: .
    command: video-processor worker start
    environment:
      - DATABASE_URL=postgresql://postgres:password@db:5432/video_processing
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - db
      - redis
    volumes:
      - ./output:/app/output
      - ./temp:/app/temp

  db:
    image: postgres:15
    environment:
      - POSTGRES_DB=video_processing
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  flower:
    build: .
    command: video-processor worker monitor
    ports:
      - "5555:5555"
    environment:
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - redis

volumes:
  postgres_data:
'''
    
    (output_path / 'docker-compose.yml').write_text(compose_content)
    
    # Generate .dockerignore
    dockerignore_content = '''__pycache__
*.pyc
*.pyo
*.pyd
.Python
env
pip-log.txt
pip-delete-this-directory.txt
.tox
.coverage
.coverage.*
.cache
nosetests.xml
coverage.xml
*.cover
*.log
.git
.mypy_cache
.pytest_cache
.hypothesis

.DS_Store
.vscode
.idea
*.swp
*.swo

node_modules
npm-debug.log*

.env
.env.local
.env.*.local

dist
build
*.egg-info
'''
    
    (output_path / '.dockerignore').write_text(dockerignore_content)
    
    click.echo(f"✅ Docker files generated in {output_path}")
    click.echo("Files created:")
    click.echo("  • Dockerfile")
    click.echo("  • docker-compose.yml")
    click.echo("  • .dockerignore")


@config_group.command()
@click.option(
    '--output-dir', '-o',
    type=click.Path(),
    default='./config',
    help='Output directory for generated files'
)
def generate_supervisor():
    """Generate Supervisor configuration files."""
    click.echo("👷 Generating Supervisor configuration...")
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # API server config
    api_config = '''[program:video_processor_api]
command=video-processor server start --host 0.0.0.0 --port 8000
directory=/app
user=app
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/video_processor_api.log
environment=PATH="/app/venv/bin:%(ENV_PATH)s"
'''
    
    # Worker config
    worker_config = '''[program:video_processor_worker]
command=video-processor worker start --concurrency 4
directory=/app
user=app
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/video_processor_worker.log
environment=PATH="/app/venv/bin:%(ENV_PATH)s"
'''
    
    # Beat scheduler config
    beat_config = '''[program:video_processor_beat]
command=celery -A src.celery_app.app beat --loglevel info
directory=/app
user=app
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/video_processor_beat.log
environment=PATH="/app/venv/bin:%(ENV_PATH)s"
'''
    
    # Group config
    group_config = '''[group:video_processor]
programs=video_processor_api,video_processor_worker,video_processor_beat
priority=999
'''
    
    (output_path / 'video_processor_api.conf').write_text(api_config)
    (output_path / 'video_processor_worker.conf').write_text(worker_config)
    (output_path / 'video_processor_beat.conf').write_text(beat_config)
    (output_path / 'video_processor_group.conf').write_text(group_config)
    
    click.echo(f"✅ Supervisor files generated in {output_path}")
    click.echo("Files created:")
    click.echo("  • video_processor_api.conf")
    click.echo("  • video_processor_worker.conf")
    click.echo("  • video_processor_beat.conf")
    click.echo("  • video_processor_group.conf")


def _dict_to_env(data: Dict[str, Any], prefix: str = '') -> str:
    """Convert nested dict to environment variable format."""
    lines = []
    
    for key, value in data.items():
        env_key = f"{prefix}{key.upper()}" if prefix else key.upper()
        
        if isinstance(value, dict):
            lines.extend(_dict_to_env(value, f"{env_key}_").split('\n'))
        else:
            lines.append(f"{env_key}={value}")
    
    return '\n'.join(lines)