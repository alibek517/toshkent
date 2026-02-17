
import pytest
from unittest.mock import MagicMock, AsyncMock

@pytest.fixture
def mock_supabase():
    mock = MagicMock()
    # Mock specific table methods if needed
    mock.table.return_value.select.return_value.execute.return_value.data = []
    mock.table.return_value.insert.return_value.execute.return_value.data = []
    return mock

@pytest.fixture
def mock_client():
    mock = MagicMock()
    return mock

@pytest.fixture
def sample_message():
    message = MagicMock()
    message.text = "This is a test message"
    message.chat.id = -1001234567890
    message.chat.title = "Test Group"
    message.id = 123
    message.from_user.username = "testuser"
    return message
