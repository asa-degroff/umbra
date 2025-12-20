# Consecutive Chain Processing

When users post multi-part messages on Bluesky (e.g., a thread like "1/3", "2/3", "3/3"), umbra receives separate notifications for each post. Consecutive chain processing ensures umbra:

1. Responds to the **complete thought** by finding the last post in the chain
2. **Prevents duplicate responses** by marking all chain notifications as processed

## Problem Statement

When someone mentions umbra in a multi-part message:

```
@alice posts:
├── "1/3 Hey @umbra, I've been thinking about..."    ← Notification 1
├── "2/3 ...and this leads me to wonder..."          ← Notification 2
└── "3/3 ...what do you think about all this?"       ← Notification 3
```

Without chain processing:
- Umbra might respond to "1/3" before seeing the complete thought
- Umbra might respond to each notification separately (3 responses!)
- The conversation becomes fragmented and confusing

## Solution Overview

### 1. Find Last Consecutive Post

When processing a notification, umbra traverses DOWN the reply chain to find the last consecutive post by the same author:

```
Thread structure:
├── Post A by @alice (notification) ← Start here
│   └── Post B by @alice (consecutive)
│       └── Post C by @alice (consecutive) ← Response target
│           └── Post D by @bob (different author, stop)
```

The function `find_last_consecutive_post_in_chain()` returns Post C's details (uri, cid, text).

### 2. Mark Chain as Processed

After responding to the last post, umbra marks ALL notifications from that author in the same thread (within a time window) as processed:

```
Notifications in queue:
├── Post A notification → marked 'processed'
├── Post B notification → marked 'processed'
└── Post C notification → marked 'processed' (responded to)
```

This prevents processing Post A or B later and sending duplicate responses.

---

## Implementation Details

### Chain Detection

The chain detection happens in `bsky.py` during notification processing:

```python
# Find the last consecutive post by the same author in the direct reply chain
last_consecutive_post = bsky_utils.find_last_consecutive_post_in_chain(
    thread.thread,
    author_handle
)

if last_consecutive_post:
    last_uri, last_cid, last_text = last_consecutive_post
    if last_uri != uri:
        # Use the last post in the chain instead of the notification post
        uri = last_uri
        cid = last_cid
        is_using_last_consecutive = True
```

### Chain Traversal Algorithm

`find_last_consecutive_post_in_chain()` in `bsky_utils.py`:

1. Start at the notification post's thread node
2. Check if current post is by the target author
3. Look for replies to the current post
4. If any reply is by the same author, move to that reply
5. Repeat until no more replies by the same author exist
6. Return the last post found

```python
while True:
    if not current_node.replies:
        break  # No more replies

    next_node = None
    for reply in current_node.replies:
        reply_author = reply.post.author.handle
        if reply_author == author_handle:
            next_node = reply
            last_uri = reply.post.uri
            last_cid = reply.post.cid
            break

    if next_node is None:
        break  # No consecutive post by same author

    current_node = next_node
```

### Chain Cleanup

After successfully responding, `mark_consecutive_chain_processed()` in `notification_db.py`:

```python
NOTIFICATION_DB.mark_consecutive_chain_processed(
    root_uri=root_uri,
    author_did=author_did,
    reference_time=indexed_at
)
```

**Parameters:**
- `root_uri`: Thread root to scope the search
- `author_did`: Author's DID to match
- `reference_time`: Center of the time window
- `time_window_seconds`: Window size (default: 120 seconds)

**SQL Update:**
```sql
UPDATE notifications
SET status = 'processed', processed_at = ?
WHERE root_uri = ?
AND author_did = ?
AND indexed_at >= ? AND indexed_at <= ?
AND status = 'pending'
```

---

## Parent Chain Detection

There's also an inverse function `find_consecutive_parent_posts_by_author()` that traverses UP the parent chain. This is used for high-traffic thread batch processing to provide context about multi-part messages:

```
Thread structure:
├── Post A by @alice (first part)
│   └── Post B by @alice (second part)
│       └── Post C by @alice (notification) ← Start here
```

Returns `[Post A, Post B]` in chronological order.

---

## Prompt Modification

When using the last consecutive post, umbra's prompt is modified to explain the context:

**Without consecutive chain:**
> "MOST RECENT POST (the mention you're responding to)"

**With consecutive chain:**
> "LAST POST IN CONSECUTIVE CHAIN (the post you're responding to)"
> "The YAML above shows the complete conversation thread. The metadata below points to the LAST POST in the consecutive chain by this author, not the first mention. This allows you to see and respond to their complete thought."

---

## Time Window

The default time window is **120 seconds** (2 minutes). This means:
- Notifications within 2 minutes of each other
- From the same author
- In the same thread

...are considered part of the same consecutive chain.

This window is conservative to avoid incorrectly grouping unrelated posts while still catching typical multi-part message patterns.

---

## Log Messages

**Chain detected:**
```
Found last consecutive post in chain:
    mention_uri: at://did:plc:abc/app.bsky.feed.post/123
    last_consecutive_uri: at://did:plc:abc/app.bsky.feed.post/456
    is_same_post: False
```

**Chain cleanup:**
```
Marked 3 consecutive chain notifications as processed (author: did:plc:abc..., root: ...xyz789)
```

---

## Edge Cases

### Single Post (No Chain)
If the notification is the only post by that author in the thread, no chain processing occurs. The notification is processed normally.

### Chain in Wrong Direction
If someone replies to umbra's post with a multi-part message, the chain detection only looks DOWN from the notification post. It won't traverse up to find earlier posts.

### Interleaved Authors
If two authors are posting alternately (A, B, A, B), each author's posts are treated as separate chains. The detection stops when a different author is encountered.

### Database Sync
Queue files and database may be slightly out of sync. The cleanup marks database entries as processed, and queue files are deleted when their corresponding notification is processed.

---

## Related Files

| File | Function | Purpose |
|------|----------|---------|
| `bsky.py` | Notification processing | Calls chain detection and cleanup |
| `bsky_utils.py` | `find_last_consecutive_post_in_chain()` | Traverses DOWN to find last post |
| `bsky_utils.py` | `find_consecutive_parent_posts_by_author()` | Traverses UP for context |
| `notification_db.py` | `mark_consecutive_chain_processed()` | Marks chain as processed |
