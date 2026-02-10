"""Ask Umbriel tool - sends questions to the server's technical advisor AI via R2 queue."""
from typing import Optional
from pydantic import BaseModel, Field, validator


class AskUmbrielArgs(BaseModel):
    question: str = Field(..., description="The question or request to send to Umbriel")
    context: Optional[str] = Field(default="", description="Optional context such as a thread URI, topic, or background info")
    priority: Optional[str] = Field(default="normal", description="Priority level: 'normal' or 'high'")
    max_wait_seconds: Optional[int] = Field(default=120, description="Maximum seconds to wait for response (default: 120, max: 600)")

    @validator('max_wait_seconds')
    def validate_wait_time(cls, v):
        if v is None:
            return 120
        if v < 10 or v > 600:
            raise ValueError("max_wait_seconds must be between 10 and 600")
        return v


def ask_umbriel(question: str, context: str = "", priority: str = "normal", max_wait_seconds: int = 120) -> str:
    """
    Send a question to Umbriel, the server's technical advisor AI running on OpenClaw.

    Umbriel is a separate AI agent with access to local tools, the web, and system
    administration capabilities. Use this when you need:
    - Technical advice or research
    - Information about the server, infrastructure, or local files
    - Help with tasks that require local system access
    - A second opinion or analysis from another AI perspective

    The tool uses a request/response queue system via Cloudflare R2 storage:
    1. Request is uploaded to R2 bucket with unique ID
    2. Local poller detects request and sends it to Umbriel via OpenClaw CLI
    3. Response is uploaded back to R2
    4. Tool downloads response and returns result

    Args:
        question: The question or request to send to Umbriel
        context: Optional context (thread URI, topic, background info)
        priority: Priority level - 'normal' or 'high'
        max_wait_seconds: Maximum time to wait for response (10-600 seconds, default: 120)

    Returns:
        Response from Umbriel with the answer

    Example:
        ask_umbriel(
            question="What's the current disk usage on the server?",
            context="Checking before a large backup",
            priority="normal"
        )
    """
    import os
    import json
    import time
    import uuid
    from datetime import datetime, timezone

    try:
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
            region_name='auto'
        )

        # Generate unique request ID
        request_id = str(uuid.uuid4())

        # Build the message for Umbriel
        umbriel_message = question
        if context:
            umbriel_message = f"{question}\n\nContext: {context}"

        # Create request payload
        request_data = {
            "request_id": request_id,
            "question": question,
            "context": context,
            "priority": priority,
            "message": umbriel_message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "max_wait_seconds": max_wait_seconds,
            "submitted_by": "umbra"
        }

        # Upload request to R2
        request_key = f"umbriel-requests/{request_id}.json"

        try:
            s3_client.put_object(
                Bucket=r2_bucket_name,
                Key=request_key,
                Body=json.dumps(request_data, indent=2),
                ContentType='application/json',
                Metadata={
                    'priority': priority,
                    'request-id': request_id
                }
            )
        except ClientError as e:
            raise Exception(f"Failed to upload request to R2: {str(e)}")

        # Poll for response with exponential backoff
        response_key = f"umbriel-responses/{request_id}.json"
        start_time = time.time()
        poll_interval = 2
        max_poll_interval = 10

        while time.time() - start_time < max_wait_seconds:
            try:
                response_obj = s3_client.get_object(
                    Bucket=r2_bucket_name,
                    Key=response_key
                )
                response_data = json.loads(response_obj['Body'].read())

                # Clean up request and response files
                try:
                    s3_client.delete_object(Bucket=r2_bucket_name, Key=request_key)
                    s3_client.delete_object(Bucket=r2_bucket_name, Key=response_key)
                except Exception:
                    pass

                # Check for errors in response
                if response_data.get("error"):
                    raise Exception(f"Umbriel request failed: {response_data['error']}")

                # Extract response
                umbriel_response = response_data.get("response", "")
                execution_time = response_data.get("execution_time_seconds", "unknown")

                if not umbriel_response:
                    raise Exception("Received empty response from Umbriel")

                return (
                    f"[Response from Umbriel (your technical advisor)]\n\n"
                    f"{umbriel_response}\n\n"
                    f"(Execution time: {execution_time}s | Request ID: {request_id})"
                )

            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', '')
                if error_code in ['NoSuchKey', '404']:
                    elapsed = time.time() - start_time
                    remaining = max_wait_seconds - elapsed
                    if remaining <= 0:
                        break
                    time.sleep(min(poll_interval, remaining))
                    poll_interval = min(poll_interval * 1.5, max_poll_interval)
                    continue
                else:
                    raise Exception(f"Error checking for response: {str(e)}")

        # Timeout - clean up
        try:
            s3_client.delete_object(Bucket=r2_bucket_name, Key=request_key)
        except Exception:
            pass

        raise Exception(
            f"Timeout waiting for Umbriel response after {max_wait_seconds}s. "
            f"The umbriel poller may be offline. Request ID: {request_id}"
        )

    except Exception as e:
        error_msg = str(e)
        if "credentials not configured" in error_msg.lower():
            raise Exception(error_msg)
        else:
            raise Exception(f"Error communicating with Umbriel: {error_msg}")
