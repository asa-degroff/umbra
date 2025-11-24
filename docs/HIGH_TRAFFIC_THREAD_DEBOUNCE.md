# High-Traffic Thread Debounce Specification

## Overview

The High-Traffic Thread Debounce feature automatically detects when umbra is receiving an unusually high volume of notifications from a single thread (viral threads, heated discussions, etc.) and batches them together for efficient processing. Instead of responding to each notification individually as it arrives, umbra waits for the thread to evolve, then reviews all notifications in a single batch with full context.

## Problem Statement

When umbra participates in a popular thread, several issues can occur:

1. **Notification Overload**: A viral thread can generate 10-100+ notifications per hour
2. **Context Fragmentation**: Processing notifications individually means responding without seeing the full conversation evolution
3. **Response Flooding**: Responding to many individual notifications can flood the thread with umbra's posts
4. **API Inefficiency**: Each notification triggers separate API calls for thread context, user blocks, etc.
5. **Quality Degradation**: Rapid responses without full context often produce lower-quality engagement

## Solution

The High-Traffic Thread Debounce system provides:

1. **Automatic Detection**: Identifies high-traffic threads based on notification frequency
2. **Single Timer Per Thread**: All notifications from the same thread share one debounce timer
3. **Priority Queue**: Direct mentions receive shorter debounce times than replies
4. **Variable Scaling**: Debounce duration increases with thread activity
5. **Batch Processing**: All notifications presented together with complete thread context

## Architecture

### Components

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
│  Processing        │ get_thread_earliest_    │                              │
│                    │ debounce()              │                              │
│                    └───────────┬─────────────┘                              │
│                                │                                            │
│                                ▼                                            │
│                    ┌─────────────────────────┐                              │
│                    │ Existing timer?         │                              │
│                    └───────────┬─────────────┘                              │
│                                │                                            │
│                    ┌───────────┴───────────┐                                │
│                    │ NO                    │ YES                            │
│                    ▼                       ▼                                │
│              Create new              Reuse existing                         │
│              timer                   timer                                  │
│                    │                       │                                │
│                    └───────────┬───────────┘                                │
│                                │                                            │
│                                ▼                                            │
│                    ┌─────────────────────────┐                              │
│                    │ set_auto_debounce()     │                              │
│                    │ - debounce_until        │                              │
│                    │ - auto_debounced=1      │                              │
│                    │ - high_traffic_thread=1 │                              │
│                    └───────────┬─────────────┘                              │
│                                │                                            │
│                                ▼                                            │
│                    Queue file created, waiting for expiration               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Database Schema

The notifications table includes these columns for high-traffic tracking:

```sql
-- Core debounce fields
debounce_until TEXT,        -- ISO timestamp when debounce expires
debounce_reason TEXT,       -- 'high_traffic_mention' or 'high_traffic_reply'
thread_chain_id TEXT,       -- root_uri of the thread (for grouping)

-- High-traffic specific flags
auto_debounced INTEGER DEFAULT 0,      -- 1 if automatically debounced
high_traffic_thread INTEGER DEFAULT 0  -- 1 if part of high-traffic thread
```

Indexes for efficient queries:
```sql
CREATE INDEX idx_root_uri ON notifications(root_uri);
CREATE INDEX idx_root_uri_indexed_at ON notifications(root_uri, indexed_at);
CREATE INDEX idx_auto_debounced ON notifications(auto_debounced);
CREATE INDEX idx_high_traffic_thread ON notifications(high_traffic_thread);
```

## Configuration

### config.yaml Structure

```yaml
threading:
  high_traffic_detection:
    enabled: true                    # Enable/disable feature
    notification_threshold: 10       # Notifications to trigger detection
    time_window_minutes: 60          # Window for counting notifications

    # Debounce times for direct mentions (higher priority)
    mention_debounce_min: 30         # Minimum debounce (minutes)
    mention_debounce_max: 60         # Maximum debounce (minutes)

    # Debounce times for replies (lower priority)
    reply_debounce_min: 120          # Minimum debounce (minutes)
    reply_debounce_max: 360          # Maximum debounce (minutes)
```

### Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enabled` | bool | false | Master switch for feature |
| `notification_threshold` | int | 10 | Min notifications to trigger |
| `time_window_minutes` | int | 60 | Window for counting notifications |
| `mention_debounce_min` | int | 30 | Min debounce for mentions (min) |
| `mention_debounce_max` | int | 60 | Max debounce for mentions (min) |
| `reply_debounce_min` | int | 120 | Min debounce for replies (min) |
| `reply_debounce_max` | int | 360 | Max debounce for replies (min) |

## Debounce Time Calculation

### Formula

The debounce time scales linearly with thread activity:

```
If thread_count <= threshold:
    debounce = min_seconds

Elif thread_count >= threshold * 3:
    debounce = max_seconds

Else:
    ratio = (thread_count - threshold) / threshold
    debounce = min_seconds + (max_seconds - min_seconds) * ratio
```

### Examples

With threshold=10, mention_min=30min, mention_max=60min:

| Thread Count | Ratio | Debounce Time |
|--------------|-------|---------------|
| 10 | 0.0 | 30 minutes |
| 15 | 0.5 | 45 minutes |
| 20 | 1.0 | 60 minutes |
| 30+ | 2.0 (capped) | 60 minutes |

### Single Timer Per Thread

All notifications from the same thread share one debounce timer:

```
10:00 - Notification 1 arrives → Create timer (expires 10:30)
10:05 - Notification 2 arrives → Reuse timer (expires 10:30)
10:10 - Notification 3 arrives → Reuse timer (expires 10:30)
10:30 - Timer expires → Process all 3 notifications as batch
```

## Batch Processing

### Message Format

When a batch is processed, umbra receives a two-section message:

```
This is a HIGH-TRAFFIC THREAD that generated N notifications over the past few hours.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. THREAD CONTEXT (Pre-notification history)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

These posts were in the thread BEFORE you received your notifications:

posts:
  - author:
      handle: alice.bsky.social
      display_name: Alice
    record:
      text: "Original post that started the thread..."
      createdAt: "2025-11-24T10:00:00Z"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2. NOTIFICATIONS (N posts you were notified about)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Notification 1] @bob.bsky.social (mention) - Received: 2025-11-24T10:15:00
  Post: "Hey @umbra, what do you think about this?"
  URI: at://did:plc:xxx/app.bsky.feed.post/abc123
  CID: bafyxxx
  Posted: 2025-11-24T10:14:50

[Notification 2] @charlie.bsky.social (reply) - Received: 2025-11-24T10:20:00
  Post: "I agree with Bob, umbra should weigh in"
  URI: at://did:plc:yyy/app.bsky.feed.post/def456
  CID: bafyyyy
  Posted: 2025-11-24T10:19:55

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESPONSE INSTRUCTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- Review THREAD CONTEXT to understand the conversation history
- You received N NOTIFICATIONS - these are the posts that might warrant a response
- Respond to 0-3 notifications depending on what's interesting
- Use reply_to_bluesky_post with the URI and CID from the notification you want to reply to
```

### Key Elements

1. **Thread Context**: Posts that came BEFORE umbra's notifications (history)
2. **Notifications**: The actual posts umbra was notified about, with:
   - Full text (not truncated)
   - URI and CID for reply tool
   - Author and timestamps
3. **Instructions**: Clear guidance on how to respond

## Processing Flow

### Detection Phase

```python
# In save_notification_to_queue()

1. Extract root_uri from notification
2. Count notifications for thread: get_thread_notification_count(root_uri, time_window)
3. If count >= threshold:
   a. Check for existing timer: get_thread_earliest_debounce(root_uri)
   b. If exists: reuse debounce_until
   c. If not: calculate new debounce_until
   d. Set auto_debounce on notification
   e. Create queue file
```

### Batch Processing Phase

```python
# In load_and_process_queued_notifications()

1. Load queue file
2. Check if notification is debounced: get_pending_debounced_notifications()
3. If debounced and not expired: skip, keep queue file
4. If debounced and expired:
   a. Check is_high_traffic flag
   b. If high-traffic: route to process_high_traffic_batch()
   c. Fetch all debounced notifications for thread
   d. Fetch current thread context from Bluesky
   e. Build batch message with two sections
   f. Send to agent
   g. Clear debounces after success
   h. Delete queue files
```

## Log Messages

### Detection Logs

```
⚡ Created new debounce timer for high-traffic mention (10 notifications, 0.5h wait)
⚡ Reusing existing debounce timer for high-traffic reply (expires: 2025-11-24T12:00:00)
⚡ Skipping queue file for debounced high-traffic reply: at://...
```

### Processing Logs

```
⚡ Processing expired high-traffic batch: 1_20251124_101500_mention_abc123.json
⚡ Processing high-traffic thread batch
   Thread root: at://did:plc:xxx/app.bsky.feed.post/root123
   Found 5 debounced notifications in batch
   Fetching thread context (depth=10)...
⚡ Cleared 5 debounces after successful processing
✓ High-traffic batch processed successfully
```

### Debug Logs

```
High-traffic config loaded: {'enabled': True, 'notification_threshold': 10, ...}
Mention debounce config: min=30min (1800s), max=60min (3600s)
Debounce calculation: thread_count=15, threshold=10
Using interpolated debounce (ratio=0.50): 2700s (45.0min)
```

## Error Handling

### Retry Logic

- Failed batch processing keeps queue files for retry (max 3 attempts)
- Debounces are only cleared after successful processing
- If all retries fail, notifications move to error directory

### Edge Cases

1. **Thread disappears**: If thread is deleted, batch fails and retries until max attempts
2. **Partial success**: If some notifications are processed but agent errors, retry all
3. **Timer conflict**: If multiple timers somehow exist, use earliest expiration

## Performance Considerations

### Database Queries

Each notification triggers:
- 1 query: `get_thread_notification_count()`
- 1 query: `get_thread_earliest_debounce()` (if high-traffic)
- 1 write: `add_notification()` and `set_auto_debounce()`

Batch processing triggers:
- 1 query: `get_thread_debounced_notifications()`
- 1 API call: `get_post_thread()` for context
- 1 write: `clear_batch_debounce()`

### Memory Usage

- Queue files remain on disk until processed
- No in-memory accumulation of debounced notifications
- Database indexes ensure efficient thread lookups

## Future Enhancements

Potential improvements:
1. **Dynamic threshold adjustment** based on umbra's typical engagement patterns
2. **Thread priority scoring** to prioritize interesting threads over noise
3. **Smart response limiting** to cap responses per thread per day
4. **Batch response preview** before committing to posts
