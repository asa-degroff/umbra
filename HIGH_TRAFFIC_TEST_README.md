# High-Traffic Thread Testing

## Overview

This document describes the test suite for the high-traffic thread debounce feature, which was enhanced to provide per-post metadata for selective agent responses.

## Test Files

### `test_high_traffic_batch_processing.py`

Comprehensive test suite that validates:

1. **Per-Post Metadata Extraction**
   - Verifies thread flattening extracts all posts correctly
   - Confirms metadata includes URI, CID, author, timestamp, and text preview
   - Validates metadata format matches agent requirements

2. **Batch Processing Message Format**
   - Tests message structure includes all required sections
   - Verifies POST METADATA table is properly formatted
   - Ensures INSTRUCTIONS guide agent to selective responses
   - Confirms NOTIFICATIONS RECEIVED summary is included

3. **High-Traffic Detection**
   - Simulates 11 notifications in a 30-minute window
   - Verifies threshold-based detection (default: 6 notifications)
   - Tests auto-debounce flag setting
   - Validates database operations

4. **End-to-End Simulation**
   - Creates realistic high-traffic scenario
   - Generates complete agent message with metadata
   - Verifies message length and structure

## Running the Tests

```bash
# Activate virtual environment
source .venv/bin/activate

# Run high-traffic batch processing tests
python test_high_traffic_batch_processing.py

# Run original high-traffic database tests
python test_high_traffic.py
```

## Test Output

Successful test run shows:

```
✓ Thread flattening extracts all posts
✓ Per-post metadata includes URI, CID, author, timestamp, text
✓ Message format provides metadata table for agent
✓ Agent can respond to any post using metadata
✓ High-traffic detection and auto-debounce work correctly
```

## What the Tests Validate

### Metadata Extraction
Each post in the thread is extracted with:
```
[Post 1] @user0.bsky.social at 2025-11-23T18:24:52.117907
  URI: at://did:plc:test/app.bsky.feed.post/root123
  CID: cid0
  Text: This is post 1 in the thread...
```

### Message Structure
The agent receives a properly formatted message with:
- **THREAD CONTEXT**: Complete thread in YAML format
- **POST METADATA**: Table with URI/CID for each post
- **NOTIFICATIONS RECEIVED**: Summary of who engaged when
- **INSTRUCTIONS**: Guidance for selective responses (0-3 posts)

### High-Traffic Detection
- Configurable threshold (default: 6 notifications in 30 minutes)
- Variable debounce times based on activity level
- Priority queue (mentions: 30-60 min, replies: 2-6 hours)

## Integration with Main Bot

When umbra is running (via `python bsky.py`):

1. High-traffic threads are automatically detected
2. Notifications are debounced and batched together
3. After debounce period expires:
   - Thread is fetched from Bluesky
   - Posts are flattened and metadata extracted
   - Agent receives complete context with metadata table
4. Agent can respond to ANY post using the metadata
5. Queue files are properly cleaned up

## Monitoring

Look for these log messages:

- `⚡ Auto-debounced high-traffic mention (N notifications, X.Xh wait)`
- `⚡ Processing high-traffic thread batch`
- `Sending high-traffic batch to agent | N posts in thread | M notifications`

## Related Files

- `bsky.py`: Main bot implementation with `process_high_traffic_batch()`
- `notification_db.py`: Database methods for debounce tracking
- `config.yaml`: High-traffic detection configuration
- `test_high_traffic.py`: Database-focused tests

## Configuration

Edit `config.yaml` to tune high-traffic detection:

```yaml
threading:
  high_traffic_detection:
    enabled: true
    notification_threshold: 6  # Number of notifications to trigger
    time_window_minutes: 30    # Time window for counting
    mention_debounce_min: 30   # Minimum wait for mentions (minutes)
    mention_debounce_max: 60   # Maximum wait for mentions
    reply_debounce_min: 120    # Minimum wait for replies (2 hours)
    reply_debounce_max: 360    # Maximum wait for replies (6 hours)
```

## Next Steps

1. Deploy and monitor with real high-traffic threads
2. Verify agent successfully uses metadata to respond selectively
3. Tune configuration based on observed thread patterns
4. Monitor API usage reduction from batch processing

## Bug Fixes Included

This test suite also validates fixes for:

1. **Regular debounce processing**: Ensures `process_debounced_thread()` properly processes agent responses
2. **Queue file cleanup**: Verifies no duplicate notifications after debounce
3. **Tool call extraction**: Confirms both `add_post_to_bluesky_reply_thread` and `reply_to_bluesky_post` are handled
