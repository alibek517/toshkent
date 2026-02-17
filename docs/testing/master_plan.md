# Master Test Plan

## 1. Objectives
- Ensure **Zero Regression**: Existing keyword matching and forwarding must gracefully handle errors.
- **Isolation**: Tests must NOT spam real Telegram groups.
- **Coverage**: End-to-End (E2E) flows from "Message Received" to "Data Saved in DB".

## 2. Test Environments

### A. Local Sandbox (Recommended)
We will use `pytest` with **Mocking**.
- **Mock Telegram**: Use `unittest.mock` to mock `pyrogram.Client` and `message` objects.
- **Mock Supabase**: Use a fake Supabase client that stores data in a local `dict` instead of making HTTP requests.

### B. Live Sandbox (Integration)
For true E2E testing, we need:
1.  **Test Group**: A dedicated Telegram group (e.g., "UserBot Test Zone").
2.  **Test Channel**: A dedicated channel for the "Drivers" output.
3.  **Test Database**: A separate Supabase project (or a separate schema/table set).

## 3. Implementation Plan for Tests

### Step 1: Install Test Dependencies
Create `requirements-test.txt`:
```
pytest
pytest-asyncio
pytest-mock
coverage
```

### Step 2: Create Test Directory Structure
```
tests/
├── conftest.py          # Fixtures (mock_client, mock_supabase)
├── unit/
│   ├── test_regex.py    # Test keyword matching logic
│   └── test_utils.py    # Test helper functions
└── integration/
    ├── test_flow.py     # Message -> Handler -> Queue -> Sender
    └── test_portal.py   # FastAPI endpoints
```

### Step 3: Write Critical Tests
1.  **Regex Matching**:
    - Input: "Salom, yuk bor Toshkentdan"
    - Keyword: "yuk bor"
    - Expected: Match found.

2.  **Ignore Logic**:
    - Input: Message from blocked group ID.
    - Expected: No action.

3.  **Forwarding Format**:
    - Verify that the forwarded message contains the correct HTML links and structure.

## 4. Execution Instructions
1.  `pip install -r requirements-test.txt`
2.  `pytest tests/ -v`
