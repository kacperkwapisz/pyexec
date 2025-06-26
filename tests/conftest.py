# This file is intentionally left blank.
# It is used by pytest to discover and load plugins.

import os
import pytest
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

# Set the test API key as an environment variable *before* the app is imported by tests
TEST_API_KEY = "test-api-key"
os.environ["API_KEY"] = TEST_API_KEY
os.environ["API_KEY_NAME"] = "X-API-Key"


@pytest.fixture(scope="session", autouse=True)
def mock_docker_globally():
    """
    Globally mocks docker.from_env() for the entire test session.
    This runs before any modules are even imported.
    """
    with patch("docker.from_env") as mock_from_env:
        # Configure the mock to return another mock
        mock_docker_client = MagicMock()
        mock_from_env.return_value = mock_docker_client
        yield mock_docker_client


@pytest.fixture(scope="module")
def client():
    """
    Provides a configured TestClient for the application.
    This client will be shared across all tests in a module.
    """
    # Imports are safe now because docker.from_env is mocked
    from pyexec.main import app

    with TestClient(app) as test_client:
        test_client.headers = {"X-API-Key": "test-api-key"}
        yield test_client


@pytest.fixture
def test_session(tmp_path: Path):
    """
    Creates a temporary session directory for a single test.
    Using pytest's built-in tmp_path fixture for robust cleanup.
    """
    # We need to import this here, after settings are configured
    from pyexec.config import settings

    # Temporarily override the session path to use the test's temp directory
    original_path = settings.BASE_SESSION_PATH
    settings.BASE_SESSION_PATH = tmp_path

    session_id = f"test-session-{os.urandom(4).hex()}"
    (tmp_path / session_id).mkdir()

    yield session_id

    # Restore original path
    settings.BASE_SESSION_PATH = original_path


@pytest.fixture(scope="session")
def api_key():
    """A fixture to provide the test API key value."""
    return TEST_API_KEY


@pytest.fixture
def api_headers(api_key):
    """A fixture to provide the full authorization header."""
    return {"X-API-Key": api_key}
