"""
End-to-end CLI tests covering complete workflows.
"""

import pytest
import subprocess
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, Mock

from click.testing import CliRunner

from src.cli.main import cli


class TestCLIEndToEnd:
    """End-to-end CLI workflow tests."""
    
    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    def test_cli_help(self, runner):
        """Test CLI help command."""
        result = runner.invoke(cli, ['--help'])
        assert result.exit_code == 0
        assert 'Enterprise Video Processing Platform CLI' in result.output
        assert 'process' in result.output
        assert 'jobs' in result.output
        assert 'server' in result.output
        assert 'worker' in result.output
    
    def test_version_command(self, runner):
        """Test version command."""
        result = runner.invoke(cli, ['version'])
        assert result.exit_code == 0
        assert 'Enterprise Video Processing Platform' in result.output
        assert 'Environment:' in result.output
        assert 'Python:' in result.output
    
    def test_init_command(self, runner, temp_dir):
        """Test initialization command."""
        output_dir = temp_dir / 'output'
        temp_work_dir = temp_dir / 'temp'
        
        result = runner.invoke(cli, [
            'init',
            '--output-dir', str(output_dir),
            '--temp-dir', str(temp_work_dir)
        ])
        
        assert result.exit_code == 0
        assert 'Initializing Video Processing Platform' in result.output
        assert output_dir.exists()
        assert temp_work_dir.exists()
    
    def test_config_show_command(self, runner):
        """Test configuration show command."""
        result = runner.invoke(cli, ['config', 'show', '--format', 'json'])
        assert result.exit_code == 0
        
        # Should be valid JSON
        config_data = json.loads(result.output)
        assert 'app' in config_data
        assert 'api' in config_data
        assert 'database' in config_data
    
    def test_config_get_command(self, runner):
        """Test configuration get command."""
        result = runner.invoke(cli, ['config', 'get', 'app.name'])
        assert result.exit_code == 0
        assert 'Enterprise Video Processing Platform' in result.output
    
    def test_config_validate_command(self, runner):
        """Test configuration validation."""
        result = runner.invoke(cli, ['config', 'validate'])
        assert result.exit_code == 0
        # Should show validation results
        assert 'Validating configuration' in result.output
    
    def test_health_list_command(self, runner):
        """Test health checks list command."""
        result = runner.invoke(cli, ['health', 'list'])
        assert result.exit_code == 0
        assert 'Available Health Checks' in result.output
    
    @pytest.mark.asyncio
    async def test_health_check_command(self, runner):
        """Test health check command."""
        with patch('src.monitoring.health.health_checker.get_health_summary') as mock_health:
            mock_health.return_value = {
                'status': 'healthy',
                'timestamp': '2023-01-01T00:00:00',
                'checks': {
                    'test_check': {
                        'status': 'healthy',
                        'message': 'Test check passed',
                        'duration': 0.1
                    }
                },
                'summary': {
                    'total_checks': 1,
                    'status_counts': {'healthy': 1, 'degraded': 0, 'unhealthy': 0, 'unknown': 0}
                }
            }
            
            result = runner.invoke(cli, ['health', 'check'])
            assert result.exit_code == 0
            assert 'Health Summary' in result.output
    
    def test_jobs_list_command(self, runner):
        """Test jobs list command."""
        with patch('src.database.connection.get_async_session'):
            with patch('src.database.repositories.job_repo.JobRepository') as mock_repo:
                mock_repo.return_value.get_jobs.return_value = []
                
                result = runner.invoke(cli, ['jobs', 'list'])
                assert result.exit_code == 0
                assert 'No jobs found' in result.output
    
    def test_config_generate_docker(self, runner, temp_dir):
        """Test Docker configuration generation."""
        result = runner.invoke(cli, [
            'config', 'generate-docker',
            '--output-dir', str(temp_dir)
        ])
        
        assert result.exit_code == 0
        assert 'Docker files generated' in result.output
        
        # Check generated files
        assert (temp_dir / 'Dockerfile').exists()
        assert (temp_dir / 'docker-compose.yml').exists()
        assert (temp_dir / '.dockerignore').exists()
    
    def test_config_generate_supervisor(self, runner, temp_dir):
        """Test Supervisor configuration generation."""
        result = runner.invoke(cli, [
            'config', 'generate-supervisor',
            '--output-dir', str(temp_dir)
        ])
        
        assert result.exit_code == 0
        assert 'Supervisor files generated' in result.output
        
        # Check generated files
        assert (temp_dir / 'video_processor_api.conf').exists()
        assert (temp_dir / 'video_processor_worker.conf').exists()
        assert (temp_dir / 'video_processor_beat.conf').exists()
        assert (temp_dir / 'video_processor_group.conf').exists()


class TestProcessingWorkflows:
    """Test complete processing workflows."""
    
    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def sample_video_file(self, temp_dir):
        """Create a sample video file for testing."""
        video_file = temp_dir / 'sample.mp4'
        # Create a dummy file (in real tests, this would be a valid video)
        video_file.write_bytes(b'fake video content')
        return video_file
    
    @patch('src.cli.commands.process.asyncio.run')
    def test_download_workflow(self, mock_asyncio, runner, temp_dir):
        """Test video download workflow."""
        mock_asyncio.return_value = None
        
        result = runner.invoke(cli, [
            'process', 'download',
            'https://example.com/video1.mp4',
            'https://example.com/video2.mp4',
            '--output-dir', str(temp_dir),
            '--quality', '720p',
            '--job-name', 'Test Download'
        ])
        
        # Should not crash (mocked async function)
        mock_asyncio.assert_called_once()
    
    @patch('src.cli.commands.process.asyncio.run')
    def test_video_processing_workflow(self, mock_asyncio, runner, temp_dir, sample_video_file):
        """Test video processing workflow."""
        mock_asyncio.return_value = None
        
        result = runner.invoke(cli, [
            'process', 'video',
            str(sample_video_file),
            '--output-dir', str(temp_dir),
            '--quality', '1080p',
            '--codec', 'h264',
            '--use-gpu',
            '--job-name', 'Test Processing'
        ])
        
        mock_asyncio.assert_called_once()
    
    @patch('src.cli.commands.process.asyncio.run')
    def test_merge_workflow(self, mock_asyncio, runner, temp_dir, sample_video_file):
        """Test video merge workflow."""
        mock_asyncio.return_value = None
        
        # Create additional sample files
        video_file2 = temp_dir / 'sample2.mp4'
        video_file2.write_bytes(b'fake video content 2')
        
        output_file = temp_dir / 'merged.mp4'
        
        result = runner.invoke(cli, [
            'process', 'merge',
            str(sample_video_file),
            str(video_file2),
            '--output', str(output_file),
            '--create-chapters',
            '--job-name', 'Test Merge'
        ])
        
        mock_asyncio.assert_called_once()
    
    @patch('src.cli.commands.process.asyncio.run')
    def test_complete_workflow(self, mock_asyncio, runner, temp_dir):
        """Test complete download -> process -> merge workflow."""
        mock_asyncio.return_value = None
        
        merge_output = temp_dir / 'final.mp4'
        
        result = runner.invoke(cli, [
            'process', 'complete',
            'https://example.com/video1.mp4',
            'https://example.com/video2.mp4',
            '--output-dir', str(temp_dir),
            '--quality', '1080p',
            '--merge-output', str(merge_output),
            '--create-chapters',
            '--use-gpu',
            '--job-name', 'Complete Workflow Test',
            '--priority', 'high'
        ])
        
        mock_asyncio.assert_called_once()


class TestServerManagement:
    """Test server management commands."""
    
    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()
    
    @patch('src.cli.commands.server.uvicorn')
    def test_server_start_command(self, mock_uvicorn, runner):
        """Test server start command."""
        mock_server = Mock()
        mock_uvicorn.Server.return_value = mock_server
        
        result = runner.invoke(cli, [
            'server', 'start',
            '--host', '127.0.0.1',
            '--port', '8001',
            '--workers', '2'
        ])
        
        # Should attempt to start server
        mock_uvicorn.Server.assert_called_once()
    
    @patch('src.cli.commands.server.requests')
    def test_server_status_command(self, mock_requests, runner):
        """Test server status command."""
        # Mock healthy response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'status': 'healthy',
            'version': '1.0.0',
            'uptime': 3600
        }
        mock_requests.get.return_value = mock_response
        
        result = runner.invoke(cli, ['server', 'status'])
        assert result.exit_code == 0
        assert 'Server is running and healthy' in result.output
    
    @patch('src.cli.commands.server.subprocess.run')
    def test_server_production_command(self, mock_subprocess, runner):
        """Test production server start."""
        mock_subprocess.return_value = Mock(returncode=0)
        
        result = runner.invoke(cli, [
            'server', 'production',
            '--workers', '4',
            '--bind', '0.0.0.0:8000'
        ])
        
        mock_subprocess.assert_called_once()


class TestWorkerManagement:
    """Test worker management commands."""
    
    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()
    
    @patch('src.cli.commands.worker.subprocess.run')
    def test_worker_start_command(self, mock_subprocess, runner):
        """Test worker start command."""
        mock_subprocess.return_value = Mock(returncode=0)
        
        result = runner.invoke(cli, [
            'worker', 'start',
            '--queues', 'processing',
            '--queues', 'download',
            '--concurrency', '4'
        ])
        
        mock_subprocess.assert_called_once()
    
    @patch('src.cli.commands.worker.subprocess.run')
    def test_worker_status_command(self, mock_subprocess, runner):
        """Test worker status command."""
        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout='Worker status output',
            stderr=''
        )
        
        result = runner.invoke(cli, ['worker', 'status'])
        assert result.exit_code == 0
    
    @patch('src.cli.commands.worker.psutil')
    def test_worker_stop_command(self, mock_psutil, runner):
        """Test worker stop command."""
        # Mock worker process
        mock_process = Mock()
        mock_process.info = {'pid': 1234, 'cmdline': ['celery', 'worker']}
        mock_process.terminate.return_value = None
        mock_process.wait.return_value = None
        
        mock_psutil.process_iter.return_value = [mock_process]
        
        result = runner.invoke(cli, ['worker', 'stop'])
        assert result.exit_code == 0
        mock_process.terminate.assert_called_once()


class TestIntegrationScenarios:
    """Test realistic integration scenarios."""
    
    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()
    
    def test_development_setup_scenario(self, runner):
        """Test complete development environment setup."""
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)
            
            # 1. Initialize project
            result = runner.invoke(cli, [
                'init',
                '--output-dir', str(temp_path / 'output'),
                '--temp-dir', str(temp_path / 'temp')
            ])
            assert result.exit_code == 0
            
            # 2. Validate configuration
            result = runner.invoke(cli, ['config', 'validate'])
            assert result.exit_code == 0
            
            # 3. Generate Docker files
            result = runner.invoke(cli, [
                'config', 'generate-docker',
                '--output-dir', str(temp_path / 'docker')
            ])
            assert result.exit_code == 0
            
            # 4. Check health checks are available
            result = runner.invoke(cli, ['health', 'list'])
            assert result.exit_code == 0
    
    def test_production_deployment_scenario(self, runner):
        """Test production deployment preparation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)
            
            # 1. Generate production configs
            result = runner.invoke(cli, [
                'config', 'generate-supervisor',
                '--output-dir', str(temp_path / 'supervisor')
            ])
            assert result.exit_code == 0
            
            # 2. Show production configuration
            result = runner.invoke(cli, [
                'config', 'show',
                '--format', 'env'
            ])
            assert result.exit_code == 0
            
            # 3. Validate configuration
            result = runner.invoke(cli, ['config', 'validate'])
            assert result.exit_code == 0
    
    @patch('src.cli.commands.process.asyncio.run')
    @patch('src.cli.commands.jobs.asyncio.run')
    def test_job_lifecycle_scenario(self, mock_jobs_asyncio, mock_process_asyncio, runner):
        """Test complete job lifecycle."""
        # Mock async functions
        mock_process_asyncio.return_value = None
        mock_jobs_asyncio.return_value = None
        
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)
            
            # 1. Start a processing job
            result = runner.invoke(cli, [
                'process', 'download',
                'https://example.com/test.mp4',
                '--output-dir', str(temp_path),
                '--job-name', 'Integration Test Job'
            ])
            # Should not crash with mocked async
            
            # 2. List jobs
            result = runner.invoke(cli, ['jobs', 'list'])
            # Will show "No jobs found" due to mocking, but shouldn't crash
            
            # 3. Check active jobs
            result = runner.invoke(cli, ['jobs', 'active'])
            # Should not crash


if __name__ == "__main__":
    pytest.main([__file__, "-v"])