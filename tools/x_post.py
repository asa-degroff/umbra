"""Tool for creating standalone posts on X (Twitter)."""
import os
import json
import logging
import requests
from typing import Optional
from pydantic import BaseModel, Field, validator
from requests_oauthlib import OAuth1

logger = logging.getLogger(__name__)


class PostToXArgs(BaseModel):
    text: str = Field(
        ..., 
        description="Text content for the X post (max 280 characters)"
    )
    
    @validator('text')
    def validate_text_length(cls, v):
        if len(v) > 280:
            raise ValueError(f"Text exceeds 280 character limit (current: {len(v)} characters)")
        return v


def post_to_x(text: str) -> str:
    """
    Create a new standalone post on X (Twitter). This is not a reply to another post.
    
    Use this tool when you want to share a thought, observation, or announcement 
    that isn't in response to anyone else's post.
    
    Args:
        text: Text content for the post (max 280 characters)
    
    Returns:
        Success message with post ID if successful
    
    Raises:
        Exception: If text exceeds character limit or posting fails
    """
    # Validate input
    if len(text) > 280:
        raise Exception(f"Text exceeds 280 character limit (current: {len(text)} characters)")
    
    try:
        # Get credentials from environment variables
        consumer_key = os.environ.get("X_CONSUMER_KEY")
        consumer_secret = os.environ.get("X_CONSUMER_SECRET")
        access_token = os.environ.get("X_ACCESS_TOKEN")
        access_token_secret = os.environ.get("X_ACCESS_TOKEN_SECRET")
        
        if not all([consumer_key, consumer_secret, access_token, access_token_secret]):
            raise Exception("Missing X API credentials in environment variables")
        
        # Create OAuth 1.0a authentication
        auth = OAuth1(
            consumer_key,
            client_secret=consumer_secret,
            resource_owner_key=access_token,
            resource_owner_secret=access_token_secret
        )
        
        # Prepare the request
        url = "https://api.x.com/2/tweets"
        headers = {"Content-Type": "application/json"}
        payload = {"text": text}
        
        # Make the POST request
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            auth=auth
        )
        
        # Check response
        if response.status_code == 201:
            result = response.json()
            if 'data' in result:
                tweet_id = result['data'].get('id', 'unknown')
                tweet_url = f"https://x.com/i/status/{tweet_id}"
                logger.info(f"Successfully posted to X: {tweet_url}")
                return f"Successfully posted to X. Tweet ID: {tweet_id}. URL: {tweet_url}"
            else:
                raise Exception(f"Unexpected response format: {result}")
        else:
            error_msg = f"X API error: {response.status_code} - {response.text}"
            logger.error(error_msg)
            raise Exception(error_msg)
            
    except requests.exceptions.RequestException as e:
        error_msg = f"Network error posting to X: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)
    except Exception as e:
        if "Missing X API credentials" in str(e) or "X API error" in str(e):
            raise
        error_msg = f"Unexpected error posting to X: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)