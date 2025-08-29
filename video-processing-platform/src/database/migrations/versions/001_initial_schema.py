"""Initial database schema

Revision ID: 001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create users table
    op.create_table('users',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('username', sa.String(length=50), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=True),
        sa.Column('role', sa.Enum('ADMIN', 'USER', 'VIEWER', name='userrole'), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('is_verified', sa.Boolean(), nullable=False),
        sa.Column('api_key', sa.String(length=255), nullable=True),
        sa.Column('job_count', sa.Integer(), nullable=False),
        sa.Column('total_processing_time', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_api_key'), 'users', ['api_key'], unique=True)
    op.create_index(op.f('ix_users_created_at'), 'users', ['created_at'], unique=False)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_is_active'), 'users', ['is_active'], unique=False)
    op.create_index(op.f('ix_users_role'), 'users', ['role'], unique=False)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    op.create_index('idx_users_created', 'users', ['created_at'], unique=False)
    op.create_index('idx_users_role_active', 'users', ['role', 'is_active'], unique=False)

    # Create jobs table
    op.create_table('jobs',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('status', sa.Enum('PENDING', 'INITIALIZING', 'DOWNLOADING', 'PROCESSING', 'MERGING', 'COMPRESSING', 'UPLOADING', 'COMPLETED', 'FAILED', 'CANCELLED', name='jobstatus'), nullable=False),
        sa.Column('priority', sa.Enum('LOW', 'NORMAL', 'HIGH', 'URGENT', name='jobpriority'), nullable=False),
        sa.Column('request_data', sa.JSON(), nullable=False),
        sa.Column('season_name', sa.String(length=255), nullable=False),
        sa.Column('video_urls', sa.JSON(), nullable=False),
        sa.Column('video_quality', sa.String(length=10), nullable=False),
        sa.Column('compression_preset', sa.String(length=20), nullable=False),
        sa.Column('compression_level', sa.Integer(), nullable=False),
        sa.Column('use_gpu', sa.Boolean(), nullable=False),
        sa.Column('use_hardware_accel', sa.Boolean(), nullable=False),
        sa.Column('output_file', sa.Text(), nullable=True),
        sa.Column('output_size', sa.Integer(), nullable=True),
        sa.Column('progress', sa.JSON(), nullable=False),
        sa.Column('current_stage', sa.String(length=50), nullable=True),
        sa.Column('progress_percentage', sa.Integer(), nullable=False),
        sa.Column('errors', sa.JSON(), nullable=False),
        sa.Column('error_count', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.String(length=255), nullable=True),
        sa.Column('notification_webhook', sa.Text(), nullable=True),
        sa.Column('notification_sent', sa.Boolean(), nullable=False),
        sa.Column('tags', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_jobs_created_at'), 'jobs', ['created_at'], unique=False)
    op.create_index(op.f('ix_jobs_id'), 'jobs', ['id'], unique=False)
    op.create_index(op.f('ix_jobs_priority'), 'jobs', ['priority'], unique=False)
    op.create_index(op.f('ix_jobs_season_name'), 'jobs', ['season_name'], unique=False)
    op.create_index(op.f('ix_jobs_status'), 'jobs', ['status'], unique=False)
    op.create_index(op.f('ix_jobs_task_id'), 'jobs', ['task_id'], unique=False)
    op.create_index(op.f('ix_jobs_updated_at'), 'jobs', ['updated_at'], unique=False)
    op.create_index(op.f('ix_jobs_user_id'), 'jobs', ['user_id'], unique=False)
    op.create_index('idx_jobs_created_status', 'jobs', ['created_at', 'status'], unique=False)
    op.create_index('idx_jobs_status_priority', 'jobs', ['status', 'priority'], unique=False)
    op.create_index('idx_jobs_user_status', 'jobs', ['user_id', 'status'], unique=False)

    # Create video_metadata table
    op.create_table('video_metadata',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('job_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('episode_number', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=True),
        sa.Column('duration', sa.Float(), nullable=True),
        sa.Column('filesize', sa.Integer(), nullable=True),
        sa.Column('format', sa.String(length=50), nullable=True),
        sa.Column('codec', sa.String(length=50), nullable=True),
        sa.Column('resolution', sa.String(length=20), nullable=True),
        sa.Column('fps', sa.Float(), nullable=True),
        sa.Column('bitrate', sa.Integer(), nullable=True),
        sa.Column('audio_codec', sa.String(length=50), nullable=True),
        sa.Column('audio_bitrate', sa.Integer(), nullable=True),
        sa.Column('audio_channels', sa.Integer(), nullable=True),
        sa.Column('downloaded_path', sa.Text(), nullable=True),
        sa.Column('processed_path', sa.Text(), nullable=True),
        sa.Column('download_status', sa.String(length=20), nullable=False),
        sa.Column('processing_status', sa.String(length=20), nullable=False),
        sa.Column('download_progress', sa.Integer(), nullable=False),
        sa.Column('processing_progress', sa.Integer(), nullable=False),
        sa.Column('download_error', sa.Text(), nullable=True),
        sa.Column('processing_error', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False),
        sa.Column('metadata', sa.JSON(), nullable=False),
        sa.Column('download_checksum', sa.String(length=64), nullable=True),
        sa.Column('processed_checksum', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('download_started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('download_completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('processing_started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('processing_completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_video_metadata_created_at'), 'video_metadata', ['created_at'], unique=False)
    op.create_index(op.f('ix_video_metadata_download_status'), 'video_metadata', ['download_status'], unique=False)
    op.create_index(op.f('ix_video_metadata_episode_number'), 'video_metadata', ['episode_number'], unique=False)
    op.create_index(op.f('ix_video_metadata_id'), 'video_metadata', ['id'], unique=False)
    op.create_index(op.f('ix_video_metadata_job_id'), 'video_metadata', ['job_id'], unique=False)
    op.create_index(op.f('ix_video_metadata_processing_status'), 'video_metadata', ['processing_status'], unique=False)
    op.create_index('idx_video_download_status', 'video_metadata', ['download_status'], unique=False)
    op.create_index('idx_video_job_episode', 'video_metadata', ['job_id', 'episode_number'], unique=False)
    op.create_index('idx_video_processing_status', 'video_metadata', ['processing_status'], unique=False)

    # Create audit_logs table
    op.create_table('audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('action', sa.Enum('USER_LOGIN', 'USER_LOGOUT', 'USER_CREATED', 'USER_UPDATED', 'USER_DELETED', 'JOB_CREATED', 'JOB_STARTED', 'JOB_COMPLETED', 'JOB_FAILED', 'JOB_CANCELLED', 'JOB_DELETED', 'SYSTEM_STARTUP', 'SYSTEM_SHUTDOWN', 'CONFIG_CHANGED', 'AUTH_FAILED', 'ACCESS_DENIED', 'API_KEY_CREATED', 'API_KEY_REVOKED', 'FILE_UPLOADED', 'FILE_DOWNLOADED', 'FILE_DELETED', name='auditaction'), nullable=False),
        sa.Column('resource_type', sa.String(length=50), nullable=True),
        sa.Column('resource_id', sa.String(length=255), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('details', sa.JSON(), nullable=False),
        sa.Column('success', sa.Boolean(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'], unique=False)
    op.create_index(op.f('ix_audit_logs_created_at'), 'audit_logs', ['created_at'], unique=False)
    op.create_index(op.f('ix_audit_logs_id'), 'audit_logs', ['id'], unique=False)
    op.create_index(op.f('ix_audit_logs_ip_address'), 'audit_logs', ['ip_address'], unique=False)
    op.create_index(op.f('ix_audit_logs_resource_id'), 'audit_logs', ['resource_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_resource_type'), 'audit_logs', ['resource_type'], unique=False)
    op.create_index(op.f('ix_audit_logs_success'), 'audit_logs', ['success'], unique=False)
    op.create_index(op.f('ix_audit_logs_user_id'), 'audit_logs', ['user_id'], unique=False)
    op.create_index('idx_audit_created_action', 'audit_logs', ['created_at', 'action'], unique=False)
    op.create_index('idx_audit_ip_created', 'audit_logs', ['ip_address', 'created_at'], unique=False)
    op.create_index('idx_audit_resource', 'audit_logs', ['resource_type', 'resource_id'], unique=False)
    op.create_index('idx_audit_user_action', 'audit_logs', ['user_id', 'action'], unique=False)

    # Create storage_files table
    op.create_table('storage_files',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('job_id', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('video_id', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('filename', sa.String(length=500), nullable=False),
        sa.Column('file_path', sa.String(length=1000), nullable=False),
        sa.Column('original_filename', sa.String(length=500), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('content_type', sa.String(length=100), nullable=True),
        sa.Column('file_extension', sa.String(length=20), nullable=True),
        sa.Column('md5_hash', sa.String(length=32), nullable=True),
        sa.Column('sha256_hash', sa.String(length=64), nullable=True),
        sa.Column('checksum', sa.String(length=100), nullable=True),
        sa.Column('storage_backend', sa.Enum('LOCAL', 'S3', 'MINIO', 'AZURE', 'GCS', name='storagebackend'), nullable=False),
        sa.Column('bucket_name', sa.String(length=200), nullable=True),
        sa.Column('storage_path', sa.String(length=1000), nullable=False),
        sa.Column('access_level', sa.Enum('PUBLIC', 'PRIVATE', 'AUTHENTICATED', 'RESTRICTED', name='accesslevel'), nullable=False),
        sa.Column('is_encrypted', sa.Boolean(), nullable=False),
        sa.Column('encryption_key_id', sa.String(length=100), nullable=True),
        sa.Column('public_url', sa.String(length=2000), nullable=True),
        sa.Column('signed_url', sa.String(length=2000), nullable=True),
        sa.Column('signed_url_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('upload_started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('upload_completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_accessed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('file_category', sa.String(length=50), nullable=True),
        sa.Column('file_type', sa.String(length=50), nullable=True),
        sa.Column('is_temporary', sa.Boolean(), nullable=False),
        sa.Column('processing_stage', sa.String(length=50), nullable=True),
        sa.Column('file_metadata', sa.JSON(), nullable=False),
        sa.Column('storage_metadata', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['video_id'], ['video_metadata.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_storage_files_access_level'), 'storage_files', ['access_level'], unique=False)
    op.create_index(op.f('ix_storage_files_created_at'), 'storage_files', ['created_at'], unique=False)
    op.create_index(op.f('ix_storage_files_expires_at'), 'storage_files', ['expires_at'], unique=False)
    op.create_index(op.f('ix_storage_files_file_category'), 'storage_files', ['file_category'], unique=False)
    op.create_index(op.f('ix_storage_files_file_extension'), 'storage_files', ['file_extension'], unique=False)
    op.create_index(op.f('ix_storage_files_file_path'), 'storage_files', ['file_path'], unique=False)
    op.create_index(op.f('ix_storage_files_file_type'), 'storage_files', ['file_type'], unique=False)
    op.create_index(op.f('ix_storage_files_filename'), 'storage_files', ['filename'], unique=False)
    op.create_index(op.f('ix_storage_files_id'), 'storage_files', ['id'], unique=False)
    op.create_index(op.f('ix_storage_files_is_temporary'), 'storage_files', ['is_temporary'], unique=False)
    op.create_index(op.f('ix_storage_files_job_id'), 'storage_files', ['job_id'], unique=False)
    op.create_index(op.f('ix_storage_files_md5_hash'), 'storage_files', ['md5_hash'], unique=False)
    op.create_index(op.f('ix_storage_files_storage_backend'), 'storage_files', ['storage_backend'], unique=False)
    op.create_index(op.f('ix_storage_files_video_id'), 'storage_files', ['video_id'], unique=False)
    op.create_index('idx_storage_files_backend_category', 'storage_files', ['storage_backend', 'file_category'], unique=False)
    op.create_index('idx_storage_files_expires_temp', 'storage_files', ['expires_at', 'is_temporary'], unique=False)
    op.create_index('idx_storage_files_job_category', 'storage_files', ['job_id', 'file_category'], unique=False)
    op.create_index('idx_storage_files_path_backend', 'storage_files', ['file_path', 'storage_backend'], unique=False)
    op.create_index('idx_storage_files_type_access', 'storage_files', ['file_type', 'access_level'], unique=False)
    op.create_index('idx_storage_files_video_stage', 'storage_files', ['video_id', 'processing_stage'], unique=False)


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table('storage_files')
    op.drop_table('audit_logs')
    op.drop_table('video_metadata')
    op.drop_table('jobs')
    op.drop_table('users')
    
    # Drop enums
    op.execute('DROP TYPE IF EXISTS storagebackend')
    op.execute('DROP TYPE IF EXISTS accesslevel')
    op.execute('DROP TYPE IF EXISTS auditaction')
    op.execute('DROP TYPE IF EXISTS jobpriority')
    op.execute('DROP TYPE IF EXISTS jobstatus')
    op.execute('DROP TYPE IF EXISTS userrole')