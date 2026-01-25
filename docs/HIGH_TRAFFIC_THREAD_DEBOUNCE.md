# High-Traffic Thread Debounce Specification

## Overview

The High-Traffic Thread Debounce feature automatically detects when umbra is receiving an unusually high volume of notifications from a single thread (viral threads, heated discussions, etc.) and batches them together for efficient processing. Instead of responding to each notification individually as it arrives, umbra waits for the thread to evolve, then reviews all notifications in a single batch with full context.

## Table of Contents

1. [Problem Statement](#problem-statement)
2. [Solution Overview](#solution-overview)
3. [Architecture](#architecture)
4. [Database Schema](#database-schema)
5. [Thread State Machine](#thread-state-machine)
6. [Configuration](#configuration)
7. [Detection Mechanism](#detection-mechanism)
8. [Debounce Time Calculation](#debounce-time-calculation)
9. [Batch Processing](#batch-processing)
10. [Incremental Batches](#incremental-batches)
11. [Multi-Part Reply Handling](#multi-part-reply-handling)
12. [Processing Flow](#processing-flow)
13. [Log Messages](#log-messages)
14. [Error Handling](#error-handling)
15. [Performance Considerations](#performance-considerations)
16. [Related Functions](#related-functions)
17. [Migration Guide](#migration-guide)
18. [Future Enhancements](#future-enhancements)

---

## Problem Statement

When umbra participates in a popular thread, several issues can occur:

1. **Notification Overload**: A viral thread can generate 10-100+ notifications per hour
2. **Context Fragmentation**: Processing notifications individually means responding without seeing the full conversation evolution
3. **Response Flooding**: Responding to many individual notifications can flood the thread with umbra's posts
4. **API Inefficiency**: Each notification triggers separate API calls for thread context, user blocks, etc.
5. **Quality Degradation**: Rapid responses without full context often produce lower-quality engagement

---

## Solution Overview

The High-Traffic Thread Debounce system provides:

1. **Automatic Detection**: Identifies high-traffic threads based on notification frequency
2. **Single Timer Per Thread**: All notifications from the same thread share one debounce timer
3. **Priority Queue**: Direct mentions receive shorter debounce times than replies
4. **Variable Scaling**: Debounce duration increases with thread activity
5. **Batch Processing**: All notifications presented together with complete thread context
6. **Full Context Preservation**: Tree view always includes all context posts for complete thread understanding
7. **State Machine**: Robust tracking of thread lifecycle (debouncing → cooldown → reset)

---

## Architecture

### High-Level Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Notification Flow                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Bluesky API                                                                 │
│       │                                                                      │
│       ▼                                                                      │
│  ┌─────────────────────────┐                                                │
│  │ save_notification_to_   │                                                │
│  │ queue()                 │                                                │
│  └───────────┬─────────────┘                                                │
│              │                                                              │
│              ▼                                                              │
│  ┌─────────────────────────┐     ┌────────────────────────────────┐        │
│  │ High-Traffic Detection  │────▶│ get_thread_notification_count()│        │
│  └───────────┬─────────────┘     └────────────────────────────────┘        │
│              │                                                              │
│              ▼                                                              │
│         count >= threshold?                                                 │
│              │                                                              │
│     ┌────────┴────────┐                                                     │
│     │ NO              │ YES                                                 │
│     ▼                 ▼                                                     │
│  Normal            ┌─────────────────────────┐                              │
│  Processing        │ Check thread_state      │                              │
│                    │ table for existing      │                              │
│                    │ debounce timer          │                              │
│                    └───────────┬─────────────┘                              │
│                                │                                            │
│                    ┌───────────┴───────────┐                                │
│                    │                       │                                │
│                    ▼                       ▼                                │
│              No state              DEBOUNCING or COOLDOWN                   │
│              (new thread)          (existing thread)                        │
│                    │                       │                                │
│                    ▼                       ▼                                │
│              Create new              Extend/Re-trigger                      │
│              debounce timer          debounce timer                         │
│                    │                       │                                │
│                    └───────────┬───────────┘                                │
│                                │                                            │
│                                ▼                                            │
│                    ┌─────────────────────────┐                              │
│                    │ set_auto_debounce()     │                              │
│                    │ - debounce_until        │                              │
│                    │ - auto_debounced=1      │                              │
│                    │ - high_traffic_thread=1 │                              │
│                    │ - thread_chain_id       │                              │
│                    └───────────┬─────────────┘                              │
│                                │                                            │
│                                ▼                                            │
│                    Queue file created, waiting for expiration               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Components

| Component | File | Purpose |
|-----------|------|---------|
| Detection Logic | `bsky.py` | Counts notifications, triggers debouncing |
| State Machine | `notification_db.py` | Manages thread lifecycle states |
| Batch Processing | `bsky.py` | Processes expired debounces as batches |
| Configuration | `config.yaml` | Thresholds, timing parameters |
| Queue Files | `queue/` directory | Pending notifications on disk |

---

## Database Schema

### Notifications Table

The notifications table includes these columns for high-traffic tracking:

```sql
-- Core notification fields
uri TEXT PRIMARY KEY,           -- Unique notification identifier
indexed_at TEXT,                -- When notification was received
processed_at TEXT,              -- When notification was processed
status TEXT,                    -- pending|processed|ignored|no_reply|in_progress|error
reason TEXT,                    -- mention|reply|follow|repost|like
author_handle TEXT,             -- Who posted it
author_did TEXT,                -- Author's DID
text TEXT,                      -- Post text (first 500 chars)
parent_uri TEXT,                -- Parent post (if reply)
root_uri TEXT,                  -- Thread root (always populated)

-- Debounce fields
debounce_until TEXT,            -- ISO timestamp when debounce expires
debounce_reason TEXT,           -- 'high_traffic_mention' or 'high_traffic_reply'
thread_chain_id TEXT,           -- root_uri of the thread (for batch grouping)

-- High-traffic specific flags
auto_debounced INTEGER DEFAULT 0,      -- 1 if automatically debounced
high_traffic_thread INTEGER DEFAULT 0  -- 1 if part of high-traffic thread
```

### Indexes

```sql
CREATE INDEX idx_root_uri ON notifications(root_uri);
CREATE INDEX idx_root_uri_indexed_at ON notifications(root_uri, indexed_at);
CREATE INDEX idx_auto_debounced ON notifications(auto_debounced);
CREATE INDEX idx_high_traffic_thread ON notifications(high_traffic_thread);
CREATE INDEX idx_debounce_until ON notifications(debounce_until);
```

### Thread State Table

The `thread_state` table implements a state machine with three states:

```sql
CREATE TABLE thread_state (
    root_uri TEXT PRIMARY KEY,              -- Thread identifier
    state TEXT NOT NULL,                    -- 'debouncing' or 'cooldown'
    debounce_until TEXT,                    -- When debounce expires
    debounce_started_at TEXT,               -- When this debounce cycle started
    cooldown_until TEXT,                    -- When cooldown expires
    notification_count INTEGER DEFAULT 0,   -- Notifications in this cycle
    last_notification_at TEXT,              -- Most recent notification
    updated_at TEXT                         -- Last state update
);
```

**Purpose**: Coordinates timing for all notifications from the same thread - single timer per thread, not per notification.

### Thread Batch History Table

```sql
CREATE TABLE thread_batch_history (
    root_uri TEXT PRIMARY KEY,                  -- Thread identifier
    last_batch_processed_at TEXT,               -- When batch was processed
    last_batch_newest_post_indexed_at TEXT      -- Newest post in last batch
);
```

**Purpose**: Enables incremental batches - subsequent batches only show NEW posts, not previously reviewed ones. Persists independently of `thread_state` so history survives cooldown expiry.

---

## Thread State Machine

The system uses a three-state machine to track each thread's lifecycle:

### State Diagram

```
                    ┌─────────────────────────────────┐
                    │      NO STATE (initial)         │
                    │   Thread not being tracked      │
                    └──────────────┬──────────────────┘
                                   │
                                   │ [notification arrives]
                                   │ [count >= threshold]
                                   ▼
                    ┌─────────────────────────────────┐
                    │         DEBOUNCING              │
                    │                                 │
                    │ • Collecting notifications      │
                    │ • debounce_until = expiry time  │
                    │ • notification_count tracks     │
                    │   activity level                │
                    │ • All notifications share       │
                    │   same timer                    │
                    └──────────────┬──────────────────┘
                                   │
    ┌──────────────────────────────┼──────────────────────────────────┐
    │                              │                                  │
    │ [new notification,           │ [debounce expires]               │
    │  timer NOT expired]          │                                  │
    │                              │                                  │
    ▼                              ▼                                  │
┌───────────────┐    ┌─────────────────────────────────────┐          │
│ Extend timer  │    │ Timer expired - check staleness     │          │
│ (from start   │    └─────────────┬───────────────────────┘          │
│  time, not    │                  │                                  │
│  from now)    │    ┌─────────────┴─────────────┐                    │
└───────┬───────┘    │                           │                    │
        │            │                           │                    │
        │   [expired recently          [expired long ago              │
        │    + new notification]        (stale state)]                │
        │            │                           │                    │
        │            ▼                           ▼                    │
        │   ┌───────────────┐          ┌───────────────┐              │
        │   │ Start new     │          │ Clear state   │              │
        │   │ debounce      │          │ → Normal      │              │
        │   │ cycle         │          │   processing  │              │
        │   └───────────────┘          └───────┬───────┘              │
        │                                      │                      │
        └──────────────────────────────────────┼──────────────────────┘
                                               │
                     [batch processed]         │ [stale → NO STATE]
                              │                │
                              ▼                │
                    ┌─────────────────────────────────┐
                    │          COOLDOWN               │
                    │                                 │
                    │ • Batch has been processed      │
                    │ • cooldown_until = now +        │
                    │   time_window_minutes           │
                    │ • Prevents immediate            │
                    │   re-triggering                 │
                    └──────────────┬──────────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          │                        │                        │
          │ [new notification      │ [cooldown expires]     │
          │  count >= threshold]   │                        │
          │                        │                        │
          ▼                        ▼                        │
    ┌───────────────┐       ┌───────────────┐               │
    │ Re-trigger    │       │ Clear state   │               │
    │ debouncing    │       │ (back to NO   │               │
    │ (new cycle)   │       │  STATE)       │               │
    └───────────────┘       └───────────────┘               │
```

### State Transitions

| Current State | Event | New State | Action |
|---------------|-------|-----------|--------|
| NO STATE | count >= threshold | DEBOUNCING | `set_thread_debouncing()` |
| DEBOUNCING | new notification (timer not expired) | DEBOUNCING | `extend_thread_debounce()` |
| DEBOUNCING | timer expires + batch processed | COOLDOWN | `process_high_traffic_batch()` then `set_thread_cooldown()` |
| DEBOUNCING | timer expired recently + new notification | DEBOUNCING | `set_thread_debouncing()` (new cycle) |
| DEBOUNCING | timer expired long ago (stale) + new notification | NO STATE | `clear_thread_state()` → normal processing |
| COOLDOWN | count >= threshold | DEBOUNCING | `set_thread_debouncing()` (new cycle) |
| COOLDOWN | cooldown expires | NO STATE | `cleanup_expired_cooldowns()` |

### Stale State Detection

When a thread is in DEBOUNCING state but the timer has expired and no batch processing occurred (e.g., no queue processing triggered), the state can become "stale". This happens when:

1. A thread's debounce timer expires
2. No batch processing occurs (the notification queue doesn't encounter it)
3. A significant amount of time passes (longer than `time_window_minutes`)
4. A new notification arrives for that thread

In this case, instead of starting a new debounce cycle, the system:
1. Recognizes the state as stale (timer expired > `time_window_minutes` ago)
2. Clears the thread state via `clear_thread_state()`
3. Processes the new notification normally (no debouncing)

This prevents notifications from being indefinitely debounced when thread activity dies down.

### Timer Extension Logic

When a new notification arrives during DEBOUNCING, the timer is **extended from the original start time**, not from now. This prevents infinite deferral:

```python
# Wrong approach (would defer forever):
new_debounce_until = now + debounce_seconds

# Correct approach (bounded deferral):
new_debounce_until = debounce_started_at + debounce_seconds
```

**Example Timeline:**
```
10:00 - First notification (threshold reached)
        → Set debounce_started_at = 10:00
        → Set debounce_until = 10:00 + 30min = 10:30

10:15 - Second notification arrives
        → Thread count now 12 → recalculate to 35 minutes
        → New debounce_until = 10:00 + 35min = 10:35
        → NOT 10:15 + 35min = 10:50 (would keep extending)

10:25 - Third notification arrives
        → Thread count now 15 → recalculate to 40 minutes
        → New debounce_until = 10:00 + 40min = 10:40

10:40 - Timer expires → Process batch of all 3 notifications
```

---

## Configuration

### config.yaml Structure

```yaml
threading:
  # Manual debounce (agent-triggered)
  debounce_enabled: true
  debounce_seconds: 600
  max_debounce_seconds: 1200

  # Automatic high-traffic detection
  high_traffic_detection:
    enabled: true                    # Enable/disable feature
    notification_threshold: 6        # Notifications to trigger detection
    time_window_minutes: 30          # Window for counting notifications

    # Debounce times for direct mentions (higher priority)
    mention_debounce_min: 7          # Minimum debounce (minutes)
    mention_debounce_max: 30         # Maximum debounce (minutes)

    # Debounce times for replies (lower priority)
    reply_debounce_min: 15           # Minimum debounce (minutes)
    reply_debounce_max: 60           # Maximum debounce (minutes)
```

### Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enabled` | bool | false | Master switch for feature |
| `notification_threshold` | int | 6 | Min notifications to trigger |
| `time_window_minutes` | int | 30 | Window for counting notifications |
| `mention_debounce_min` | int | 7 | Min debounce for mentions (min) |
| `mention_debounce_max` | int | 30 | Max debounce for mentions (min) |
| `reply_debounce_min` | int | 15 | Min debounce for replies (min) |
| `reply_debounce_max` | int | 60 | Max debounce for replies (min) |

### Tuning Guidelines

| Scenario | Adjustment |
|----------|------------|
| More responsive to mentions | Lower `mention_debounce_min/max` |
| Wait longer for threads to settle | Increase `reply_debounce_max` |
| Trigger detection earlier | Lower `notification_threshold` |
| Trigger detection later | Raise `notification_threshold` |
| Shorter counting window | Lower `time_window_minutes` |

---

## Detection Mechanism

### How Detection Works

When a notification arrives:

1. **Extract root_uri** from the notification (identifies the thread)
2. **Count recent notifications** for that thread within the time window:
   ```python
   thread_count = get_thread_notification_count(root_uri, time_window_minutes)
   ```
3. **Compare against threshold**:
   - If `count < threshold`: Process normally
   - If `count >= threshold`: Trigger high-traffic debouncing

### Thread Counting Query

```sql
SELECT COUNT(*) FROM notifications
WHERE root_uri = ?
AND indexed_at >= datetime('now', '-N minutes')
AND reason IN ('mention', 'reply')
```

### Single Timer Per Thread

All notifications from the same thread share one debounce timer. When a new notification arrives for an already-debouncing thread:

1. Check `thread_state` table for existing timer
2. If timer exists and not expired: **reuse** the same `debounce_until`
3. If timer exists but calculation yields later time: **extend** the timer
4. All notifications marked with the same timer → process together

**Log messages:**
```
⚡ Started new debounce cycle for mention (duration: 7min)
⚡ Reusing existing debounce timer for high-traffic reply (expires: 2025-11-24T12:00:00)
⚡ Extending debounce for high-traffic mention (18 notifications, new expiry: 2025-11-24T12:15:00)
```

---

## Debounce Time Calculation

### Variable Debounce Formula

The debounce time scales linearly with thread activity:

```python
def calculate_variable_debounce(thread_count, threshold, min_seconds, max_seconds):
    if thread_count <= threshold:
        return min_seconds
    elif thread_count >= threshold * 20:
        return max_seconds
    else:
        # Linear interpolation between threshold and 20x threshold
        ratio = (thread_count - threshold) / (threshold * 19)
        return min_seconds + (max_seconds - min_seconds) * ratio
```

### Examples

With `threshold=2`, `min=2min`, `max=60min`:

| Thread Count | Ratio | Calculation | Debounce Time |
|--------------|-------|-------------|---------------|
| 2 | 0.0 | 2 + (60-2) × 0 | 2 minutes |
| 12 | 0.26 | 2 + (60-2) × 0.26 | 17 minutes |
| 21 | 0.5 | 2 + (60-2) × 0.5 | 31 minutes |
| 31 | 0.76 | 2 + (60-2) × 0.76 | 46 minutes |
| 40+ | 1.0 (capped) | 2 + (60-2) × 1.0 | 60 minutes |

### Priority Queue: Mentions vs Replies

Direct mentions receive shorter debounce times than replies:

| Type | Default Range | Rationale |
|------|---------------|-----------|
| Mention | 7-30 minutes | Direct engagement, higher priority |
| Reply | 15-60 minutes | Lower priority, can wait longer |

This ensures umbra remains responsive to direct mentions while giving reply-heavy threads more time to evolve.

---

## Batch Processing

### When Batches are Processed

Batch processing triggers when:
1. A queue file is loaded for a debounced notification
2. The `debounce_until` timestamp has passed
3. The notification has `auto_debounced=1` AND `high_traffic_thread=1`

### Batch Processing Steps

```
1. Load queue file for expired debounce
2. Check if high-traffic batch (auto_debounced=1, high_traffic_thread=1)
3. Fetch ALL debounced notifications for this thread from database
4. Mark all notifications as in_progress (prevents re-queuing)
5. Fetch current thread context from Bluesky (depth=10)
6. For each notification, fetch parent chain for multi-part detection
7. Merge all posts, deduplicate, sort chronologically
8. Split into:
   - THREAD CONTEXT: Posts that existed before notifications
   - NOTIFICATIONS: The posts umbra was actually notified about
9. Check batch history for previously reviewed posts
10. Build message with metadata and instructions
11. Send to agent
12. Process agent's reply_to_bluesky_post tool calls
13. Mark ALL batch notifications as processed
14. Clear debounce flags on all notifications
15. Transition thread to COOLDOWN state
16. Update batch history for incremental batches
17. Delete queue files
```

### Message Format to Agent

```
This is a HIGH-TRAFFIC THREAD that generated N notifications during the debounce period.

================================================================================
1. THREAD CONTEXT (Pre-notification history)
================================================================================

These posts were in the thread BEFORE you received your notifications:

posts:
  - author:
      handle: alice.bsky.social
      display_name: Alice
    record:
      text: "Original post that started the thread..."
      createdAt: "2025-11-24T10:00:00Z"

================================================================================
2. NOTIFICATIONS (N posts you were notified about)
================================================================================

[Notification 1] @bob.bsky.social (mention) - Received: 2025-11-24T10:15:00
  Post: "Hey @umbra, what do you think about this?"
  URI: at://did:plc:xxx/app.bsky.feed.post/abc123
  CID: bafyxxx
  Posted: 2025-11-24T10:14:50

[Notification 2] @charlie.bsky.social (reply) - Received: 2025-11-24T10:20:00
  [Part 1 by same author]: "This is the first part..." (Posted: 2025-11-24T10:14:00)
  [Part 2 by same author]: "...continuing from above" (Posted: 2025-11-24T10:14:30)
  Post: "And finally, my conclusion is..."
  URI: at://did:plc:yyy/app.bsky.feed.post/def456
  CID: bafyyyy
  Posted: 2025-11-24T10:19:55

================================================================================
RESPONSE INSTRUCTIONS
================================================================================

- Review THREAD CONTEXT to understand the conversation history
- You received N NOTIFICATIONS - these are the posts that might warrant a response
- Respond to 0-3 notifications depending on what's interesting
- Use reply_to_bluesky_post with the URI and CID from the notification you want to reply to
```

### Preventing Duplicate Batch Processing

Multiple queue files may exist for one batch. The system prevents re-processing:

```python
processed_high_traffic_batches = set()  # Track batches in current cycle

for queue_file in queue_files:
    batch_id = notification.get('thread_chain_id')  # root_uri

    if batch_id in processed_high_traffic_batches:
        # Already processed this batch
        mark_processed(uri, 'processed')
        delete_queue_file()
        continue

    # Process batch once
    process_high_traffic_batch(...)
    processed_high_traffic_batches.add(batch_id)
```

---

## Incremental Batches

### The Problem

When a thread continues generating notifications after a batch is processed, umbra needs to maintain context about the full thread structure. Notifications may be replies to any post in the thread, so the agent must see the complete conversation to understand the context.

### Solution: Full Tree View Always

The system always includes the complete tree view of all context posts (non-notification posts), regardless of whether it's a first batch or an incremental batch. This ensures:
1. Notifications that reply to older posts have proper context
2. The agent understands the full thread structure
3. No context is lost due to optimization

The `thread_batch_history` table tracks batch history for logging purposes:

```sql
-- Records when batches were processed
INSERT INTO thread_batch_history (root_uri, last_batch_processed_at, last_batch_newest_post_indexed_at)
VALUES (?, ?, ?)
ON CONFLICT(root_uri) DO UPDATE SET ...
```

### How Incremental Batches Work

**First Batch:**
1. Fetch entire thread
2. Show full tree view of all context posts
3. Record newest post timestamp for logging

**Second Batch (thread continues):**
1. Fetch entire thread (may have grown)
2. Show full tree view of all context posts (same as first batch)
3. Notifications section shows only new notifications
4. Update batch history for tracking

### Message Format (Same for All Batches)

```
This is a HIGH-TRAFFIC THREAD that generated N notifications during the debounce period.

================================================================================
1. Thread context (Pre-notification history)
================================================================================

These posts were in the thread BEFORE you received your notifications:

Thread Structure:
├─ @alice.bsky.social: "Original post that started the thread..."
│  └─ @bob.bsky.social: "First reply..."
│     └─ @charlie.bsky.social: "Continuing the conversation..."

================================================================================
2. NOTIFICATIONS (N posts you were notified about)
================================================================================
...
```

---

## Multi-Part Reply Handling

### The Problem

Users often split long thoughts across multiple posts (1/2, 2/2, etc.). When umbra receives a notification for the final post, it needs to see the preceding parts for context.

### Solution: Parent Chain Traversal

For each notification, the system:

1. **Fetches parent chain** via Bluesky API:
   ```python
   get_post_thread(notif_uri, parent_height=20, depth=0)
   ```

2. **Traverses upward** through parents, collecting consecutive posts by the same author

3. **Stops when** encountering a post by a different author

4. **Displays** preceding parts chronologically (oldest first)

### Example Output

When notification post is the third part of a multi-part reply:

```
[Notification 3] @alice.bsky.social (reply) - Received: 2025-11-24T10:20:00
  [Part 1 by same author]: "1/3 I've been thinking about this topic..." (Posted: 2025-11-24T10:14:00)
  [Part 2 by same author]: "2/3 Building on my first point..." (Posted: 2025-11-24T10:15:30)
  Post: "3/3 And my conclusion is that we should consider..."
  URI: at://did:plc:xxx/app.bsky.feed.post/abc123
  CID: bafyxxx
  Posted: 2025-11-24T10:20:00
```

### Implementation Details

```python
def find_consecutive_parent_posts_by_author(post, author_did, client):
    """
    Traverse UP through parents to find consecutive posts by same author.
    Returns list of (text, createdAt) tuples in chronological order.
    """
    preceding_parts = []
    current = post.get('parent')

    while current:
        current_author = current.get('author', {}).get('did')
        if current_author != author_did:
            break  # Different author - stop traversal

        # Same author - collect this part
        text = current.get('record', {}).get('text', '')
        created_at = current.get('record', {}).get('createdAt', '')
        preceding_parts.append((text, created_at))

        # Move to next parent
        current = current.get('parent')

    # Return in chronological order (oldest first)
    return list(reversed(preceding_parts))
```

---

## Processing Flow

### Complete Detection Phase Flow

```python
# In save_notification_to_queue()

def save_notification_to_queue(notification, config):
    root_uri = extract_root_uri(notification)

    # 1. Count notifications for this thread
    thread_count = db.get_thread_notification_count(
        root_uri,
        config['time_window_minutes']
    )

    # 2. Check if threshold reached
    if thread_count < config['notification_threshold']:
        # Normal processing
        save_to_queue(notification)
        return

    # 3. High-traffic detected - check thread state
    thread_state = db.get_thread_state(root_uri)

    if thread_state is None:
        # 4a. No existing state - create new debounce cycle
        debounce_seconds = calculate_debounce(thread_count, notification['reason'])
        debounce_until = (now + timedelta(seconds=debounce_seconds)).isoformat()

        db.set_thread_debouncing(root_uri, debounce_until, thread_count)
        log("⚡ Started new debounce cycle")

    elif thread_state['state'] == 'debouncing':
        timer_expired = thread_state['debounce_until'] <= now

        if timer_expired:
            # Check if state is stale (expired > time_window_minutes ago)
            minutes_since_expiry = (now - thread_state['debounce_until']).total_seconds() / 60

            if minutes_since_expiry > config['time_window_minutes']:
                # 4b-stale. Stale state - clear and process normally
                db.clear_thread_state(root_uri)
                log(f"⚡ Thread debounce state is stale ({minutes_since_expiry:.1f}min since expiry), clearing state")
                # Continue to normal processing (no debouncing)
                save_to_queue(notification)
                return
            else:
                # 4b-recent. Timer expired recently - start new cycle
                debounce_seconds = calculate_debounce(thread_count, notification['reason'])
                debounce_until = (now + timedelta(seconds=debounce_seconds)).isoformat()
                db.set_thread_debouncing(root_uri, debounce_until, notification_count=1)
                log("⚡ Debounce timer expired for thread, starting new cycle")
        else:
            # 4b. Timer not expired - extend it
            new_debounce_seconds = calculate_debounce(thread_count, notification['reason'])
            debounce_until = db.extend_thread_debounce(
                root_uri,
                new_debounce_seconds,
                thread_count,
                thread_state['debounce_started_at']
            )
            log("⚡ Extended debounce timer")

    elif thread_state['state'] == 'cooldown':
        # 4c. In cooldown - re-trigger debouncing (new cycle)
        debounce_seconds = calculate_debounce(thread_count, notification['reason'])
        debounce_until = (now + timedelta(seconds=debounce_seconds)).isoformat()

        db.set_thread_debouncing(root_uri, debounce_until, thread_count)
        log("⚡ Re-triggered debounce during cooldown")

    # 5. Set auto-debounce flags on notification
    db.set_auto_debounce(
        notification['uri'],
        debounce_until=debounce_until,
        debounce_reason=f"high_traffic_{notification['reason']}",
        thread_chain_id=root_uri
    )

    # 6. Create queue file
    save_to_queue(notification, debounced=True)
```

### Complete Batch Processing Flow

```python
# In load_and_process_queued_notifications()

def process_queue():
    processed_batches = set()

    for queue_file in queue_directory:
        notification = load_json(queue_file)

        # Check if debounced
        debounce_until = notification.get('debounce_until')
        if debounce_until and debounce_until > now:
            log("⏸️ Skipping - debounce not expired")
            continue

        # Check if high-traffic batch
        is_high_traffic = (
            notification.get('auto_debounced') == 1 and
            notification.get('high_traffic_thread') == 1
        )

        if is_high_traffic:
            batch_id = notification.get('thread_chain_id')

            if batch_id in processed_batches:
                # Already processed - just clean up
                db.mark_processed(notification['uri'])
                delete_file(queue_file)
                continue

            # Process the batch
            success = process_high_traffic_batch(notification)
            if success:
                processed_batches.add(batch_id)
        else:
            # Normal or manual debounce processing
            process_single_notification(notification)
```

---

## Log Messages

### Detection Phase

```
⚡ Started new debounce cycle for mention (duration: 7min)
⚡ Started new debounce cycle for reply (duration: 15min)
⚡ Extending debounce for high-traffic mention (18 notifications, new expiry: 2025-11-24T12:15:00)
⚡ Reusing existing debounce timer for high-traffic reply (expires: 2025-11-24T12:00:00)
⚡ Re-triggering debounce during cooldown for reply (min duration: 15min)
⚡ Thread debounce state is stale (45.3min since expiry), clearing state
⚡ Debounce timer expired for thread, starting new cycle for incoming reply
```

### Waiting Phase

```
⏸️ Skipping debounced notification (waiting until 2025-11-24T12:30:00)
```

### Processing Phase

```
⚡ Processing high-traffic thread batch
   Thread root: at://did:plc:xxx/app.bsky.feed.post/root123
   Found 5 debounced notifications in batch
   Fetching thread context (depth=10)...
Sending high-traffic batch to agent | 12 posts in thread | 5 notifications | prompt: 2847 chars
⚡ Tool call: reply_to_bluesky_post
⚡ Marked 5 notifications as processed
⚡ Cleared 5 debounces after successful processing
⏳ Thread entering cooldown until 2025-11-24T13:00:00
📝 Updated batch history (newest post: 2025-11-24T12:45:00Z)
✓ High-traffic batch processed successfully
⚡ Deleted 5 queue files for batch
```

### Cooldown Phase

```
🔄 Cleaning up 3 expired thread cooldowns
🔄 Cleared thread state for at://did:plc:xxx/app.bsky.feed.post/root123
```

### Debug Logs

```
High-traffic config loaded: {'enabled': True, 'notification_threshold': 6, ...}
Mention debounce config: min=7min (420s), max=30min (1800s)
Debounce calculation: thread_count=15, threshold=6
Using interpolated debounce (ratio=0.75): 1522s (25.4min)
```

---

## Error Handling

### Retry Logic

- Failed batch processing keeps queue files for retry (max 3 attempts)
- Debounces are only cleared after successful processing
- If all retries fail, notifications move to error directory
- Thread state is NOT cleared on failure (will retry with same timer)

### Edge Cases

| Scenario | Handling |
|----------|----------|
| Thread deleted | Batch fails, retries, eventually moves to error |
| Partial success | Retry entire batch (atomicity) |
| Single notification left | Fall back to normal processing |
| Timer conflict | Use earliest expiration time |
| API timeout | Retry with exponential backoff |
| Stale debounce state | Clear thread state, process normally (see [Stale State Detection](#stale-state-detection)) |

### Single Notification Fallback

If only one notification remains in a batch (others deleted/processed):

```python
if len(batch_notifications) == 1:
    # Fall back to normal processing
    db.clear_high_traffic_flags(single_uri)
    return False  # Will be processed normally on next iteration
```

---

## Performance Considerations

### Database Query Cost Per Notification

| Operation | Queries |
|-----------|---------|
| Count thread notifications | 1 SELECT |
| Check existing timer | 1 SELECT |
| Save notification with debounce | 1 INSERT |
| Get thread state | 1 SELECT |
| Update thread state | 1 UPDATE |

### Batch Processing Query Cost

| Operation | Queries/Calls |
|-----------|---------------|
| Fetch debounced notifications | 1 SELECT |
| Fetch thread from Bluesky | 1 API call |
| Fetch parent chains | N API calls (1 per notification) |
| Mark processed | N UPDATEs |
| Clear debounces | 1 UPDATE |
| Update batch history | 1 UPSERT |

### API Call Reduction

**Without batching:** N notifications × (thread fetch + parent chain + response) = N × 3 API calls

**With batching:** 1 thread fetch + N parent chains + K responses = 1 + N + K API calls (where K << N)

For a thread with 20 notifications where agent responds to 2:
- Without: 60 API calls
- With: 23 API calls (62% reduction)

### Index Strategy

| Index | Purpose | Query Pattern |
|-------|---------|---------------|
| `idx_root_uri_indexed_at` | Fast notification counting | `WHERE root_uri = ? AND indexed_at >= ?` |
| `idx_debounce_until` | Find expired debounces | `WHERE debounce_until < ?` |
| `idx_auto_debounced` | Route to batch processor | `WHERE auto_debounced = 1` |
| `idx_high_traffic_thread` | Route to batch processor | `WHERE high_traffic_thread = 1` |

---

## Related Functions

### bsky_utils.py

| Function | Purpose |
|----------|---------|
| `flatten_thread_structure()` | Converts nested thread data into flat chronological list |
| `find_consecutive_parent_posts_by_author()` | Traverses UP through parents for multi-part detection |
| `get_post_thread()` | Fetches thread from Bluesky with configurable depth |

### bsky.py

| Function | Purpose |
|----------|---------|
| `process_high_traffic_batch()` | Main batch processing function |
| `save_notification_to_queue()` | Detection and debounce timer creation |
| `notification_to_dict()` | Converts notifications including reply info |
| `build_high_traffic_message()` | Constructs agent message with metadata |

### notification_db.py

| Function | Purpose |
|----------|---------|
| `get_thread_notification_count()` | Counts notifications within time window |
| `get_thread_state()` | Gets current state machine state |
| `set_thread_debouncing()` | Transitions to DEBOUNCING state |
| `extend_thread_debounce()` | Extends timer from start time |
| `set_thread_cooldown()` | Transitions to COOLDOWN state |
| `clear_thread_state()` | Removes thread from state table |
| `cleanup_expired_cooldowns()` | Batch cleanup of expired cooldowns |
| `get_thread_debounced_notifications()` | Fetches all notifications for batch |
| `set_auto_debounce()` | Sets debounce fields on notification |
| `clear_batch_debounce()` | Clears flags after successful processing |
| `calculate_variable_debounce()` | Computes duration based on activity |
| `get_thread_batch_history()` | Retrieves history for incremental batches |
| `update_thread_batch_history()` | Updates after batch processing |

---

## Migration Guide

### Required Migrations

Run these migrations before enabling high-traffic detection:

```bash
# 1. Add basic debounce columns
ac && python migrate_debounce_schema.py

# 2. Add high-traffic specific columns
ac && python migrate_high_traffic_schema.py

# 3. Create thread state table
ac && python migrate_thread_state_schema.py
```

### Migration Details

**migrate_debounce_schema.py:**
- Adds `debounce_until`, `debounce_reason`, `thread_chain_id` columns
- Creates indexes for debounce lookups

**migrate_high_traffic_schema.py:**
- Adds `auto_debounced`, `high_traffic_thread` columns
- Creates indexes for high-traffic routing

**migrate_thread_state_schema.py:**
- Creates `thread_state` table
- Creates `thread_batch_history` table
- Enables state machine functionality

### Enabling the Feature

After migrations, enable in `config.yaml`:

```yaml
threading:
  high_traffic_detection:
    enabled: true  # Set to true
```

---

## Future Enhancements

Potential improvements:

1. **Dynamic threshold adjustment** based on umbra's typical engagement patterns
2. **Thread priority scoring** to prioritize interesting threads over noise
3. **Smart response limiting** to cap responses per thread per day
4. **Batch response preview** before committing to posts
5. **Parent chain caching** to reduce API calls for notifications in the same branch
6. **Adaptive debounce timing** based on thread velocity (posts per minute)
7. **Thread sentiment analysis** to adjust engagement strategy
8. **Cross-thread deduplication** for users posting similar content in multiple threads
