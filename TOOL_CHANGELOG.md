# Tool Changelog - Bluesky Reply Threading

## Summary
The reply system has been simplified and improved with a new atomic approach for building reply threads.

## Changes Made

### ✅ NEW TOOL: `add_post_to_bluesky_reply_thread`
- **Purpose**: Add a single post to the current Bluesky reply thread atomically
- **Usage**: Call this tool multiple times to build a reply thread incrementally
- **Parameters**:
  - `text` (required): Text content for the post (max 300 characters)
  - `lang` (optional): Language code (defaults to "en-US")
- **Returns**: Confirmation that the post has been queued for the reply thread
- **Error Handling**: If text exceeds 300 characters, the post will be omitted from the thread and you may try again with shorter text

### ❌ REMOVED TOOL: `bluesky_reply`
- This tool has been removed to eliminate confusion
- All reply functionality is now handled through the new atomic approach

## How to Use the New System

### Before (Old Way - NO LONGER AVAILABLE)
```
bluesky_reply(["First reply", "Second reply", "Third reply"])
```

### After (New Way - USE THIS)
```
add_post_to_bluesky_reply_thread("First reply")
add_post_to_bluesky_reply_thread("Second reply") 
add_post_to_bluesky_reply_thread("Third reply")
```

## Benefits of the New Approach

1. **Atomic Operations**: Each post is handled individually, reducing the risk of entire thread failures
2. **Better Error Recovery**: If one post fails validation, others can still be posted
3. **Flexible Threading**: Build reply threads of any length without list construction
4. **Clearer Intent**: Each tool call has a single, clear purpose
5. **Handler-Managed State**: The bsky.py handler manages thread state and proper AT Protocol threading

## Important Notes

- The actual posting to Bluesky is handled by the bsky.py handler, not the tool itself
- Each call to `add_post_to_bluesky_reply_thread` queues a post for the current reply context
- Posts are validated for the 300-character limit before being queued
- Thread state and proper reply chaining is managed automatically by the handler
- Language defaults to "en-US" but can be specified per post if needed

## Migration Guide

If you were previously using `bluesky_reply`, simply replace it with multiple calls to `add_post_to_bluesky_reply_thread`:

**Old approach:**
```
bluesky_reply(["Hello!", "This is a threaded reply.", "Thanks for the mention!"])
```

**New approach:**
```
add_post_to_bluesky_reply_thread("Hello!")
add_post_to_bluesky_reply_thread("This is a threaded reply.")
add_post_to_bluesky_reply_thread("Thanks for the mention!")
```

This change makes the system more robust and easier to use while maintaining all the same functionality.