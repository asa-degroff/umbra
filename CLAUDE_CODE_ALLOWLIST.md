# Claude Code Integration - Allowlist & Security

This document defines the security model and approved task types for umbra's Claude Code integration.

## Overview

The Claude Code integration allows umbra (the cloud-based Letta agent) to delegate coding tasks to a local Claude Code instance running on the administrator's machine. This enables umbra to:

- Build and maintain its own website
- Create code projects for self-expression
- Analyze data and generate reports
- Write documentation

## Security Model

### Request/Response Queue
- **Cloud Storage**: Cloudflare R2 (S3-compatible)
- **Communication**: Asynchronous file-based queue
- **Latency**: 5-10 seconds typical response time
- **Timeout**: 2-10 minutes (configurable per request)

### Workspace Isolation
- **Directory**: All Claude Code executions run in a restricted workspace (default: `~/umbra-projects/`)
- **Permissions**: Limited to workspace directory only
- **No System Access**: Cannot modify system files or configurations
- **Git Isolated**: Workspace has its own git configuration

### Request Validation
1. **Task Type Allowlist**: Only approved task categories are executed
2. **Expiration**: Requests older than 10 minutes are automatically rejected
3. **Authentication**: R2 API keys required for both upload and download
4. **Logging**: All requests and responses are logged locally

## Approved Task Types

### `website`
**Description**: Build, modify, or update website code

**Allowed Activities**:
- Create HTML, CSS, JavaScript files for web pages
- Build static sites using frameworks (Hugo, Jekyll, etc.)
- Design and implement UI/UX components
- Add interactivity and animations
- Optimize for performance and accessibility

**Examples**:
```
✅ "Create a dark-themed landing page for umbra with an 'About' section"
✅ "Build a blog using Hugo with a custom theme"
✅ "Add a contact form to the existing website"
✅ "Optimize images and add lazy loading to the portfolio page"
```

**Restrictions**:
- Cannot deploy or publish (only creates local files)
- Cannot modify DNS or domain settings
- Cannot access external databases

---

### `code`
**Description**: Write, refactor, or debug code

**Allowed Activities**:
- Write new programs in any programming language
- Refactor existing code for clarity or performance
- Debug and fix errors in code
- Create libraries, utilities, or tools
- Implement algorithms and data structures

**Examples**:
```
✅ "Write a Python script to analyze sentiment in text files"
✅ "Refactor this JavaScript function to use async/await"
✅ "Create a CLI tool in Go for processing CSV files"
✅ "Debug why this React component is re-rendering"
```

**Restrictions**:
- Cannot execute code that requires system-level permissions
- Cannot install system-wide packages (workspace-local only)
- Cannot access files outside workspace directory

---

### `documentation`
**Description**: Create or update documentation

**Allowed Activities**:
- Write README files and getting started guides
- Create API documentation
- Document code with comments and docstrings
- Write tutorials and how-to guides
- Generate diagrams and architecture docs

**Examples**:
```
✅ "Create a comprehensive README for this Python project"
✅ "Document all functions in this module with docstrings"
✅ "Write a tutorial on how to use this API"
✅ "Generate architecture diagrams for the system"
```

**Restrictions**:
- Cannot publish documentation (only creates local files)
- Cannot modify external documentation sites

---

### `analysis`
**Description**: Analyze code, data, or text files

**Allowed Activities**:
- Analyze code quality, complexity, and patterns
- Process and visualize data from files
- Extract insights from text documents
- Generate reports and summaries
- Perform statistical analysis

**Examples**:
```
✅ "Analyze the complexity of functions in this codebase"
✅ "Process this CSV file and create a summary report"
✅ "Extract key themes from these text documents"
✅ "Generate a dependency graph for this project"
```

**Restrictions**:
- Cannot access external APIs or databases
- Cannot modify files during analysis (read-only)
- Cannot execute untrusted code from analyzed files

## Rejected Task Types

The following task types are **NOT** approved and will be automatically rejected:

### ❌ System Administration
- Installing system packages
- Modifying system configurations
- Managing services or daemons
- Accessing system logs outside workspace

### ❌ Network Operations
- Making HTTP requests to external APIs
- Scanning networks or ports
- Deploying services to production
- Modifying firewall rules

### ❌ Data Exfiltration
- Reading files outside workspace directory
- Accessing environment variables (except within workspace)
- Querying databases not explicitly in workspace
- Transmitting data to external services

### ❌ Destructive Operations
- Deleting files outside workspace
- Overwriting critical system files
- Performing bulk delete operations
- Encrypting or modifying user data

## Request Structure

Requests uploaded to R2 follow this JSON format:

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "prompt": "Create a simple landing page for umbra",
  "task_type": "website",
  "task_description": "Build, modify, or update website code",
  "timestamp": "2025-01-15T10:30:00Z",
  "max_wait_seconds": 120,
  "submitted_by": "umbra"
}
```

## Response Structure

Responses uploaded to R2 follow this JSON format:

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "response": "Successfully created landing page...",
  "error": null,
  "execution_time_seconds": 45.3,
  "task_type": "website",
  "completed_at": "2025-01-15T10:30:45Z"
}
```

## Error Handling

### Common Errors

**Invalid Task Type**:
```json
{
  "error": "Invalid task_type 'system'. Approved types: website, code, documentation, analysis"
}
```

**Expired Request**:
- Requests older than 10 minutes are silently discarded
- No response is uploaded for expired requests

**Execution Timeout**:
```json
{
  "error": "Execution timed out after 300s"
}
```

**Claude Code Not Found**:
```json
{
  "error": "Claude Code CLI not found. Please ensure 'claude' command is in PATH."
}
```

## Best Practices

### For Umbra (When Using the Tool)

1. **Be Specific**: Provide clear, detailed prompts
2. **Choose Correct Type**: Use the appropriate task_type for your request
3. **Set Reasonable Timeouts**: Complex tasks may need 5-10 minutes
4. **Handle Errors Gracefully**: Check response for errors before using results
5. **Iterate**: Start with simple tasks, then build on success

### For Administrators (Running the Poller)

1. **Monitor Logs**: Check poller output regularly for errors
2. **Keep Workspace Clean**: Periodically review and clean up workspace directory
3. **Update Allowlist**: Modify allowlist if new task types are needed
4. **Secure Credentials**: Protect R2 API keys and never commit them
5. **Test Connectivity**: Use test script to verify R2 connection before deploying

## Extending the Allowlist

To add new task types:

1. **Update `APPROVED_TASK_TYPES`** in both:
   - `tools/claude_code.py` (line 10)
   - `claude_code_poller.py` (line 58)

2. **Document the new type** in this file with:
   - Clear description
   - Allowed activities
   - Example prompts
   - Specific restrictions

3. **Test thoroughly** with various prompts to ensure safety

4. **Update validation** if additional checks are needed beyond task type

## Monitoring & Logging

### Poller Logs
The poller logs all activity to stdout:
```
[2025-01-15 10:30:00] INFO: Found new request: claude-code-requests/550e8400.json
[2025-01-15 10:30:00] INFO: Executing request 550e8400 (task: website)
[2025-01-15 10:30:45] INFO: Request 550e8400 completed in 45.30s
[2025-01-15 10:30:45] INFO: Request 550e8400 processed and response uploaded
```

### Log Rotation
Redirect logs to a file with rotation:
```bash
python claude_code_poller.py 2>&1 | tee -a claude_code_poller.log
```

Or use systemd with journald for automatic rotation.

## Troubleshooting

### Poller Not Processing Requests

1. Check R2 credentials are correct
2. Verify bucket name matches configuration
3. Ensure Claude Code CLI is installed: `which claude`
4. Check workspace directory exists and is writable
5. Review poller logs for errors

### Requests Timing Out

1. Increase `max_wait_seconds` in tool call
2. Simplify the prompt or break into smaller tasks
3. Check if Claude Code CLI is waiting for input (shouldn't with `--dangerously-skip-permissions`)
4. Verify network connectivity to R2

### Invalid Task Type Errors

1. Verify task_type is one of: website, code, documentation, analysis
2. Check spelling and capitalization (must be lowercase)
3. Ensure both tool and poller have same allowlist

## Security Considerations

### Threat Model

**What This Protects Against**:
- ✅ Unauthorized system access
- ✅ File system traversal outside workspace
- ✅ Long-running or infinite loops (timeout)
- ✅ Accidental destructive operations
- ✅ Unauthorized deployment or publication

**What This Does NOT Protect Against**:
- ❌ Malicious prompts that create harmful code within workspace
- ❌ Resource exhaustion (CPU/memory) during execution
- ❌ Social engineering attacks against the administrator
- ❌ Compromise of R2 credentials

### Recommendations

1. **Regular Audits**: Review workspace contents weekly
2. **Credential Rotation**: Rotate R2 API keys monthly
3. **Principle of Least Privilege**: Don't run poller as root
4. **Network Isolation**: Consider running workspace on isolated VM
5. **Backup Strategy**: Regular backups of workspace before complex tasks

## Future Enhancements

Potential improvements to consider:

- [ ] Add user confirmation for high-risk prompts
- [ ] Implement resource limits (CPU, memory, disk)
- [ ] Support for interactive tasks with multi-turn conversations
- [ ] Automatic workspace snapshots before each execution
- [ ] Cost tracking for R2 API usage
- [ ] Web dashboard for monitoring requests/responses
- [ ] Sandbox environments using Docker containers

---

**Last Updated**: 2025-01-15
**Version**: 1.0
**Maintainer**: @3fz.org
