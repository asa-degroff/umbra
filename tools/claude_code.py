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
        default=120,
        description="Maximum seconds to wait for response (default: 120)"
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
        if v < 10 or v > 600:
            raise ValueError("max_wait_seconds must be between 10 and 600")
        return v


def ask_claude_code(
    prompt: str,
    task_type: str,
    max_wait_seconds: int = 120
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
        max_wait_seconds: Maximum time to wait for response (10-600 seconds)

    Returns:
        Response from Claude Code with task completion details

    Raises:
        Exception: If task_type is invalid, credentials missing, timeout occurs,
                  or any error occurs during execution

    Example:
        ask_claude_code(
            prompt="Create a simple HTML landing page for umbra with dark theme",
            task_type="website",
            max_wait_seconds=180
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

        # Import required libraries (using standard library + requests)
        import hashlib
        import hmac
        from urllib.parse import quote
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError, URLError

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

        # Helper function for AWS Signature Version 4
        def sign_request(method, url, headers, payload=''):
            """Create AWS Signature Version 4 for R2 request."""
            # Parse URL
            from urllib.parse import urlparse
            parsed = urlparse(url)
            host = parsed.netloc
            path = parsed.path or '/'

            # Create canonical request
            canonical_headers = f'host:{host}\n'
            signed_headers = 'host'
            payload_hash = hashlib.sha256(payload.encode('utf-8')).hexdigest()
            canonical_request = f'{method}\n{path}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}'

            # Create string to sign
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            date_stamp = timestamp[:8]
            credential_scope = f'{date_stamp}/auto/s3/aws4_request'
            string_to_sign = f'AWS4-HMAC-SHA256\n{timestamp}\n{credential_scope}\n{hashlib.sha256(canonical_request.encode()).hexdigest()}'

            # Calculate signature
            def get_signature_key(key, date, region, service):
                k_date = hmac.new(f'AWS4{key}'.encode(), date.encode(), hashlib.sha256).digest()
                k_region = hmac.new(k_date, region.encode(), hashlib.sha256).digest()
                k_service = hmac.new(k_region, service.encode(), hashlib.sha256).digest()
                k_signing = hmac.new(k_service, 'aws4_request'.encode(), hashlib.sha256).digest()
                return k_signing

            signing_key = get_signature_key(r2_secret_access_key, date_stamp, 'auto', 's3')
            signature = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()

            # Create authorization header
            authorization = (
                f'AWS4-HMAC-SHA256 Credential={r2_access_key_id}/{credential_scope}, '
                f'SignedHeaders={signed_headers}, Signature={signature}'
            )

            headers['Authorization'] = authorization
            headers['x-amz-date'] = timestamp
            headers['x-amz-content-sha256'] = payload_hash
            return headers

        # R2 endpoint
        r2_endpoint = f"https://{r2_bucket_name}.{r2_account_id}.r2.cloudflarestorage.com"

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
        request_url = f"{r2_endpoint}/{request_key}"
        request_body = json.dumps(request_data, indent=2)

        try:
            headers = {'Content-Type': 'application/json'}
            headers = sign_request('PUT', request_url, headers, request_body)

            req = Request(request_url, data=request_body.encode('utf-8'), headers=headers, method='PUT')
            with urlopen(req, timeout=30) as response:
                if response.status not in [200, 201]:
                    raise Exception(f"Failed to upload request: HTTP {response.status}")
        except (HTTPError, URLError) as e:
            raise Exception(f"Failed to upload request to R2: {str(e)}")

        # Poll for response with exponential backoff
        response_key = f"claude-code-responses/{request_id}.json"
        response_url = f"{r2_endpoint}/{response_key}"
        start_time = time.time()
        poll_interval = 2  # Start with 2 seconds
        max_poll_interval = 10  # Cap at 10 seconds

        while time.time() - start_time < max_wait_seconds:
            try:
                # Check if response exists
                headers = {}
                headers = sign_request('GET', response_url, headers, '')

                req = Request(response_url, headers=headers, method='GET')
                with urlopen(req, timeout=30) as response:
                    response_body = response.read().decode('utf-8')
                    response_data = json.loads(response_body)

                # Clean up request and response files
                try:
                    # Delete request file
                    delete_url = f"{r2_endpoint}/{request_key}"
                    del_headers = {}
                    del_headers = sign_request('DELETE', delete_url, del_headers, '')
                    del_req = Request(delete_url, headers=del_headers, method='DELETE')
                    urlopen(del_req, timeout=30)

                    # Delete response file
                    del_headers2 = {}
                    del_headers2 = sign_request('DELETE', response_url, del_headers2, '')
                    del_req2 = Request(response_url, headers=del_headers2, method='DELETE')
                    urlopen(del_req2, timeout=30)
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

            except HTTPError as e:
                if e.code == 404:
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
                    # Other HTTP error
                    raise Exception(f"Error checking for response: HTTP {e.code} - {str(e)}")
            except URLError as e:
                # Network error
                raise Exception(f"Network error checking for response: {str(e)}")

        # Timeout occurred - clean up request file
        try:
            delete_url = f"{r2_endpoint}/{request_key}"
            del_headers = {}
            del_headers = sign_request('DELETE', delete_url, del_headers, '')
            del_req = Request(delete_url, headers=del_headers, method='DELETE')
            urlopen(del_req, timeout=30)
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
