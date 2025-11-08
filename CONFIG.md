# Configuration Guide

### Option 1: Migrate from existing `.env` file (if you have one)
```bash
python migrate_config.py
```

### Option 2: Start fresh with example
1. **Copy the example configuration:**
   ```bash
   cp config.yaml.example config.yaml
   ```

2. **Edit `config.yaml` with your credentials:**
   ```yaml
   # Required: Letta API configuration
   letta:
     api_key: "your-letta-api-key-here"
     project_id: "project-id-here"
   
   # Required: Bluesky credentials
   bluesky:
     username: "your-handle.bsky.social"
     password: "your-app-password"
   ```

3. **Run the configuration test:**
   ```bash
   python test_config.py
   ```

## Configuration Structure

### Letta Configuration
```yaml
letta:
  api_key: "your-letta-api-key-here"     # Required
  timeout: 600                           # API timeout in seconds
  project_id: "your-project-id"          # Required: Your Letta project ID
```

### Bluesky Configuration
```yaml
bluesky:
  username: "handle.bsky.social"         # Required: Your Bluesky handle
  password: "your-app-password"          # Required: Your Bluesky app password
  pds_uri: "https://bsky.social"         # Optional: PDS URI (defaults to bsky.social)
```

### Cloudflare R2 Configuration (Claude Code Integration)
```yaml
cloudflare_r2:
  account_id: "your-r2-account-id"       # Required: Cloudflare R2 account ID
  access_key_id: "your-r2-access-key"    # Required: R2 API access key ID
  secret_access_key: "your-r2-secret"    # Required: R2 API secret access key
  bucket_name: "umbra-claude-code"       # Required: R2 bucket name
```

**Setup Instructions**:
1. Log in to [Cloudflare Dashboard](https://dash.cloudflare.com/)
2. Navigate to R2 Object Storage
3. Create a new bucket named `umbra-claude-code` (or your preferred name)
4. Create two folders in the bucket: `claude-code-requests/` and `claude-code-responses/`
5. Go to "Manage R2 API Tokens" and create a new API token with:
   - Permissions: Read & Write
   - Bucket: Select your bucket or all buckets
6. Save the Access Key ID and Secret Access Key
7. Find your Account ID in the R2 overview page

### Claude Code Configuration
```yaml
claude_code:
  workspace_dir: "~/umbra-projects"      # Directory for Claude Code executions
  approved_tasks:                        # Allowlist of task types
    - "website"
    - "code"
    - "documentation"
    - "analysis"
```

### Bot Behavior
```yaml
bot:
  fetch_notifications_delay: 30          # Seconds between notification checks
  max_processed_notifications: 10000     # Max notifications to track
  max_notification_pages: 20             # Max pages to fetch per cycle
  
  agent:
    name: "umbra"                         # Agent name
    model: "anthropic/claude-haiku-4-5-20251001"          # LLM model to use
    embedding: "openai/text-embedding-3-small"  # Embedding model
    description: "A social media agent dwelling in the umbra."
    max_steps: 100                       # Max steps per agent interaction
    
    # Memory blocks configuration
    blocks:
      zeitgeist:
        label: "zeitgeist"
        value: "I don't currently know anything about what is happening right now."
        description: "A block to store your understanding of the current social environment."
      # ... more blocks
```

### Queue Configuration
```yaml
queue:
  priority_users:                        # Users whose messages get priority
    - "3fz.org"
  base_dir: "queue"                      # Queue directory
  error_dir: "queue/errors"              # Failed notifications
  no_reply_dir: "queue/no_reply"         # No-reply notifications
  processed_file: "queue/processed_notifications.json"
```

### Threading Configuration
```yaml
threading:
  parent_height: 40                      # Thread context depth
  depth: 10                              # Thread context width
  max_post_characters: 300               # Max characters per post
```

### Logging Configuration
```yaml
logging:
  level: "INFO"                          # Root logging level
  loggers:
    void_bot: "INFO"                     # Main bot logger
    void_bot_prompts: "WARNING"          # Prompt logger (set to DEBUG to see prompts)
    httpx: "CRITICAL"                    # HTTP client logger
```

## Environment Variable Fallback

The configuration system still supports environment variables as a fallback:

**Letta Configuration:**
- `LETTA_API_KEY` - Letta API key

**Bluesky Configuration:**
- `BSKY_USERNAME` - Bluesky username
- `BSKY_PASSWORD` - Bluesky password
- `PDS_URI` - Bluesky PDS URI

**Cloudflare R2 Configuration (Claude Code):**
- `R2_ACCOUNT_ID` - Cloudflare R2 account ID
- `R2_ACCESS_KEY_ID` - R2 API access key ID
- `R2_SECRET_ACCESS_KEY` - R2 API secret access key
- `R2_BUCKET_NAME` - R2 bucket name (defaults to "umbra-claude-code")

**Claude Code Configuration:**
- `CLAUDE_CODE_WORKSPACE` - Workspace directory (defaults to "~/umbra-projects")

If both config file and environment variables are present, environment variables take precedence.

## Migration from Environment Variables

If you're currently using environment variables (`.env` file), you can easily migrate to YAML using the automated migration script:

### Automated Migration (Recommended)

```bash
python migrate_config.py
```

The migration script will:
- ✅ Read your existing `.env` file
- ✅ Merge with any existing `config.yaml`
- ✅ Create automatic backups
- ✅ Test the new configuration
- ✅ Provide clear next steps

### Manual Migration

Alternatively, you can migrate manually:

1. Copy your current values from `.env` to `config.yaml`
2. Test with `python test_config.py`
3. Optionally remove the `.env` file (it will still work as fallback)

## Security Notes

- `config.yaml` is automatically added to `.gitignore` to prevent accidental commits
- Store sensitive credentials securely and never commit them to version control
- Consider using environment variables for production deployments
- The configuration loader will warn if it can't find `config.yaml` and falls back to environment variables

## Advanced Configuration

You can programmatically access configuration in your code:

```python
from config_loader import get_letta_config, get_bluesky_config

# Get configuration sections
letta_config = get_letta_config()
bluesky_config = get_bluesky_config()

# Access individual values
api_key = letta_config['api_key']
username = bluesky_config['username']
```
