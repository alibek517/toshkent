# Manual Sandbox Testing Guide

This guide explains how to safely run the project in a "Sandbox" mode where it monitors real groups (or test groups) but sends alerts to a **Test Channel** instead of the real Drivers Group.

## 1. Prerequisites

You need the following for a safe manual test:

1.  **Test Telegram Account**: A phone number you can log in with (can be your main account, but safer to use a secondary).
2.  **Test Bot Token**: Create a new bot with [@BotFather](https://t.me/BotFather) (e.g., `my_test_forwarder_bot`).
    *   **Why?** The system uses a Bot to send the formatted alert to the drivers group. You don't want to use the production bot for testing.
3.  **Test Output Group**: A Telegram group where the bot will send alerts.
    *   Add your **Test Bot** to this group as an Admin.
    *   Get the `chat_id` of this group (e.g., `-100123456789`).

## 2. Configuration (`.env.test`)

Create a file named `.env.test` by copying `env.test.example`:

```bash
cp env.test.example .env.test
```

Edit `.env.test` with your **SANDBOX** credentials:

```ini
# Real Telegram Account (The "Ears")
TELEGRAM_API_ID=123456          # Your API ID
TELEGRAM_API_HASH=abcdef...     # Your API Hash
PHONE_NUMBER=+998901234567      # The phone number monitoring groups

# Test Output (The "Voice")
TELEGRAM_BOT_TOKEN=123:ABC...   # <--- YOUR NEW TEST BOT TOKEN
DRIVERS_GROUP_ID=-100987654321  # <--- YOUR TEST GROUP ID

# Database (Ideally use a separate project or just be careful)
SUPABASE_URL=...
SUPABASE_SERVICE_KEY=...

# App Settings
SEND_WORKERS=1                  # Low concurrency for testing
```

## 3. Running in Sandbox Mode

We can run the `main.py` using the `.env.test` file.

**Option A (Manual Export):**
```bash
export $(cat .env.test | xargs) && python3 main.py
```

**Option B (Modify main.py temporarily):**
Change `load_dotenv()` to `load_dotenv(".env.test")` in `main.py` (line 18).

## 4. Verification Steps

1.  **Start the script**: You should see "UserBot Multi-Account ishga tushmoqda...".
2.  **Log in**: If asked, enter the code sent to your Telegram account.
3.  **Send a Trigger**:
    *   Go to a group that the UserBot account has joined.
    *   Send a message with a keyword (e.g., "yuk bor").
4.  **Check Output**:
    *   Look at your **Test Output Group**.
    *   **PASS**: The Test Bot sends a formatted message with "Yangi buyurtma" and a link.
    *   **FAIL**: No message appears (check console logs for errors).

## 5. Cleaning Up
*   Stop the script (`Ctrl+C`).
*   Delete the session file in `sessions/` if you don't want to keep the session active.
