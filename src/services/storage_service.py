"""Storage service for S3-compatible (MinIO) file storage."""

import io
import uuid
from datetime import timedelta

from minio import Minio
from minio.error import S3Error

from src.core.config import Settings, get_settings
from src.core.exceptions import AppError


class StorageError(AppError):
    """Storage operation error."""

    def __init__(self, detail: str, operation: str = "storage") -> None:
        super().__init__(
            title="Storage Error",
            detail=detail,
            status_code=500,
            error_type=f"about:blank#storage-{operation}-error",
        )


class StorageService:
    """Service for interacting with S3-compatible storage (MinIO)."""

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize storage service with settings.

        Args:
            settings: Application settings. If None, loads from environment.
        """
        self.settings = settings or get_settings()
        self._client: Minio | None = None

    @property
    def client(self) -> Minio:
        """Get or create MinIO client (lazy initialization)."""
        if self._client is None:
            self._client = Minio(
                endpoint=self.settings.minio_endpoint,
                access_key=self.settings.minio_access_key,
                secret_key=self.settings.minio_secret_key,
                secure=self.settings.minio_secure,
            )
        return self._client

    @property
    def bucket_name(self) -> str:
        """Get the configured bucket name."""
        return self.settings.minio_bucket

    async def ensure_bucket_exists(self) -> None:
        """Ensure the storage bucket exists, creating it if necessary.

        Raises:
            StorageError: If bucket creation fails
        """
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
        except S3Error as e:
            raise StorageError(
                detail=f"Failed to ensure bucket exists: {e}",
                operation="bucket-create",
            ) from e

    def generate_key(
        self,
        filename: str,
        prefix: str = "recordings",
    ) -> str:
        """Generate a unique S3 key for a file.

        Args:
            filename: Original filename
            prefix: Key prefix (folder path)

        Returns:
            Unique S3 key in format: prefix/uuid-filename
        """
        unique_id = uuid.uuid4().hex[:12]
        # Sanitize filename
        safe_filename = "".join(
            c if c.isalnum() or c in ".-_" else "_" for c in filename
        )
        return f"{prefix}/{unique_id}-{safe_filename}"

    async def upload_file(
        self,
        file_data: bytes | io.BytesIO,
        key: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload a file to storage.

        Args:
            file_data: File content as bytes or BytesIO
            key: S3 key (path) for the file
            content_type: MIME type of the file

        Returns:
            The S3 key where the file was stored

        Raises:
            StorageError: If upload fails
        """
        try:
            await self.ensure_bucket_exists()

            if isinstance(file_data, bytes):
                file_data = io.BytesIO(file_data)

            file_data.seek(0, 2)  # Seek to end
            file_size = file_data.tell()
            file_data.seek(0)  # Seek back to beginning

            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=key,
                data=file_data,
                length=file_size,
                content_type=content_type,
            )

            return key

        except S3Error as e:
            raise StorageError(
                detail=f"Failed to upload file: {e}",
                operation="upload",
            ) from e

    async def get_presigned_url(
        self,
        key: str,
        expires: timedelta = timedelta(hours=1),
    ) -> str:
        """Get a presigned URL for temporary access to a file.

        Args:
            key: S3 key of the file
            expires: How long the URL should be valid

        Returns:
            Presigned URL for accessing the file

        Raises:
            StorageError: If URL generation fails
        """
        try:
            url = self.client.presigned_get_object(
                bucket_name=self.bucket_name,
                object_name=key,
                expires=expires,
            )
            return url

        except S3Error as e:
            raise StorageError(
                detail=f"Failed to generate presigned URL: {e}",
                operation="presign",
            ) from e

    async def delete_file(self, key: str) -> bool:
        """Delete a file from storage.

        Args:
            key: S3 key of the file to delete

        Returns:
            True if file was deleted, False if file didn't exist

        Raises:
            StorageError: If deletion fails
        """
        try:
            # Check if object exists first
            try:
                self.client.stat_object(self.bucket_name, key)
            except S3Error as e:
                if e.code == "NoSuchKey":
                    return False
                raise

            self.client.remove_object(self.bucket_name, key)
            return True

        except S3Error as e:
            raise StorageError(
                detail=f"Failed to delete file: {e}",
                operation="delete",
            ) from e

    async def file_exists(self, key: str) -> bool:
        """Check if a file exists in storage.

        Args:
            key: S3 key of the file

        Returns:
            True if file exists, False otherwise

        Raises:
            StorageError: If check fails
        """
        try:
            self.client.stat_object(self.bucket_name, key)
            return True
        except S3Error as e:
            if e.code == "NoSuchKey":
                return False
            raise StorageError(
                detail=f"Failed to check file existence: {e}",
                operation="stat",
            ) from e

    async def get_file_size(self, key: str) -> int | None:
        """Get the size of a file in storage.

        Args:
            key: S3 key of the file

        Returns:
            File size in bytes, or None if file doesn't exist

        Raises:
            StorageError: If operation fails
        """
        try:
            stat = self.client.stat_object(self.bucket_name, key)
            return stat.size
        except S3Error as e:
            if e.code == "NoSuchKey":
                return None
            raise StorageError(
                detail=f"Failed to get file size: {e}",
                operation="stat",
            ) from e
