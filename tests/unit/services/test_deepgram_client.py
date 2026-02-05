"""Tests for DeepgramClient."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.services.deepgram_client import (
    DeepgramClient,
    DeepgramError,
    Segment,
    TranscriptionResult,
    Word,
)


@pytest.fixture
def mock_settings() -> MagicMock:
    """Create mock settings."""
    settings = MagicMock()
    settings.deepgram_api_key = "test-api-key"
    return settings


@pytest.fixture
def client(mock_settings: MagicMock) -> DeepgramClient:
    """Create DeepgramClient with mock settings."""
    return DeepgramClient(settings=mock_settings)


@pytest.fixture
def mock_http_client() -> MagicMock:
    """Create a mock HTTP client."""
    return MagicMock()


@pytest.fixture
def sample_response() -> dict:
    """Create a sample Deepgram API response."""
    return {
        "metadata": {
            "duration": 10.5,
            "language": "en",
        },
        "results": {
            "channels": [
                {
                    "alternatives": [
                        {
                            "transcript": "Hello how are you today",
                            "confidence": 0.95,
                            "words": [
                                {
                                    "word": "Hello",
                                    "start": 0.0,
                                    "end": 0.5,
                                    "confidence": 0.98,
                                    "speaker": 0,
                                },
                                {
                                    "word": "how",
                                    "start": 0.6,
                                    "end": 0.8,
                                    "confidence": 0.96,
                                    "speaker": 0,
                                },
                                {
                                    "word": "are",
                                    "start": 0.9,
                                    "end": 1.0,
                                    "confidence": 0.97,
                                    "speaker": 0,
                                },
                                {
                                    "word": "you",
                                    "start": 1.1,
                                    "end": 1.3,
                                    "confidence": 0.99,
                                    "speaker": 1,
                                },
                                {
                                    "word": "today",
                                    "start": 1.4,
                                    "end": 1.8,
                                    "confidence": 0.95,
                                    "speaker": 1,
                                },
                            ],
                        }
                    ]
                }
            ],
            "utterances": [
                {
                    "transcript": "Hello how are",
                    "start": 0.0,
                    "end": 1.0,
                    "speaker": 0,
                    "confidence": 0.97,
                    "words": [
                        {
                            "word": "Hello",
                            "start": 0.0,
                            "end": 0.5,
                            "confidence": 0.98,
                            "speaker": 0,
                        },
                        {
                            "word": "how",
                            "start": 0.6,
                            "end": 0.8,
                            "confidence": 0.96,
                            "speaker": 0,
                        },
                        {
                            "word": "are",
                            "start": 0.9,
                            "end": 1.0,
                            "confidence": 0.97,
                            "speaker": 0,
                        },
                    ],
                },
                {
                    "transcript": "you today",
                    "start": 1.1,
                    "end": 1.8,
                    "speaker": 1,
                    "confidence": 0.97,
                    "words": [
                        {
                            "word": "you",
                            "start": 1.1,
                            "end": 1.3,
                            "confidence": 0.99,
                            "speaker": 1,
                        },
                        {
                            "word": "today",
                            "start": 1.4,
                            "end": 1.8,
                            "confidence": 0.95,
                            "speaker": 1,
                        },
                    ],
                },
            ],
        },
    }


class TestWord:
    """Tests for Word dataclass."""

    def test_create_word(self) -> None:
        """Test creating a Word."""
        word = Word(
            word="hello",
            start=0.0,
            end=0.5,
            confidence=0.95,
            speaker=0,
        )

        assert word.word == "hello"
        assert word.start == 0.0
        assert word.end == 0.5
        assert word.confidence == 0.95
        assert word.speaker == 0


class TestSegment:
    """Tests for Segment dataclass."""

    def test_create_segment(self) -> None:
        """Test creating a Segment."""
        segment = Segment(
            text="Hello there",
            start_time=0.0,
            end_time=1.0,
            speaker="Speaker 0",
            confidence=0.95,
        )

        assert segment.text == "Hello there"
        assert segment.speaker == "Speaker 0"

    def test_to_dict(self) -> None:
        """Test converting to dict."""
        word = Word(word="hello", start=0.0, end=0.5, confidence=0.95, speaker=0)
        segment = Segment(
            text="hello",
            start_time=0.0,
            end_time=0.5,
            speaker="Speaker 0",
            confidence=0.95,
            words=[word],
        )

        result = segment.to_dict()

        assert result["text"] == "hello"
        assert result["start_time"] == 0.0
        assert result["end_time"] == 0.5
        assert result["speaker"] == "Speaker 0"
        assert len(result["words"]) == 1


class TestDeepgramClientInit:
    """Tests for DeepgramClient initialization."""

    def test_init_with_settings(self, mock_settings: MagicMock) -> None:
        """Test client initialization with settings."""
        client = DeepgramClient(settings=mock_settings)
        assert client.settings == mock_settings

    def test_client_lazy_init(self, client: DeepgramClient) -> None:
        """Test HTTP client is lazily initialized."""
        assert client._client is None
        _ = client.client
        assert client._client is not None


class TestTranscribeFile:
    """Tests for transcribe_file method."""

    async def test_successful_transcription(
        self,
        client: DeepgramClient,
        mock_http_client: MagicMock,
        sample_response: dict,
    ) -> None:
        """Test successful transcription."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_response
        mock_http_client.post = AsyncMock(return_value=mock_response)

        # Set mock client directly
        client._client = mock_http_client

        result = await client.transcribe_file(
            audio_data=b"fake audio data",
            content_type="audio/mpeg",
        )

        assert isinstance(result, TranscriptionResult)
        assert result.full_text == "Hello how are you today"
        assert len(result.segments) == 2
        assert result.duration_seconds == 10.5
        assert result.word_count == 5

    async def test_transcription_with_diarization(
        self,
        client: DeepgramClient,
        mock_http_client: MagicMock,
        sample_response: dict,
    ) -> None:
        """Test transcription with speaker diarization."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_response
        mock_http_client.post = AsyncMock(return_value=mock_response)

        client._client = mock_http_client

        result = await client.transcribe_file(
            audio_data=b"fake audio data",
            enable_diarization=True,
        )

        # Check diarize param was passed
        call_kwargs = mock_http_client.post.call_args.kwargs
        assert "diarize" in call_kwargs["params"]

        # Check speakers are labeled
        assert result.segments[0].speaker == "Speaker 0"
        assert result.segments[1].speaker == "Speaker 1"

    async def test_retry_on_rate_limit(
        self,
        client: DeepgramClient,
        mock_http_client: MagicMock,
        sample_response: dict,
    ) -> None:
        """Test retry on 429 rate limit."""
        rate_limit_response = MagicMock()
        rate_limit_response.status_code = 429
        rate_limit_response.headers = {"Retry-After": "0"}

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = sample_response

        mock_http_client.post = AsyncMock(
            side_effect=[rate_limit_response, success_response]
        )
        client._client = mock_http_client

        result = await client.transcribe_file(audio_data=b"fake audio data")

        assert result.full_text == "Hello how are you today"
        assert mock_http_client.post.call_count == 2

    async def test_retry_on_server_error(
        self,
        client: DeepgramClient,
        mock_http_client: MagicMock,
        sample_response: dict,
    ) -> None:
        """Test retry on 5xx server error."""
        # Reduce retry delay for testing
        client.RETRY_DELAY = 0.01

        server_error_response = MagicMock()
        server_error_response.status_code = 500
        server_error_response.text = "Internal Server Error"

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = sample_response

        mock_http_client.post = AsyncMock(
            side_effect=[server_error_response, success_response]
        )
        client._client = mock_http_client

        result = await client.transcribe_file(audio_data=b"fake audio data")

        assert result.full_text == "Hello how are you today"

    async def test_raises_on_client_error(
        self,
        client: DeepgramClient,
        mock_http_client: MagicMock,
    ) -> None:
        """Test DeepgramError raised on 4xx errors."""
        error_response = MagicMock()
        error_response.status_code = 400
        error_response.text = "Bad Request"

        mock_http_client.post = AsyncMock(return_value=error_response)
        client._client = mock_http_client

        with pytest.raises(DeepgramError) as exc_info:
            await client.transcribe_file(audio_data=b"fake audio data")

        assert exc_info.value.status_code == 400

    async def test_raises_after_max_retries(
        self,
        client: DeepgramClient,
        mock_http_client: MagicMock,
    ) -> None:
        """Test DeepgramError raised after max retries."""
        # Reduce retry delay for testing
        client.RETRY_DELAY = 0.01

        mock_http_client.post = AsyncMock(
            side_effect=httpx.TimeoutException("Timeout")
        )
        client._client = mock_http_client

        with pytest.raises(DeepgramError) as exc_info:
            await client.transcribe_file(audio_data=b"fake audio data")

        assert "3 attempts" in str(exc_info.value)


class TestParseResponse:
    """Tests for _parse_response method."""

    def test_parse_empty_response(self, client: DeepgramClient) -> None:
        """Test parsing empty response."""
        result = client._parse_response({})

        assert result.full_text == ""
        assert result.segments == []
        assert result.duration_seconds == 0.0

    def test_parse_response_without_utterances(
        self, client: DeepgramClient
    ) -> None:
        """Test parsing response without utterances (uses words)."""
        data = {
            "metadata": {"duration": 2.0},
            "results": {
                "channels": [
                    {
                        "alternatives": [
                            {
                                "transcript": "Hello world",
                                "confidence": 0.95,
                                "words": [
                                    {
                                        "word": "Hello",
                                        "start": 0.0,
                                        "end": 0.5,
                                        "confidence": 0.98,
                                        "speaker": 0,
                                    },
                                    {
                                        "word": "world",
                                        "start": 0.6,
                                        "end": 1.0,
                                        "confidence": 0.96,
                                        "speaker": 0,
                                    },
                                ],
                            }
                        ]
                    }
                ]
            },
        }

        result = client._parse_response(data)

        assert result.full_text == "Hello world"
        assert len(result.segments) == 1
        assert result.segments[0].speaker == "Speaker 0"

    def test_parse_response_speaker_change(self, client: DeepgramClient) -> None:
        """Test parsing response with speaker changes."""
        data = {
            "metadata": {"duration": 2.0},
            "results": {
                "channels": [
                    {
                        "alternatives": [
                            {
                                "transcript": "Hello Hi",
                                "confidence": 0.95,
                                "words": [
                                    {
                                        "word": "Hello",
                                        "start": 0.0,
                                        "end": 0.5,
                                        "confidence": 0.98,
                                        "speaker": 0,
                                    },
                                    {
                                        "word": "Hi",
                                        "start": 0.6,
                                        "end": 1.0,
                                        "confidence": 0.96,
                                        "speaker": 1,
                                    },
                                ],
                            }
                        ]
                    }
                ]
            },
        }

        result = client._parse_response(data)

        # Should create separate segments for each speaker
        assert len(result.segments) == 2
        assert result.segments[0].speaker == "Speaker 0"
        assert result.segments[0].text == "Hello"
        assert result.segments[1].speaker == "Speaker 1"
        assert result.segments[1].text == "Hi"


class TestCloseClient:
    """Tests for close method."""

    async def test_close_client(self, client: DeepgramClient) -> None:
        """Test closing the HTTP client."""
        # Initialize the client
        _ = client.client
        assert client._client is not None

        # Mock aclose
        client._client.aclose = AsyncMock()  # type: ignore[method-assign]

        await client.close()

        assert client._client is None

    async def test_close_not_initialized(self, client: DeepgramClient) -> None:
        """Test closing when client not initialized."""
        assert client._client is None
        await client.close()  # Should not raise
        assert client._client is None
