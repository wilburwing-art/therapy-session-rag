"""Tests for StorageService."""

import io
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from minio.error import S3Error

from src.services.storage_service import StorageError, StorageService


@pytest.fixture
def mock_settings() -> MagicMock:
    """Create mock settings."""
    settings = MagicMock()
    settings.minio_endpoint = "localhost:9000"
    settings.minio_access_key = "minioadmin"
    settings.minio_secret_key = "minioadmin"
    settings.minio_bucket = "test-bucket"
    settings.minio_secure = False
    return settings


@pytest.fixture
def mock_minio_client() -> MagicMock:
    """Create mock MinIO client."""
    return MagicMock()


@pytest.fixture
def storage_service(
    mock_settings: MagicMock, mock_minio_client: MagicMock
) -> StorageService:
    """Create StorageService with mocked client."""
    service = StorageService(settings=mock_settings)
    service._client = mock_minio_client
    return service


class TestStorageServiceInit:
    """Tests for StorageService initialization."""

    def test_init_with_settings(self, mock_settings: MagicMock) -> None:
        """Test service can be initialized with settings."""
        service = StorageService(settings=mock_settings)
        assert service.settings == mock_settings

    def test_bucket_name_from_settings(
        self, mock_settings: MagicMock
    ) -> None:
        """Test bucket name is retrieved from settings."""
        service = StorageService(settings=mock_settings)
        assert service.bucket_name == "test-bucket"


class TestGenerateKey:
    """Tests for generate_key method."""

    def test_generates_unique_keys(
        self, storage_service: StorageService
    ) -> None:
        """Test that generated keys are unique."""
        key1 = storage_service.generate_key("file.mp3")
        key2 = storage_service.generate_key("file.mp3")
        assert key1 != key2

    def test_includes_prefix(self, storage_service: StorageService) -> None:
        """Test that key includes prefix."""
        key = storage_service.generate_key("file.mp3", prefix="audio")
        assert key.startswith("audio/")

    def test_sanitizes_filename(
        self, storage_service: StorageService
    ) -> None:
        """Test that special characters in filename are sanitized."""
        key = storage_service.generate_key("file with spaces!@#.mp3")
        # Should not contain spaces or special characters
        filename_part = key.split("/")[-1]
        assert " " not in filename_part
        assert "!" not in filename_part
        assert "@" not in filename_part


class TestEnsureBucketExists:
    """Tests for ensure_bucket_exists method."""

    async def test_creates_bucket_if_not_exists(
        self, storage_service: StorageService, mock_minio_client: MagicMock
    ) -> None:
        """Test bucket is created if it doesn't exist."""
        mock_minio_client.bucket_exists.return_value = False

        await storage_service.ensure_bucket_exists()

        mock_minio_client.make_bucket.assert_called_once_with("test-bucket")

    async def test_skips_creation_if_exists(
        self, storage_service: StorageService, mock_minio_client: MagicMock
    ) -> None:
        """Test bucket creation is skipped if it exists."""
        mock_minio_client.bucket_exists.return_value = True

        await storage_service.ensure_bucket_exists()

        mock_minio_client.make_bucket.assert_not_called()

    async def test_raises_storage_error_on_failure(
        self, storage_service: StorageService, mock_minio_client: MagicMock
    ) -> None:
        """Test StorageError is raised on failure."""
        mock_minio_client.bucket_exists.side_effect = S3Error(
            code="InternalError",
            message="Server error",
            resource="bucket",
            request_id="123",
            host_id="host",
            response=None,
        )

        with pytest.raises(StorageError):
            await storage_service.ensure_bucket_exists()


class TestUploadFile:
    """Tests for upload_file method."""

    async def test_upload_bytes(
        self, storage_service: StorageService, mock_minio_client: MagicMock
    ) -> None:
        """Test uploading bytes."""
        mock_minio_client.bucket_exists.return_value = True
        file_data = b"test audio content"

        result = await storage_service.upload_file(
            file_data=file_data,
            key="recordings/test.mp3",
            content_type="audio/mpeg",
        )

        assert result == "recordings/test.mp3"
        mock_minio_client.put_object.assert_called_once()

    async def test_upload_bytesio(
        self, storage_service: StorageService, mock_minio_client: MagicMock
    ) -> None:
        """Test uploading BytesIO."""
        mock_minio_client.bucket_exists.return_value = True
        file_data = io.BytesIO(b"test audio content")

        result = await storage_service.upload_file(
            file_data=file_data,
            key="recordings/test.mp3",
        )

        assert result == "recordings/test.mp3"

    async def test_raises_storage_error_on_upload_failure(
        self, storage_service: StorageService, mock_minio_client: MagicMock
    ) -> None:
        """Test StorageError is raised on upload failure."""
        mock_minio_client.bucket_exists.return_value = True
        mock_minio_client.put_object.side_effect = S3Error(
            code="InternalError",
            message="Upload failed",
            resource="object",
            request_id="123",
            host_id="host",
            response=None,
        )

        with pytest.raises(StorageError):
            await storage_service.upload_file(
                file_data=b"test",
                key="test.mp3",
            )


class TestGetPresignedUrl:
    """Tests for get_presigned_url method."""

    async def test_returns_presigned_url(
        self, storage_service: StorageService, mock_minio_client: MagicMock
    ) -> None:
        """Test presigned URL is returned."""
        expected_url = "https://minio.example.com/bucket/file?signature=abc"
        mock_minio_client.presigned_get_object.return_value = expected_url

        result = await storage_service.get_presigned_url("recordings/test.mp3")

        assert result == expected_url

    async def test_custom_expiry(
        self, storage_service: StorageService, mock_minio_client: MagicMock
    ) -> None:
        """Test custom expiry time is passed."""
        mock_minio_client.presigned_get_object.return_value = "url"
        expires = timedelta(hours=24)

        await storage_service.get_presigned_url("test.mp3", expires=expires)

        mock_minio_client.presigned_get_object.assert_called_once_with(
            bucket_name="test-bucket",
            object_name="test.mp3",
            expires=expires,
        )

    async def test_raises_storage_error_on_failure(
        self, storage_service: StorageService, mock_minio_client: MagicMock
    ) -> None:
        """Test StorageError is raised on failure."""
        mock_minio_client.presigned_get_object.side_effect = S3Error(
            code="NoSuchKey",
            message="Key not found",
            resource="object",
            request_id="123",
            host_id="host",
            response=None,
        )

        with pytest.raises(StorageError):
            await storage_service.get_presigned_url("nonexistent.mp3")


class TestDeleteFile:
    """Tests for delete_file method."""

    async def test_deletes_existing_file(
        self, storage_service: StorageService, mock_minio_client: MagicMock
    ) -> None:
        """Test existing file is deleted."""
        mock_minio_client.stat_object.return_value = MagicMock()

        result = await storage_service.delete_file("recordings/test.mp3")

        assert result is True
        mock_minio_client.remove_object.assert_called_once()

    async def test_returns_false_for_nonexistent_file(
        self, storage_service: StorageService, mock_minio_client: MagicMock
    ) -> None:
        """Test returns False for nonexistent file."""
        error = S3Error(
            code="NoSuchKey",
            message="Key not found",
            resource="object",
            request_id="123",
            host_id="host",
            response=None,
        )
        mock_minio_client.stat_object.side_effect = error

        result = await storage_service.delete_file("nonexistent.mp3")

        assert result is False
        mock_minio_client.remove_object.assert_not_called()

    async def test_raises_storage_error_on_failure(
        self, storage_service: StorageService, mock_minio_client: MagicMock
    ) -> None:
        """Test StorageError is raised on other errors."""
        mock_minio_client.stat_object.return_value = MagicMock()
        mock_minio_client.remove_object.side_effect = S3Error(
            code="InternalError",
            message="Delete failed",
            resource="object",
            request_id="123",
            host_id="host",
            response=None,
        )

        with pytest.raises(StorageError):
            await storage_service.delete_file("test.mp3")


class TestFileExists:
    """Tests for file_exists method."""

    async def test_returns_true_for_existing_file(
        self, storage_service: StorageService, mock_minio_client: MagicMock
    ) -> None:
        """Test returns True for existing file."""
        mock_minio_client.stat_object.return_value = MagicMock()

        result = await storage_service.file_exists("recordings/test.mp3")

        assert result is True

    async def test_returns_false_for_nonexistent_file(
        self, storage_service: StorageService, mock_minio_client: MagicMock
    ) -> None:
        """Test returns False for nonexistent file."""
        error = S3Error(
            code="NoSuchKey",
            message="Key not found",
            resource="object",
            request_id="123",
            host_id="host",
            response=None,
        )
        mock_minio_client.stat_object.side_effect = error

        result = await storage_service.file_exists("nonexistent.mp3")

        assert result is False


class TestGetFileSize:
    """Tests for get_file_size method."""

    async def test_returns_file_size(
        self, storage_service: StorageService, mock_minio_client: MagicMock
    ) -> None:
        """Test returns file size."""
        stat = MagicMock()
        stat.size = 1024000
        mock_minio_client.stat_object.return_value = stat

        result = await storage_service.get_file_size("recordings/test.mp3")

        assert result == 1024000

    async def test_returns_none_for_nonexistent_file(
        self, storage_service: StorageService, mock_minio_client: MagicMock
    ) -> None:
        """Test returns None for nonexistent file."""
        error = S3Error(
            code="NoSuchKey",
            message="Key not found",
            resource="object",
            request_id="123",
            host_id="host",
            response=None,
        )
        mock_minio_client.stat_object.side_effect = error

        result = await storage_service.get_file_size("nonexistent.mp3")

        assert result is None
