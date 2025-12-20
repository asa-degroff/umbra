# Scheduled Tasks

Umbra includes a scheduled tasks system that runs various autonomous behaviors at configurable intervals. All scheduled tasks are persistent across restarts - if umbra is restarted, it will resume existing schedules from the database rather than generating new random times.

## Overview

The scheduled tasks system is implemented in `scheduled_prompts.py` and provides:

- **Interval-based scheduling**: Tasks run at fixed intervals (e.g., every 24 hours)
- **Random window scheduling**: Tasks run at random times within a window (e.g., randomly within 36 hours)
- **Persistence**: Schedules survive restarts via SQLite database
- **CLI control**: Tasks can be disabled via command-line arguments

## Available Tasks

| Task | Schedule Type | Window/Interval | Description |
|------|--------------|-----------------|-------------|
| `synthesis` | Fixed interval | Every 24 hours | Deep reflection and memory synthesis |
| `mutuals_engagement` | Random window | Within 36 hours | Engage with mutuals feed |
| `daily_review` | Random window | Within 24 hours | Review own posts from past 24h |
| `feed_engagement` | Random window | Within 24 hours | Read and engage with feeds |
| `curiosities_exploration` | Random window | Within 24 hours | Explore topics from curiosities block |

---

## Task Details

### Synthesis

**Schedule**: Every 24 hours (fixed interval)

**Purpose**: Prompts umbra to synthesize recent experiences and update memory. This is the most comprehensive scheduled task.

**What it does**:
1. Attaches temporal journal blocks (day, month, year) for recording reflections
2. Sends a synthesis prompt to the agent
3. Agent can update memory blocks, create journal entries, and post synthesis content
4. Detaches temporal blocks after completion

**Temporal Blocks**:
- `umbra_day_YYYY_MM_DD`: Daily journal for current date
- `umbra_month_YYYY_MM`: Monthly journal for current month
- `umbra_year_YYYY`: Yearly journal for current year

These blocks are only attached during synthesis/daily review and detached afterward.

---

### Mutuals Engagement

**Schedule**: Random time within 36-hour window

**Purpose**: Proactive engagement with mutual follows on Bluesky.

**What it does**:
1. Prompts agent to use `get_bluesky_feed` to read the Mutuals feed
2. Agent looks for interesting posts from the past day
3. Agent may reply using `reply_to_bluesky_post`

**Prompt excerpt**:
> "Look for posts from the past day that are interesting, thought-provoking, or worth responding to... Choose something that allows you to contribute meaningfully to the conversation."

---

### Daily Review

**Schedule**: Random time within 24-hour window

**Purpose**: Self-reflection on umbra's own posting activity.

**What it does**:
1. Fetches umbra's own posts and replies from the past 24 hours
2. Attaches temporal journal blocks
3. Presents posts to agent with metadata (uri, cid) for potential follow-ups
4. Agent can:
   - Update memory with observations
   - Identify operational anomalies (duplicate posts, errors)
   - Follow up on previous posts using `reply_to_bluesky_post`
   - Create new posts to expand on topics

**Post grouping**: The system intelligently groups reply chains together and includes parent context when umbra replied to someone else's post.

---

### Feed Engagement

**Schedule**: Random time within 24-hour window

**Purpose**: Stay in tune with the network zeitgeist.

**What it does**:
1. Prompts agent to read both 'home' and 'MLBlend' feeds
2. Agent looks for:
   - Interesting discussions or trending topics
   - Posts that spark curiosity
   - Themes or patterns in discussions
3. Agent may create a new post or update memory with observations

---

### Curiosities Exploration

**Schedule**: Random time within 24-hour window

**Purpose**: Intellectual exploration and sharing of evolving understanding.

**What it does**:
1. Agent reviews its `curiosities` memory block for topics to explore
2. Agent searches for information using `search_bluesky_posts` and web search
3. Agent reflects and creates a post sharing the exploration
4. Agent updates curiosities block with new topics for future exploration

**Prompt excerpt**:
> "This is your space for intellectual exploration and sharing your evolving understanding with your network. Let your curiosity guide what you share. You don't need to post a complete answer—questions and open-ended exploration are encouraged."

---

## Configuration

### Command-Line Arguments

All tasks are enabled by default. Disable specific tasks with these flags:

```bash
# Disable individual tasks
python bsky.py --no-synthesis
python bsky.py --no-mutuals-engagement
python bsky.py --no-daily-review
python bsky.py --no-feed-engagement
python bsky.py --no-curiosities

# Combine flags to disable multiple tasks
python bsky.py --no-mutuals-engagement --no-daily-review --no-feed-engagement

# Run only synthesis and curiosities
python bsky.py --no-mutuals-engagement --no-daily-review --no-feed-engagement
```

### Task Configuration in Code

Task parameters are defined in `scheduled_prompts.py` in the `TASK_CONFIGS` dictionary:

```python
TASK_CONFIGS = {
    'synthesis': {
        'enabled': True,
        'is_random_window': False,
        'interval_seconds': 86400,  # 24 hours
        'window_seconds': None,
        'emoji': '🧠',
        'description': 'Synthesis and reflection',
    },
    'mutuals_engagement': {
        'enabled': True,
        'is_random_window': True,
        'interval_seconds': None,
        'window_seconds': 129600,  # 36-hour window
        'emoji': '🤝',
        'description': 'Mutuals engagement',
    },
    # ... etc
}
```

### Customizing Intervals

To change task timing, modify `TASK_CONFIGS` in `scheduled_prompts.py`:

| Parameter | Type | Description |
|-----------|------|-------------|
| `enabled` | bool | Whether task runs by default |
| `is_random_window` | bool | `True` for random scheduling, `False` for fixed interval |
| `interval_seconds` | int | For fixed interval tasks: seconds between runs |
| `window_seconds` | int | For random window tasks: size of random window in seconds |
| `emoji` | str | Emoji shown in log messages |
| `description` | str | Human-readable task description |

---

## Persistence

Scheduled tasks are persisted in the SQLite database (`notifications.db`) in the `scheduled_tasks` table:

```sql
CREATE TABLE scheduled_tasks (
    task_name TEXT PRIMARY KEY,
    next_run_at TEXT,           -- ISO timestamp of next run
    last_run_at TEXT,           -- ISO timestamp of last run
    interval_seconds INTEGER,   -- For interval-based tasks
    is_random_window INTEGER,   -- 1 if random window scheduling
    window_seconds INTEGER,     -- Size of random window
    enabled INTEGER DEFAULT 1   -- Whether task is active
);
```

### Behavior on Restart

When umbra starts:
1. Loads existing schedules from database
2. If a task's scheduled time hasn't passed, uses the existing time
3. If a task's schedule has expired, calculates a new schedule
4. Logs all scheduled times with hours until execution

Example log output:
```
🧠 Synthesis and reflection enabled (every 24.0 hours)
Loaded existing synthesis schedule: 2025-12-20 14:30:00 (18.5 hours from now)
🤝 Mutuals engagement enabled (random within 36h window)
Scheduled mutuals_engagement for 2025-12-20 08:15:00 (12.2 hours from now)
```

---

## Log Messages

Each task type has distinctive log messages:

| Task | Start Message | Complete Message |
|------|---------------|------------------|
| Synthesis | `Preparing synthesis with temporal journal blocks` | `Synthesis message processed successfully` |
| Mutuals Engagement | `Sending mutuals engagement prompt to agent` | `Mutuals engagement message processed successfully` |
| Daily Review | `Fetching posts for daily review` | `Daily review message processed successfully` |
| Feed Engagement | `Sending feed engagement prompt to agent` | `Feed engagement message processed successfully` |
| Curiosities | `Sending curiosities exploration prompt to agent` | `Curiosities exploration message processed successfully` |

---

## Database Migration

If upgrading from a version without scheduled task persistence, run:

```bash
ac && python migrate_scheduled_tasks.py
```

This creates the `scheduled_tasks` table for persistent scheduling.

---

## Related Files

| File | Purpose |
|------|---------|
| `scheduled_prompts.py` | Main module with all scheduled task logic |
| `bsky.py` | Main loop that triggers scheduled tasks |
| `notification_db.py` | Database functions for task persistence |
| `migrate_scheduled_tasks.py` | Migration script for task persistence |
