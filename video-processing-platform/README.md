# Enterprise Video Processing Platform

A high-performance, scalable system for video downloading, processing, merging, and compression with GPU acceleration and enterprise-grade features.

## Features

- 🚀 **High Performance**: GPU-accelerated video processing with hardware acceleration support
- 🔄 **Concurrent Processing**: Parallel downloads and processing with intelligent queue management
- 🎯 **Smart Compression**: Adaptive bitrate and quality optimization based on content analysis
- 🌐 **Multi-Platform**: Support for multiple video platforms via yt-dlp integration
- 📊 **Enterprise Ready**: Comprehensive monitoring, logging, and observability
- 🔒 **Secure**: JWT authentication, role-based access control, and audit logging
- ☁️ **Cloud Native**: Kubernetes-ready with Docker containerization
- 🛠️ **Flexible Storage**: Support for local, S3, and MinIO storage backends

## Quick Start

### Prerequisites

- Python 3.9+
- Redis (for caching and job queue)
- PostgreSQL (for data persistence)
- FFmpeg (for video processing)
- Optional: CUDA/OpenCL drivers for GPU acceleration

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd video-processing-platform
```

2. Set up development environment:
```bash
make setup-dev
```

3. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

4. Initialize the application:
```bash
python src/main.py
```

### Development Commands

```bash
# Install dependencies
make install-dev

# Run tests
make test

# Run with coverage
make test-cov

# Format code
make format

# Run linting
make lint

# Start development server
make dev

# Clean temporary files
make clean
```

## Configuration

The application uses environment variables for configuration. Key settings include:

- `SECRET_KEY`: Secret key for JWT tokens (required)
- `DATABASE_URL`: PostgreSQL connection string (required)
- `REDIS_URL`: Redis connection string
- `STORAGE_BACKEND`: Storage backend (local, s3, minio)
- `ENABLE_GPU`: Enable GPU acceleration
- `LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR)

See `.env.example` for all available configuration options.

## Architecture

The platform follows a microservices architecture with clear separation of concerns:

- **API Layer**: FastAPI with WebSocket support for real-time updates
- **Processing Layer**: Celery workers for background job processing
- **Core Services**: Download, processing, compression, and storage services
- **Performance Layer**: Rust modules for CPU-intensive operations
- **Data Layer**: PostgreSQL for persistence, Redis for caching

## Testing

Run the test suite:

```bash
# Run all tests
make test

# Run with coverage report
make test-cov

# Run specific test file
pytest tests/test_config.py -v
```

## Docker Deployment

Build and run with Docker:

```bash
# Build Docker image
make docker-build

# Run with docker-compose
make docker-run
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support and questions, please open an issue on the GitHub repository.