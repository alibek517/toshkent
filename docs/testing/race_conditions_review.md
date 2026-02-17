# Race Conditions Review — `main.py`

## Summary

After a thorough review of `main.py`, I found **3 confirmed race conditions** and **2 potential issues**. Below is the full analysis.

---

## 🔴 Confirmed Race Conditions

### 1. `refresh_keywords()` — Non-Atomic Global Update (Line 373)

**Problem:** Multiple handlers can trigger `refresh_keywords()` concurrently when `CACHE_TTL` expires. The function writes to three globals (`keywords_cache`, `keywords_regex`, `last_cache_update`) without any lock. If two coroutines run it simultaneously:
- Handler A reads old `keywords_regex` while Handler B is mid-update
- `keywords_cache` and `keywords_regex` can be temporarily inconsistent (list says 10 keywords, regex only has 5)

**Severity:** Medium — Could cause missed keyword matches for a brief window.

**Fix:**
```python
import asyncio
_keywords_lock = asyncio.Lock()

async def refresh_keywords():
    global keywords_cache, keywords_regex, last_cache_update
    async with _keywords_lock:
        # Check again inside lock (double-check pattern)
        if time.time() - last_cache_update <= CACHE_TTL:
            return
        # ... rest of logic
```

### 2. `sync_account_groups()` — Lambda Closure Bug (Line 488–494)

**Problem:** Inside the `for group in new_groups:` loop, the lambda captures `group` by reference, not by value. By the time `asyncio.to_thread` executes the lambda, `group` may have already moved to the next iteration. This means all inserts could use the **last** group's data.

**Severity:** High — Silently inserts wrong group data into Supabase.

**Fix:**
```python
for group in new_groups:
    g = group  # capture by value
    try:
        await sb_execute(lambda g=g: supabase.table("account_groups").insert({
            "phone_number": phone,
            "group_id": g["group_id"],
            "group_name": g["group_name"],
        }).execute())
```

### 3. `sync_all_groups()` — Same Lambda Closure Bug (Line 537)

**Problem:** Same issue as #2. The `lambda` inside the loop captures `g` by reference.

**Fix:**
```python
for g in groups_found:
    # ...
    group_data = g  # capture
    await sb_execute(lambda group_data=group_data: supabase.table("watched_groups").insert({
        "group_id": group_data["group_id"],
        "group_name": group_data["group_name"],
        "is_blocked": is_blocked
    }).execute())
```

---

## 🟡 Potential Issues

### 4. `send_queue` — No Duplicate Check (Line 802–809)

**Problem:** If two accounts are in the same group and both receive the same message, each will independently match the keyword and enqueue a forward. The `cache_key` is `(normalize_chat_id(chat_id), int(message.id))` but there's no deduplication check before `put_nowait`.

**Impact:** The drivers group gets **duplicate alerts** for the same message.

**Fix:** Add a `seen_messages` set with TTL:
```python
_seen_messages: Dict[tuple, float] = {}

# In handle_message, before enqueueing:
cache_key = (normalize_chat_id(chat_id), int(message.id))
now = time.time()
if cache_key in _seen_messages and now - _seen_messages[cache_key] < 60:
    return  # Already processed
_seen_messages[cache_key] = now
```

### 5. `aiohttp_session` — Shared Session Across Workers (Line 653)

**Problem:** `aiohttp_session` is a global shared by all `send_worker` tasks. If the session is closed (e.g., during shutdown) while a worker is mid-request, it will crash.

**Impact:** Low — Only during shutdown. But could cause noisy error logs.

**Fix:** Each worker should check `session.closed` before using it, or use a try/except around the session usage.

---

## ✅ Things That Are Fine

- **`asyncio.create_task` for DB saves** (lines 784, 798): These are fire-and-forget, which is acceptable since DB failures are logged but don't block the message handler.
- **`asyncio.Event().wait()`** (line 850, 938): Correct pattern for keeping the event loop alive.
- **`FloodWait` handling** (line 519–528): Properly sleeps and retries.
- **Queue backpressure** (line 804–809): The `while True` + `sleep(0.05)` loop prevents message loss when the queue is full.

---

## Priority Order for Fixes

1. **#2 & #3 (Lambda Closure)** — Silent data corruption, fix immediately
2. **#4 (Duplicate Messages)** — User-visible bug, fix next
3. **#1 (Keywords Lock)** — Rare timing window, fix for correctness
4. **#5 (Session Check)** — Nice to have
