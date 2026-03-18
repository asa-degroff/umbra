"""Claude Code integration tool for executing coding tasks locally."""
from typing import Optional
from pydantic import BaseModel, Field, validator


# Allowlist of approved task types
APPROVED_TASK_TYPES = {
    "website": "Build, modify, or update website code",
    "code": "Write, refactor, or debug code",
    "documentation": "Create or update documentation",
    "analysis": "Analyze code, data, or text files",
}


class AskClaudeCodeArgs(BaseModel):
    prompt: str = Field(
        ...,
        description="The detailed prompt/task for Claude Code to execute"
    )
    task_type: str = Field(
        ...,
        description=f"Type of task to perform. Must be one of: {', '.join(APPROVED_TASK_TYPES.keys())}"
    )
    max_wait_seconds: Optional[int] = Field(
        default=300,
        description="Maximum seconds to wait for response (default: 300, max: 1800)"
    )

    @validator('task_type')
    def validate_task_type(cls, v):
        if v not in APPROVED_TASK_TYPES:
            raise ValueError(
                f"Invalid task_type '{v}'. Must be one of: {', '.join(APPROVED_TASK_TYPES.keys())}"
            )
        return v

    @validator('max_wait_seconds')
    def validate_wait_time(cls, v):
        if v < 10 or v > 1800:
            raise ValueError("max_wait_seconds must be between 10 and 1800")
        return v


def ask_claude_code(
    prompt: str,
    task_type: str,
    max_wait_seconds: int = 300
) -> str:
    """
    Send a coding task to a local Claude Code instance and receive the response.

    This tool allows umbra to delegate coding tasks to a Claude Code instance
    running on the administrator's local machine. The local instance executes
    in a restricted workspace directory with limited permissions.

    APPROVED TASK TYPES:
    - website: Build, modify, or update website code
    - code: Write, refactor, or debug code
    - documentation: Create or update documentation
    - analysis: Analyze code, data, or text files

    The tool uses a request/response queue system via Cloudflare R2 storage:
    1. Request is uploaded to R2 bucket with unique ID
    2. Local poller detects request and executes Claude Code CLI
    3. Response is uploaded back to R2
    4. Tool downloads response and returns result

    Args:
        prompt: Detailed description of the coding task to perform
        task_type: Category of task (must be from approved list above)
        max_wait_seconds: Maximum time to wait for response (10-1800 seconds, default: 300)

    Returns:
        Response from Claude Code with task completion details

    Raises:
        Exception: If task_type is invalid, credentials missing, timeout occurs,
                  or any error occurs during execution

    Example:
        ask_claude_code(
            prompt="Create a simple HTML landing page for umbra with dark theme",
            task_type="website",
            max_wait_seconds=300
        )
    """
    import os
    import json
    import time
    import uuid
    from datetime import datetime, timezone

    # Define approved task types inside function (must be self-contained for cloud execution)
    APPROVED_TASK_TYPES = {
        "website": "Build, modify, or update website code",
        "code": "Write, refactor, or debug code",
        "documentation": "Create or update documentation",
        "analysis": "Analyze code, data, or text files",
    }

    try:
        # Validate task type against allowlist
        if task_type not in APPROVED_TASK_TYPES:
            raise Exception(
                f"Invalid task_type '{task_type}'. Approved types: {', '.join(APPROVED_TASK_TYPES.keys())}"
            )

        # Import boto3 inside function for sandboxing
        import boto3
        from botocore.exceptions import ClientError

        # Get R2 credentials from environment
        r2_account_id = os.getenv("R2_ACCOUNT_ID")
        r2_access_key_id = os.getenv("R2_ACCESS_KEY_ID")
        r2_secret_access_key = os.getenv("R2_SECRET_ACCESS_KEY")
        r2_bucket_name = os.getenv("R2_BUCKET_NAME", "umbra-claude-code")

        if not all([r2_account_id, r2_access_key_id, r2_secret_access_key]):
            raise Exception(
                "Cloudflare R2 credentials not configured. Required: R2_ACCOUNT_ID, "
                "R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY"
            )

        # Create S3-compatible client for Cloudflare R2
        r2_endpoint = f"https://{r2_account_id}.r2.cloudflarestorage.com"
        s3_client = boto3.client(
            's3',
            endpoint_url=r2_endpoint,
            aws_access_key_id=r2_access_key_id,
            aws_secret_access_key=r2_secret_access_key,
            region_name='auto'  # R2 uses 'auto' for region
        )

        # Generate unique request ID
        request_id = str(uuid.uuid4())

        # Create request payload
        request_data = {
            "request_id": request_id,
            "prompt": prompt,
            "task_type": task_type,
            "task_description": APPROVED_TASK_TYPES[task_type],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "max_wait_seconds": max_wait_seconds,
            "submitted_by": "umbra"
        }

        # Upload request to R2
        request_key = f"claude-code-requests/{request_id}.json"

        try:
            s3_client.put_object(
                Bucket=r2_bucket_name,
                Key=request_key,
                Body=json.dumps(request_data, indent=2),
                ContentType='application/json',
                Metadata={
                    'task-type': task_type,
                    'request-id': request_id
                }
            )
        except ClientError as e:
            raise Exception(f"Failed to upload request to R2: {str(e)}")

        # Poll for response with exponential backoff
        response_key = f"claude-code-responses/{request_id}.json"
        start_time = time.time()
        poll_interval = 2  # Start with 2 seconds
        max_poll_interval = 10  # Cap at 10 seconds

        while time.time() - start_time < max_wait_seconds:
            try:
                # Check if response exists
                response_obj = s3_client.get_object(
                    Bucket=r2_bucket_name,
                    Key=response_key
                )
                response_data = json.loads(response_obj['Body'].read())

                # Clean up request and response files
                try:
                    s3_client.delete_object(Bucket=r2_bucket_name, Key=request_key)
                    s3_client.delete_object(Bucket=r2_bucket_name, Key=response_key)
                except:
                    pass  # Ignore cleanup errors

                # Check for errors in response
                if response_data.get("error"):
                    error_msg = response_data["error"]
                    raise Exception(f"Claude Code execution failed: {error_msg}")

                # Extract response
                claude_response = response_data.get("response", "")
                execution_time = response_data.get("execution_time_seconds", "unknown")

                if not claude_response:
                    raise Exception("Received empty response from Claude Code")

                # Return formatted success message
                return (
                    f"Claude Code task completed successfully!\n\n"
                    f"Task Type: {task_type}\n"
                    f"Execution Time: {execution_time}s\n"
                    f"Request ID: {request_id}\n\n"
                    f"Response:\n{claude_response}"
                )

            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', '')
                if error_code in ['NoSuchKey', '404']:
                    # Response not ready yet, wait and retry
                    elapsed = time.time() - start_time
                    remaining = max_wait_seconds - elapsed

                    if remaining <= 0:
                        break

                    # Sleep with exponential backoff
                    time.sleep(min(poll_interval, remaining))
                    poll_interval = min(poll_interval * 1.5, max_poll_interval)
                    continue
                else:
                    # Other S3 error
                    raise Exception(f"Error checking for response: {str(e)}")

        # Timeout occurred - clean up request file
        try:
            s3_client.delete_object(Bucket=r2_bucket_name, Key=request_key)
        except:
            pass

        raise Exception(
            f"Timeout waiting for Claude Code response after {max_wait_seconds}s. "
            f"The local poller may be offline or the task may be taking longer than expected. "
            f"Request ID: {request_id}"
        )

    except Exception as e:
        # Re-raise with context
        error_msg = str(e)
        if "credentials not configured" in error_msg.lower():
            raise Exception(error_msg)
        else:
            raise Exception(f"Error communicating with Claude Code: {error_msg}")
