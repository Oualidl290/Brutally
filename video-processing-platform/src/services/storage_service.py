"""
Storage service with multi-backend support.
Provides unified interface for local filesystem, S3, and MinIO storage.
"""

import asyncio
import hashlib
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, BinaryIO, AsyncIterator
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import mimetypes
import json

from ..config.logging_config import get_logger
from ..utils.exceptions import StorageError
from ..config import settings

logger = get_logger(__name__)


class StorageBackend(str, Enum):
    """Storage backend types."""
    LOCAL = "local"
    S3 = "s3"
    MINIO = "minio"


class FileAccessLevel(str, Enum):
    """File access levels."""
    PUBLIC = "public"
    PRIVATE = "private"
    AUTHENTICATED = "authenticated"


@dataclass
class StorageConfig:
    """Storage configuration."""
    backend: StorageBackend
    base_path: Optional[str] = None
    bucket_name: Optional[str] = None
    endpoint_url: Optional[str] = None
    access_key_id: Optional[str] = None
    secret_access_key: Optional[str] = None
    region: Optional[str] = None
    encryption_enabled: bool = False
    encryption_key: Optional[str] = None
    default_expiry_hours: int = 24
    max_file_size: int = 50 * 1024 * 1024 * 1024  # 50GB
    allowed_extensions: List[str] = field(default_factory=lambda: [
        '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v'
    ])


@dataclass
class FileMetadata:
    """File metadata information."""
    path: str
    size: int
    content_type: str
    created_at: datetime
    modified_at: datetime
    access_level: FileAccessLevel = FileAccessLevel.PRIVATE
    tags: Dict[str, str] = field(default_factory=dict)
    checksum: Optional[str] = None
    encryption_enabled: bool = False
    expiry_date: Optional[datetime] = None


@dataclass
class UploadResult:
    """File upload result."""
    path: str
    size: int
    checksum: str
    url: Optional[str] = None
    metadata: Optional[FileMetadata] = None


@dataclass
class DownloadResult:
    """File download result."""
    content: bytes
    metadata: FileMetadata
    url: Optional[str] = None


class StorageBackendInterface(ABC):
    """Abstract interface for storage backends."""
    
    def __init__(self, config: StorageConfig):
        self.config = config
        self.logger = get_logger(self.__class__.__name__)
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the storage backend."""
        pass
    
    @abstractmethod
    async def upload_file(
        self,
        file_path: Union[str, Path],
        content: Union[bytes, BinaryIO],
        metadata: Optional[Dict[str, Any]] = None,
        access_level: FileAccessLevel = FileAccessLevel.PRIVATE
    ) -> UploadResult:
        """Upload a file to storage."""
        pass
    
    @abstractmethod
    async def download_file(self, file_path: str) -> DownloadResult:
        """Download a file from storage."""
        pass
    
    @abstractmethod
    async def delete_file(self, file_path: str) -> bool:
        """Delete a file from storage."""
        pass
    
    @abstractmethod
    async def file_exists(self, file_path: str) -> bool:
        """Check if a file exists in storage."""
        pass
    
    @abstractmethod
    async def get_file_metadata(self, file_path: str) -> FileMetadata:
        """Get file metadata."""
        pass
    
    @abstractmethod
    async def list_files(
        self,
        prefix: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[FileMetadata]:
        """List files in storage."""
        pass
    
    @abstractmethod
    async def generate_presigned_url(
        self,
        file_path: str,
        expiry_hours: Optional[int] = None,
        method: str = "GET"
    ) -> str:
        """Generate a presigned URL for file access."""
        pass
    
    @abstractmethod
    async def copy_file(self, source_path: str, dest_path: str) -> bool:
        """Copy a file within storage."""
        pass
    
    @abstractmethod
    async def move_file(self, source_path: str, dest_path: str) -> bool:
        """Move a file within storage."""
        pass
    
    @abstractmethod
    async def get_storage_stats(self) -> Dict[str, Any]:
        """Get storage statistics."""
        pass


class LocalStorageBackend(StorageBackendInterface):
    """Local filesystem storage backend."""
    
    def __init__(self, config: StorageConfig):
        super().__init__(config)
        self.base_path = Path(config.base_path or settings.OUTPUT_DIR)
        self._metadata_cache: Dict[str, FileMetadata] = {}
    
    async def initialize(self) -> None:
        """Initialize local storage."""
        try:
            self.base_path.mkdir(parents=True, exist_ok=True)
            
            # Create metadata directory
            metadata_dir = self.base_path / ".metadata"
            metadata_dir.mkdir(exist_ok=True)
            
            self.logger.info(f"Local storage initialized at {self.base_path}")
            
        except Exception as e:
            raise StorageError(f"Failed to initialize local storage: {e}")
    
    async def upload_file(
        self,
        file_path: Union[str, Path],
        content: Union[bytes, BinaryIO],
        metadata: Optional[Dict[str, Any]] = None,
        access_level: FileAccessLevel = FileAccessLevel.PRIVATE
    ) -> UploadResult:
        """Upload file to local storage."""
        try:
            file_path = str(file_path)
            full_path = self.base_path / file_path
            
            # Ensure directory exists
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write file content
            if isinstance(content, bytes):
                full_path.write_bytes(content)
                file_size = len(content)
            else:
                # Handle file-like object
                with open(full_path, 'wb') as f:
                    if hasattr(content, 'read'):
                        data = content.read()
                        f.write(data)
                        file_size = len(data)
                    else:
                        # Assume it's already bytes
                        f.write(content)
                        file_size = len(content)
            
            # Calculate checksum
            checksum = self._calculate_checksum(full_path)
            
            # Create metadata
            file_metadata = FileMetadata(
                path=file_path,
                size=file_size,
                content_type=mimetypes.guess_type(file_path)[0] or 'application/octet-stream',
                created_at=datetime.utcnow(),
                modified_at=datetime.utcnow(),
                access_level=access_level,
                tags=metadata or {},
                checksum=checksum,
                encryption_enabled=self.config.encryption_enabled
            )
            
            # Save metadata
            await self._save_metadata(file_path, file_metadata)
            
            result = UploadResult(
                path=file_path,
                size=file_size,
                checksum=checksum,
                url=f"file://{full_path.absolute()}",
                metadata=file_metadata
            )
            
            self.logger.info(f"File uploaded to local storage: {file_path} ({file_size} bytes)")
            return result
            
        except Exception as e:
            raise StorageError(f"Failed to upload file to local storage: {e}")
    
    async def download_file(self, file_path: str) -> DownloadResult:
        """Download file from local storage."""
        try:
            full_path = self.base_path / file_path
            
            if not full_path.exists():
                raise StorageError(f"File not found: {file_path}")
            
            content = full_path.read_bytes()
            metadata = await self.get_file_metadata(file_path)
            
            return DownloadResult(
                content=content,
                metadata=metadata,
                url=f"file://{full_path.absolute()}"
            )
            
        except Exception as e:
            raise StorageError(f"Failed to download file from local storage: {e}")
    
    async def delete_file(self, file_path: str) -> bool:
        """Delete file from local storage."""
        try:
            full_path = self.base_path / file_path
            
            if full_path.exists():
                full_path.unlink()
                
                # Delete metadata
                await self._delete_metadata(file_path)
                
                self.logger.info(f"File deleted from local storage: {file_path}")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to delete file from local storage: {e}")
            return False
    
    async def file_exists(self, file_path: str) -> bool:
        """Check if file exists in local storage."""
        full_path = self.base_path / file_path
        return full_path.exists()
    
    async def get_file_metadata(self, file_path: str) -> FileMetadata:
        """Get file metadata from local storage."""
        try:
            # Try to load from metadata cache first
            if file_path in self._metadata_cache:
                return self._metadata_cache[file_path]
            
            # Try to load from metadata file
            metadata = await self._load_metadata(file_path)
            if metadata:
                return metadata
            
            # Generate metadata from file system
            full_path = self.base_path / file_path
            if not full_path.exists():
                raise StorageError(f"File not found: {file_path}")
            
            stat = full_path.stat()
            
            metadata = FileMetadata(
                path=file_path,
                size=stat.st_size,
                content_type=mimetypes.guess_type(file_path)[0] or 'application/octet-stream',
                created_at=datetime.fromtimestamp(stat.st_ctime),
                modified_at=datetime.fromtimestamp(stat.st_mtime),
                checksum=self._calculate_checksum(full_path)
            )
            
            # Cache metadata
            self._metadata_cache[file_path] = metadata
            
            return metadata
            
        except Exception as e:
            raise StorageError(f"Failed to get file metadata: {e}")
    
    async def list_files(
        self,
        prefix: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[FileMetadata]:
        """List files in local storage."""
        try:
            files = []
            search_path = self.base_path
            
            if prefix:
                search_path = self.base_path / prefix
            
            # Find all files
            if search_path.exists():
                for file_path in search_path.rglob('*'):
                    if file_path.is_file() and not file_path.name.startswith('.'):
                        relative_path = file_path.relative_to(self.base_path)
                        
                        try:
                            metadata = await self.get_file_metadata(str(relative_path))
                            files.append(metadata)
                            
                            if limit and len(files) >= limit:
                                break
                                
                        except Exception as e:
                            self.logger.warning(f"Failed to get metadata for {relative_path}: {e}")
            
            return files
            
        except Exception as e:
            raise StorageError(f"Failed to list files: {e}")
    
    async def generate_presigned_url(
        self,
        file_path: str,
        expiry_hours: Optional[int] = None,
        method: str = "GET"
    ) -> str:
        """Generate presigned URL for local file."""
        # For local storage, we'll generate a simple file URL
        # In a real implementation, you might want to use a web server
        full_path = self.base_path / file_path
        
        if not full_path.exists():
            raise StorageError(f"File not found: {file_path}")
        
        # Generate a simple file URL with expiry token
        expiry = expiry_hours or self.config.default_expiry_hours
        expiry_timestamp = int(time.time()) + (expiry * 3600)
        
        # Create a simple token (in production, use proper signing)
        token = hashlib.md5(f"{file_path}{expiry_timestamp}".encode()).hexdigest()
        
        return f"file://{full_path.absolute()}?token={token}&expires={expiry_timestamp}"
    
    async def copy_file(self, source_path: str, dest_path: str) -> bool:
        """Copy file within local storage."""
        try:
            source_full = self.base_path / source_path
            dest_full = self.base_path / dest_path
            
            if not source_full.exists():
                return False
            
            # Ensure destination directory exists
            dest_full.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy file
            import shutil
            shutil.copy2(source_full, dest_full)
            
            # Copy metadata
            source_metadata = await self.get_file_metadata(source_path)
            source_metadata.path = dest_path
            await self._save_metadata(dest_path, source_metadata)
            
            self.logger.info(f"File copied: {source_path} -> {dest_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to copy file: {e}")
            return False
    
    async def move_file(self, source_path: str, dest_path: str) -> bool:
        """Move file within local storage."""
        try:
            if await self.copy_file(source_path, dest_path):
                await self.delete_file(source_path)
                self.logger.info(f"File moved: {source_path} -> {dest_path}")
                return True
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to move file: {e}")
            return False
    
    async def get_storage_stats(self) -> Dict[str, Any]:
        """Get local storage statistics."""
        try:
            total_size = 0
            file_count = 0
            
            for file_path in self.base_path.rglob('*'):
                if file_path.is_file() and not file_path.name.startswith('.'):
                    total_size += file_path.stat().st_size
                    file_count += 1
            
            # Get disk usage
            import shutil
            disk_usage = shutil.disk_usage(self.base_path)
            
            return {
                "backend": "local",
                "base_path": str(self.base_path),
                "total_files": file_count,
                "total_size": total_size,
                "disk_total": disk_usage.total,
                "disk_used": disk_usage.used,
                "disk_free": disk_usage.free,
                "disk_usage_percent": (disk_usage.used / disk_usage.total) * 100
            }
            
        except Exception as e:
            raise StorageError(f"Failed to get storage stats: {e}")
    
    def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate MD5 checksum of file."""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    
    async def _save_metadata(self, file_path: str, metadata: FileMetadata):
        """Save file metadata."""
        metadata_dir = self.base_path / ".metadata"
        metadata_file = metadata_dir / f"{file_path.replace('/', '_')}.json"
        
        # Ensure metadata directory exists
        metadata_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert metadata to dict
        metadata_dict = {
            "path": metadata.path,
            "size": metadata.size,
            "content_type": metadata.content_type,
            "created_at": metadata.created_at.isoformat(),
            "modified_at": metadata.modified_at.isoformat(),
            "access_level": metadata.access_level.value,
            "tags": metadata.tags,
            "checksum": metadata.checksum,
            "encryption_enabled": metadata.encryption_enabled,
            "expiry_date": metadata.expiry_date.isoformat() if metadata.expiry_date else None
        }
        
        metadata_file.write_text(json.dumps(metadata_dict, indent=2))
        self._metadata_cache[file_path] = metadata
    
    async def _load_metadata(self, file_path: str) -> Optional[FileMetadata]:
        """Load file metadata."""
        try:
            metadata_dir = self.base_path / ".metadata"
            metadata_file = metadata_dir / f"{file_path.replace('/', '_')}.json"
            
            if not metadata_file.exists():
                return None
            
            metadata_dict = json.loads(metadata_file.read_text())
            
            metadata = FileMetadata(
                path=metadata_dict["path"],
                size=metadata_dict["size"],
                content_type=metadata_dict["content_type"],
                created_at=datetime.fromisoformat(metadata_dict["created_at"]),
                modified_at=datetime.fromisoformat(metadata_dict["modified_at"]),
                access_level=FileAccessLevel(metadata_dict["access_level"]),
                tags=metadata_dict["tags"],
                checksum=metadata_dict["checksum"],
                encryption_enabled=metadata_dict["encryption_enabled"],
                expiry_date=datetime.fromisoformat(metadata_dict["expiry_date"]) if metadata_dict["expiry_date"] else None
            )
            
            self._metadata_cache[file_path] = metadata
            return metadata
            
        except Exception as e:
            self.logger.warning(f"Failed to load metadata for {file_path}: {e}")
            return None
    
    async def _delete_metadata(self, file_path: str):
        """Delete file metadata."""
        try:
            metadata_dir = self.base_path / ".metadata"
            metadata_file = metadata_dir / f"{file_path.replace('/', '_')}.json"
            
            if metadata_file.exists():
                metadata_file.unlink()
            
            if file_path in self._metadata_cache:
                del self._metadata_cache[file_path]
                
        except Exception as e:
            self.logger.warning(f"Failed to delete metadata for {file_path}: {e}")

clas
s S3StorageBackend(StorageBackendInterface):
    """Amazon S3 storage backend."""
    
    def __init__(self, config: StorageConfig):
        super().__init__(config)
        self.s3_client = None
        self.bucket_name = config.bucket_name or settings.S3_BUCKET_NAME
    
    async def initialize(self) -> None:
        """Initialize S3 storage."""
        try:
            import boto3
            from botocore.exceptions import ClientError
            
            # Create S3 client
            self.s3_client = boto3.client(
                's3',
                endpoint_url=self.config.endpoint_url or settings.S3_ENDPOINT_URL,
                aws_access_key_id=self.config.access_key_id or settings.S3_ACCESS_KEY_ID,
                aws_secret_access_key=self.config.secret_access_key or settings.S3_SECRET_ACCESS_KEY,
                region_name=self.config.region or settings.S3_REGION
            )
            
            # Check if bucket exists, create if not
            try:
                self.s3_client.head_bucket(Bucket=self.bucket_name)
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    # Bucket doesn't exist, create it
                    self.s3_client.create_bucket(
                        Bucket=self.bucket_name,
                        CreateBucketConfiguration={'LocationConstraint': self.config.region or settings.S3_REGION}
                    )
                    self.logger.info(f"Created S3 bucket: {self.bucket_name}")
                else:
                    raise
            
            self.logger.info(f"S3 storage initialized with bucket: {self.bucket_name}")
            
        except ImportError:
            raise StorageError("boto3 package is required for S3 storage backend")
        except Exception as e:
            raise StorageError(f"Failed to initialize S3 storage: {e}")
    
    async def upload_file(
        self,
        file_path: Union[str, Path],
        content: Union[bytes, BinaryIO],
        metadata: Optional[Dict[str, Any]] = None,
        access_level: FileAccessLevel = FileAccessLevel.PRIVATE
    ) -> UploadResult:
        """Upload file to S3."""
        try:
            file_path = str(file_path)
            
            # Prepare metadata
            s3_metadata = metadata or {}
            s3_metadata.update({
                'access_level': access_level.value,
                'uploaded_at': datetime.utcnow().isoformat(),
                'encryption_enabled': str(self.config.encryption_enabled)
            })
            
            # Prepare upload arguments
            upload_args = {
                'Bucket': self.bucket_name,
                'Key': file_path,
                'Metadata': s3_metadata
            }
            
            # Set content type
            content_type = mimetypes.guess_type(file_path)[0] or 'application/octet-stream'
            upload_args['ContentType'] = content_type
            
            # Set ACL based on access level
            if access_level == FileAccessLevel.PUBLIC:
                upload_args['ACL'] = 'public-read'
            else:
                upload_args['ACL'] = 'private'
            
            # Add encryption if enabled
            if self.config.encryption_enabled:
                upload_args['ServerSideEncryption'] = 'AES256'
            
            # Upload file
            if isinstance(content, bytes):
                import io
                upload_args['Body'] = io.BytesIO(content)
                file_size = len(content)
            else:
                upload_args['Body'] = content
                # Try to get size
                if hasattr(content, 'seek') and hasattr(content, 'tell'):
                    current_pos = content.tell()
                    content.seek(0, 2)  # Seek to end
                    file_size = content.tell()
                    content.seek(current_pos)  # Restore position
                else:
                    file_size = 0
            
            # Perform upload
            self.s3_client.put_object(**upload_args)
            
            # Calculate checksum (ETag from S3)
            response = self.s3_client.head_object(Bucket=self.bucket_name, Key=file_path)
            checksum = response['ETag'].strip('"')
            
            # Create file metadata
            file_metadata = FileMetadata(
                path=file_path,
                size=file_size or response['ContentLength'],
                content_type=content_type,
                created_at=datetime.utcnow(),
                modified_at=response['LastModified'],
                access_level=access_level,
                tags=metadata or {},
                checksum=checksum,
                encryption_enabled=self.config.encryption_enabled
            )
            
            result = UploadResult(
                path=file_path,
                size=file_metadata.size,
                checksum=checksum,
                url=f"s3://{self.bucket_name}/{file_path}",
                metadata=file_metadata
            )
            
            self.logger.info(f"File uploaded to S3: {file_path} ({file_metadata.size} bytes)")
            return result
            
        except Exception as e:
            raise StorageError(f"Failed to upload file to S3: {e}")
    
    async def download_file(self, file_path: str) -> DownloadResult:
        """Download file from S3."""
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=file_path)
            content = response['Body'].read()
            
            # Create metadata
            metadata = FileMetadata(
                path=file_path,
                size=response['ContentLength'],
                content_type=response['ContentType'],
                created_at=response['LastModified'],
                modified_at=response['LastModified'],
                checksum=response['ETag'].strip('"'),
                tags=response.get('Metadata', {}),
                encryption_enabled=response.get('ServerSideEncryption') is not None
            )
            
            return DownloadResult(
                content=content,
                metadata=metadata,
                url=f"s3://{self.bucket_name}/{file_path}"
            )
            
        except Exception as e:
            raise StorageError(f"Failed to download file from S3: {e}")
    
    async def delete_file(self, file_path: str) -> bool:
        """Delete file from S3."""
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=file_path)
            self.logger.info(f"File deleted from S3: {file_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to delete file from S3: {e}")
            return False
    
    async def file_exists(self, file_path: str) -> bool:
        """Check if file exists in S3."""
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=file_path)
            return True
        except:
            return False
    
    async def get_file_metadata(self, file_path: str) -> FileMetadata:
        """Get file metadata from S3."""
        try:
            response = self.s3_client.head_object(Bucket=self.bucket_name, Key=file_path)
            
            metadata = FileMetadata(
                path=file_path,
                size=response['ContentLength'],
                content_type=response['ContentType'],
                created_at=response['LastModified'],
                modified_at=response['LastModified'],
                checksum=response['ETag'].strip('"'),
                tags=response.get('Metadata', {}),
                encryption_enabled=response.get('ServerSideEncryption') is not None
            )
            
            return metadata
            
        except Exception as e:
            raise StorageError(f"Failed to get file metadata from S3: {e}")
    
    async def list_files(
        self,
        prefix: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[FileMetadata]:
        """List files in S3."""
        try:
            list_args = {'Bucket': self.bucket_name}
            
            if prefix:
                list_args['Prefix'] = prefix
            
            if limit:
                list_args['MaxKeys'] = limit
            
            response = self.s3_client.list_objects_v2(**list_args)
            
            files = []
            for obj in response.get('Contents', []):
                metadata = FileMetadata(
                    path=obj['Key'],
                    size=obj['Size'],
                    content_type='application/octet-stream',  # S3 doesn't store this in list
                    created_at=obj['LastModified'],
                    modified_at=obj['LastModified'],
                    checksum=obj['ETag'].strip('"')
                )
                files.append(metadata)
            
            return files
            
        except Exception as e:
            raise StorageError(f"Failed to list files in S3: {e}")
    
    async def generate_presigned_url(
        self,
        file_path: str,
        expiry_hours: Optional[int] = None,
        method: str = "GET"
    ) -> str:
        """Generate presigned URL for S3 file."""
        try:
            expiry_seconds = (expiry_hours or self.config.default_expiry_hours) * 3600
            
            if method.upper() == "GET":
                url = self.s3_client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': self.bucket_name, 'Key': file_path},
                    ExpiresIn=expiry_seconds
                )
            elif method.upper() == "PUT":
                url = self.s3_client.generate_presigned_url(
                    'put_object',
                    Params={'Bucket': self.bucket_name, 'Key': file_path},
                    ExpiresIn=expiry_seconds
                )
            else:
                raise StorageError(f"Unsupported method: {method}")
            
            return url
            
        except Exception as e:
            raise StorageError(f"Failed to generate presigned URL: {e}")
    
    async def copy_file(self, source_path: str, dest_path: str) -> bool:
        """Copy file within S3."""
        try:
            copy_source = {'Bucket': self.bucket_name, 'Key': source_path}
            self.s3_client.copy_object(
                CopySource=copy_source,
                Bucket=self.bucket_name,
                Key=dest_path
            )
            
            self.logger.info(f"File copied in S3: {source_path} -> {dest_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to copy file in S3: {e}")
            return False
    
    async def move_file(self, source_path: str, dest_path: str) -> bool:
        """Move file within S3."""
        try:
            if await self.copy_file(source_path, dest_path):
                await self.delete_file(source_path)
                self.logger.info(f"File moved in S3: {source_path} -> {dest_path}")
                return True
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to move file in S3: {e}")
            return False
    
    async def get_storage_stats(self) -> Dict[str, Any]:
        """Get S3 storage statistics."""
        try:
            # List all objects to calculate stats
            paginator = self.s3_client.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(Bucket=self.bucket_name)
            
            total_size = 0
            file_count = 0
            
            for page in page_iterator:
                for obj in page.get('Contents', []):
                    total_size += obj['Size']
                    file_count += 1
            
            return {
                "backend": "s3",
                "bucket_name": self.bucket_name,
                "total_files": file_count,
                "total_size": total_size,
                "region": self.config.region or settings.S3_REGION
            }
            
        except Exception as e:
            raise StorageError(f"Failed to get S3 storage stats: {e}")


class MinIOStorageBackend(S3StorageBackend):
    """MinIO storage backend (inherits from S3 since MinIO is S3-compatible)."""
    
    def __init__(self, config: StorageConfig):
        super().__init__(config)
        # MinIO-specific configuration can be added here
    
    async def initialize(self) -> None:
        """Initialize MinIO storage."""
        try:
            import boto3
            from botocore.exceptions import ClientError
            
            # Create MinIO client (S3-compatible)
            self.s3_client = boto3.client(
                's3',
                endpoint_url=self.config.endpoint_url or settings.S3_ENDPOINT_URL,
                aws_access_key_id=self.config.access_key_id or settings.S3_ACCESS_KEY_ID,
                aws_secret_access_key=self.config.secret_access_key or settings.S3_SECRET_ACCESS_KEY,
                region_name=self.config.region or 'us-east-1'  # MinIO default
            )
            
            # Check if bucket exists, create if not
            try:
                self.s3_client.head_bucket(Bucket=self.bucket_name)
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    # Bucket doesn't exist, create it
                    self.s3_client.create_bucket(Bucket=self.bucket_name)
                    self.logger.info(f"Created MinIO bucket: {self.bucket_name}")
                else:
                    raise
            
            self.logger.info(f"MinIO storage initialized with bucket: {self.bucket_name}")
            
        except ImportError:
            raise StorageError("boto3 package is required for MinIO storage backend")
        except Exception as e:
            raise StorageError(f"Failed to initialize MinIO storage: {e}")
    
    async def get_storage_stats(self) -> Dict[str, Any]:
        """Get MinIO storage statistics."""
        stats = await super().get_storage_stats()
        stats["backend"] = "minio"
        stats["endpoint_url"] = self.config.endpoint_url
        return stats


class StorageService:
    """Main storage service with multi-backend support."""
    
    def __init__(self, config: Optional[StorageConfig] = None):
        self.config = config or self._create_default_config()
        self.backend: Optional[StorageBackendInterface] = None
        self.logger = get_logger(__name__)
        
        # Retention policies
        self._retention_policies: Dict[str, timedelta] = {
            'temp': timedelta(hours=24),
            'processed': timedelta(days=30),
            'archive': timedelta(days=365)
        }
    
    def _create_default_config(self) -> StorageConfig:
        """Create default storage configuration from settings."""
        backend = StorageBackend(settings.STORAGE_BACKEND)
        
        return StorageConfig(
            backend=backend,
            base_path=str(settings.OUTPUT_DIR) if backend == StorageBackend.LOCAL else None,
            bucket_name=settings.S3_BUCKET_NAME if hasattr(settings, 'S3_BUCKET_NAME') else None,
            endpoint_url=settings.S3_ENDPOINT_URL if hasattr(settings, 'S3_ENDPOINT_URL') else None,
            access_key_id=settings.S3_ACCESS_KEY_ID if hasattr(settings, 'S3_ACCESS_KEY_ID') else None,
            secret_access_key=settings.S3_SECRET_ACCESS_KEY if hasattr(settings, 'S3_SECRET_ACCESS_KEY') else None,
            region=settings.S3_REGION if hasattr(settings, 'S3_REGION') else None,
            encryption_enabled=True,
            default_expiry_hours=24
        )
    
    async def initialize(self) -> None:
        """Initialize the storage service."""
        try:
            # Create appropriate backend
            if self.config.backend == StorageBackend.LOCAL:
                self.backend = LocalStorageBackend(self.config)
            elif self.config.backend == StorageBackend.S3:
                self.backend = S3StorageBackend(self.config)
            elif self.config.backend == StorageBackend.MINIO:
                self.backend = MinIOStorageBackend(self.config)
            else:
                raise StorageError(f"Unsupported storage backend: {self.config.backend}")
            
            # Initialize backend
            await self.backend.initialize()
            
            self.logger.info(f"Storage service initialized with {self.config.backend.value} backend")
            
        except Exception as e:
            raise StorageError(f"Failed to initialize storage service: {e}")
    
    async def upload_file(
        self,
        file_path: Union[str, Path],
        content: Union[bytes, BinaryIO, Path],
        metadata: Optional[Dict[str, Any]] = None,
        access_level: FileAccessLevel = FileAccessLevel.PRIVATE,
        category: Optional[str] = None
    ) -> UploadResult:
        """Upload a file to storage."""
        if not self.backend:
            raise StorageError("Storage service not initialized")
        
        # Handle Path input for content
        if isinstance(content, Path):
            if not content.exists():
                raise StorageError(f"Source file not found: {content}")
            content = content.read_bytes()
        
        # Add category to metadata
        if metadata is None:
            metadata = {}
        if category:
            metadata['category'] = category
        
        # Set expiry based on category
        if category and category in self._retention_policies:
            expiry_date = datetime.utcnow() + self._retention_policies[category]
            metadata['expiry_date'] = expiry_date.isoformat()
        
        return await self.backend.upload_file(file_path, content, metadata, access_level)
    
    async def download_file(self, file_path: str) -> DownloadResult:
        """Download a file from storage."""
        if not self.backend:
            raise StorageError("Storage service not initialized")
        
        return await self.backend.download_file(file_path)
    
    async def delete_file(self, file_path: str) -> bool:
        """Delete a file from storage."""
        if not self.backend:
            raise StorageError("Storage service not initialized")
        
        return await self.backend.delete_file(file_path)
    
    async def file_exists(self, file_path: str) -> bool:
        """Check if a file exists in storage."""
        if not self.backend:
            raise StorageError("Storage service not initialized")
        
        return await self.backend.file_exists(file_path)
    
    async def get_file_metadata(self, file_path: str) -> FileMetadata:
        """Get file metadata."""
        if not self.backend:
            raise StorageError("Storage service not initialized")
        
        return await self.backend.get_file_metadata(file_path)
    
    async def list_files(
        self,
        prefix: Optional[str] = None,
        limit: Optional[int] = None,
        category: Optional[str] = None
    ) -> List[FileMetadata]:
        """List files in storage."""
        if not self.backend:
            raise StorageError("Storage service not initialized")
        
        files = await self.backend.list_files(prefix, limit)
        
        # Filter by category if specified
        if category:
            files = [f for f in files if f.tags.get('category') == category]
        
        return files
    
    async def generate_secure_url(
        self,
        file_path: str,
        expiry_hours: Optional[int] = None,
        method: str = "GET"
    ) -> str:
        """Generate a secure URL for file access."""
        if not self.backend:
            raise StorageError("Storage service not initialized")
        
        return await self.backend.generate_presigned_url(file_path, expiry_hours, method)
    
    async def copy_file(self, source_path: str, dest_path: str) -> bool:
        """Copy a file within storage."""
        if not self.backend:
            raise StorageError("Storage service not initialized")
        
        return await self.backend.copy_file(source_path, dest_path)
    
    async def move_file(self, source_path: str, dest_path: str) -> bool:
        """Move a file within storage."""
        if not self.backend:
            raise StorageError("Storage service not initialized")
        
        return await self.backend.move_file(source_path, dest_path)
    
    async def cleanup_expired_files(self) -> Dict[str, int]:
        """Clean up expired files based on retention policies."""
        if not self.backend:
            raise StorageError("Storage service not initialized")
        
        try:
            cleanup_stats = {"deleted": 0, "errors": 0, "total_checked": 0}
            current_time = datetime.utcnow()
            
            # Get all files
            all_files = await self.backend.list_files()
            cleanup_stats["total_checked"] = len(all_files)
            
            for file_metadata in all_files:
                try:
                    should_delete = False
                    
                    # Check explicit expiry date
                    if file_metadata.expiry_date and file_metadata.expiry_date < current_time:
                        should_delete = True
                    
                    # Check category-based retention
                    elif 'category' in file_metadata.tags:
                        category = file_metadata.tags['category']
                        if category in self._retention_policies:
                            retention_period = self._retention_policies[category]
                            if file_metadata.created_at + retention_period < current_time:
                                should_delete = True
                    
                    if should_delete:
                        success = await self.backend.delete_file(file_metadata.path)
                        if success:
                            cleanup_stats["deleted"] += 1
                            self.logger.info(f"Deleted expired file: {file_metadata.path}")
                        else:
                            cleanup_stats["errors"] += 1
                
                except Exception as e:
                    cleanup_stats["errors"] += 1
                    self.logger.error(f"Error processing file {file_metadata.path}: {e}")
            
            self.logger.info(
                f"Cleanup completed: {cleanup_stats['deleted']} deleted, "
                f"{cleanup_stats['errors']} errors, "
                f"{cleanup_stats['total_checked']} total checked"
            )
            
            return cleanup_stats
            
        except Exception as e:
            raise StorageError(f"Failed to cleanup expired files: {e}")
    
    async def get_storage_statistics(self) -> Dict[str, Any]:
        """Get storage statistics."""
        if not self.backend:
            raise StorageError("Storage service not initialized")
        
        return await self.backend.get_storage_stats()
    
    def set_retention_policy(self, category: str, retention_period: timedelta):
        """Set retention policy for a file category."""
        self._retention_policies[category] = retention_period
        self.logger.info(f"Set retention policy for '{category}': {retention_period}")
    
    def get_retention_policies(self) -> Dict[str, timedelta]:
        """Get all retention policies."""
        return self._retention_policies.copy()


# Utility functions

def create_storage_service(backend: Optional[StorageBackend] = None) -> StorageService:
    """Factory function to create a storage service."""
    if backend:
        config = StorageConfig(backend=backend)
        return StorageService(config)
    else:
        return StorageService()


async def upload_video_file(
    storage: StorageService,
    video_path: Path,
    category: str = "processed"
) -> UploadResult:
    """Convenience function to upload a video file."""
    if not video_path.exists():
        raise StorageError(f"Video file not found: {video_path}")
    
    # Generate storage path
    storage_path = f"{category}/{video_path.name}"
    
    return await storage.upload_file(
        storage_path,
        video_path,
        metadata={"original_name": video_path.name, "file_type": "video"},
        category=category
    )