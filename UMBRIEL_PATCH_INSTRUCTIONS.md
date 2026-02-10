# Umbriel Integration - R2 Queue Pattern

## Architecture

Umbra↔Umbriel communication uses a Cloudflare R2 queue pattern (same as `ask_claude_code`):

1. **Umbra** calls `ask_umbriel()` tool → uploads request to `umbriel-requests/{id}.json` in R2
2. **umbriel_poller.py** (local daemon) polls R2, finds request, sends to Umbriel via `openclaw agent -m "..."`
3. Poller uploads response to `umbriel-responses/{id}.json`
4. Tool polls for response, downloads it, returns to Umbra

Same bucket (`umbra-claude-code`) as Claude Code integration, different key prefixes.

## Setup

### 1. Register the tool in `register_tools.py`

```python
from tools.ask_umbriel import ask_umbriel, AskUmbrielArgs

# Add to TOOL_CONFIGS:
{
    "func": ask_umbriel,
    "args_schema": AskUmbrielArgs,
    "description": "Send a question to Umbriel, the server's technical advisor AI. Returns the response synchronously.",
    "tags": ["umbriel", "advisor", "inter-agent", "openclaw"]
},
```

### 2. Ensure R2 env vars are set in Letta sandbox

The tool needs these environment variables (same as `ask_claude_code`):
- `R2_ACCOUNT_ID`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_BUCKET_NAME` (default: `umbra-claude-code`)

### 3. Run the poller daemon

```bash
cd /home/asa/umbra
python umbriel_poller.py --verbose
```

Or run in background:
```bash
nohup python umbriel_poller.py >> logs/umbriel_poller.log 2>&1 &
```

Can also run alongside `claude_code_poller.py` - they use different R2 prefixes and don't interfere.

### 4. No bsky.py changes needed

The old signal-string intercept in bsky.py has been removed. The tool now communicates directly via R2 — no bsky.py involvement required.

## Umbriel→Umbra Direction

The reverse direction (Umbriel sending messages to Umbra) still uses `send_to_umbra.py` via the Letta client API. That's a separate mechanism and unchanged.

## Files

- `tools/ask_umbriel.py` — Letta sandbox tool (uploads request, polls for response)
- `umbriel_poller.py` — Local daemon (polls requests, calls OpenClaw, uploads responses)
- `umbriel_bridge.py` — **DEPRECATED** (old signal-string approach, kept for reference)
- `send_to_umbra.py` — Umbriel→Umbra direction (unchanged)
