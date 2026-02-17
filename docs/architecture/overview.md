# UserBot Project Architecture

## 1. High-Level Overview
This project is a **Telegram UserBot** designed to monitor specific Telegram groups for keywords (e.g., job postings, requests for services) and forward relevant messages to a designated "Drivers" group. It acts as a bridge between public/semi-public groups and a private service group.

The system consists of:
1.  **UserBot Core (`main.py`)**: A Python application using `pyrogram` to act as a Telegram client. It runs multiple sessions (phone numbers) to scale monitoring capabilities.
2.  **Web Portal (`portal_app.py`)**: A FastAPI web application that serves as a dashboard to view captured messages and generate screenshots.
3.  **Database (Supabase)**: A cloud PostgreSQL database used for storing state (watched groups, account status), configuration (keywords), and captured data (messages).

## 2. Detailed Architecture

### Components

#### A. UserBot Core (`main.py`)
*   **Multi-Account Management**: Handles multiple Telegram sessions (`sessions/` directory).
*   **Group Monitoring**: Dictionary-based caching of watched groups to avoid redundant network calls.
*   **Keyword Matching**: Regex-based optimized matching engine. Keywords are fetched from Supabase and cached locally with a TTL (Time-To-Live).
*   **Message Processing**:
    *   Extracts text, links, and media.
    *   Filters out spam or irrelevant content based on logic.
    *   Forwards valid hits to the `DRIVERS_GROUP_ID`.
    *   Saves hit details to Supabase (`captured_messages`, `keyword_hits`).
*   **Resiliency**: Handles `flood_wait` and other Telegram API errors. Includes logic for re-login or session cleanup upon invalidation.

#### B. Web Portal (`portal_app.py`)
*   **Tech Stack**: FastAPI, Uvicorn (implied), HTML/CSS (embedded).
*   **Features**:
    *   `/m/{uuid}`: View a captured message in a clean, formatted card UI.
    *   `/m/{uuid}/shot.png`: Generates a PNG screenshot of the message text using `Pillow` (server-side rendering).
    *   `/m/{uuid}/tgshot.png`: (Optional) Uses Playwright to take a real screenshot of the message from Web Telegram.

#### C. Database (Supabase)
*   **Tables**:
    *   `userbot_accounts`: Manages phone numbers and their states (active, pending, error).
    *   `watched_groups`: List of groups currently being monitored.
    *   `keywords`: List of keywords to trigger forwarding.
    *   `captured_messages`: Stores full details of forwarded messages.
    *   `keyword_hits`: Lightweight log of hits for analytics.
    *   `account_groups`: Mapping of which account is in which group.

### Data Flow

1.  **Initialization**:
    *   App starts, connects to Supabase.
    *   Loads accounts from `.env` or DB.
    *   For each account, starts a `pyrogram.Client`.

2.  **Monitoring Loop**:
    *   **Event**: New Message in a monitored group.
    *   **Filter**: Check if group is blocked.
    *   **Match**: Regex search against cached keywords.
    *   **Action (if match)**:
        1.  Extract data (links, sender, text).
        2.  **Async Save**: Write detailed record to `Supabase.captured_messages`.
        3.  **Async Log**: Write hit to `Supabase.keyword_hits`.
        4.  **Forward**: Send formatted message with inline keyboard to `DRIVERS_GROUP_ID`.

3.  **Portal Access**:
    *   User clicks "Portal Link" in the forwarded message.
    *   `portal_app` fetches message data from Supabase by UUID.
    *   Renders HTML page or generates Image on-the-fly.

## 3. Directory Structure
```
userbottoshkent/
├── .env                  # Secrets (API keys, DB credentials)
├── sessions/             # Telegram session files (*.session)
├── main.py               # Entry point for UserBot
├── portal_app.py         # Entry point for Web Portal
├── docs/                 # Project documentation
│   ├── architecture/     # This folder
│   ├── agents/           # Context for AI agents
│   └── testing/          # Test plans
└── requirements.txt      # Python dependencies
```

## 4. Key Configurations
*   **Keywords Refresh**: Every `CACHE_TTL` seconds (default 300s).
*   **Group Sync**: Every `SYNC_INTERVAL` seconds (default 1800s).
*   **Concurrency**: UserBot uses `asyncio` for non-blocking I/O.
