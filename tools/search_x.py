"""Search tool for X (Twitter) posts."""
from pydantic import BaseModel, Field
from typing import Optional


class SearchXArgs(BaseModel):
    username: str = Field(..., description="X username to get recent posts from (without @)")
    max_results: int = Field(default=10, description="Maximum number of posts to return (max 100)")
    exclude_replies: bool = Field(default=False, description="Whether to exclude replies")
    exclude_retweets: bool = Field(default=False, description="Whether to exclude retweets")


def search_x_posts(username: str, max_results: int = 10, exclude_replies: bool = False, exclude_retweets: bool = False) -> str:
    """
    Get recent posts from a specific X (Twitter) user.
    
    Args:
        username: X username to get posts from (without @)
        max_results: Maximum number of posts to return (max 100)
        exclude_replies: Whether to exclude replies
        exclude_retweets: Whether to exclude retweets
        
    Returns:
        YAML-formatted posts from the user
    """
    import os
    import yaml
    import requests
    from datetime import datetime
    
    try:
        # Validate inputs
        max_results = min(max_results, 100)
        
        # Get credentials from environment
        # These need to be set in the cloud environment
        consumer_key = os.getenv("X_CONSUMER_KEY")
        consumer_secret = os.getenv("X_CONSUMER_SECRET")
        access_token = os.getenv("X_ACCESS_TOKEN")
        access_token_secret = os.getenv("X_ACCESS_TOKEN_SECRET")
        
        # Also check for bearer token as fallback
        bearer_token = os.getenv("X_BEARER_TOKEN")
        
        if not any([bearer_token, (consumer_key and consumer_secret and access_token and access_token_secret)]):
            raise Exception("X API credentials not found in environment variables")
        
        # First, we need to get the user ID from the username
        base_url = "https://api.x.com/2"
        
        # Set up authentication headers
        if bearer_token:
            headers = {
                "Authorization": f"Bearer {bearer_token}",
                "Content-Type": "application/json"
            }
        else:
            # For OAuth 1.0a, we'd need requests_oauthlib
            # Since this is a cloud function, we'll require bearer token for simplicity
            raise Exception("Bearer token required for X API authentication in cloud environment")
        
        # Get user ID from username
        user_lookup_url = f"{base_url}/users/by/username/{username}"
        user_params = {
            "user.fields": "id,name,username,description"
        }
        
        try:
            user_response = requests.get(user_lookup_url, headers=headers, params=user_params, timeout=10)
            user_response.raise_for_status()
            user_data = user_response.json()
            
            if "data" not in user_data:
                raise Exception(f"User @{username} not found")
                
            user_id = user_data["data"]["id"]
            user_info = user_data["data"]
            
        except requests.exceptions.HTTPError as e:
            if user_response.status_code == 404:
                raise Exception(f"User @{username} not found")
            else:
                raise Exception(f"Failed to look up user @{username}: {str(e)}")
        
        # Get user's recent tweets
        tweets_url = f"{base_url}/users/{user_id}/tweets"
        
        # Build query parameters
        tweets_params = {
            "max_results": max_results,
            "tweet.fields": "id,text,author_id,created_at,referenced_tweets,conversation_id",
            "exclude": []
        }
        
        # Add exclusions
        if exclude_replies:
            tweets_params["exclude"].append("replies")
        if exclude_retweets:
            tweets_params["exclude"].append("retweets")
            
        # Join exclusions or remove if empty
        if tweets_params["exclude"]:
            tweets_params["exclude"] = ",".join(tweets_params["exclude"])
        else:
            del tweets_params["exclude"]
        
        try:
            tweets_response = requests.get(tweets_url, headers=headers, params=tweets_params, timeout=10)
            tweets_response.raise_for_status()
            tweets_data = tweets_response.json()
        except Exception as e:
            raise Exception(f"Failed to fetch posts from @{username}: {str(e)}")
        
        # Format results
        results = []
        for tweet in tweets_data.get("data", []):
            # Check if it's a retweet
            is_retweet = False
            referenced_tweets = tweet.get("referenced_tweets", [])
            for ref in referenced_tweets:
                if ref.get("type") == "retweeted":
                    is_retweet = True
                    break
            
            tweet_data = {
                "author": {
                    "handle": user_info.get("username", ""),
                    "display_name": user_info.get("name", ""),
                },
                "text": tweet.get("text", ""),
                "created_at": tweet.get("created_at", ""),
                "url": f"https://x.com/{username}/status/{tweet.get('id', '')}",
                "id": tweet.get("id", ""),
                "is_retweet": is_retweet
            }
            
            # Add conversation info if it's a reply
            if tweet.get("conversation_id") and tweet.get("conversation_id") != tweet.get("id"):
                tweet_data["conversation_id"] = tweet.get("conversation_id")
            
            results.append(tweet_data)
        
        return yaml.dump({
            "x_user_posts": {
                "user": {
                    "username": user_info.get("username"),
                    "name": user_info.get("name"),
                    "description": user_info.get("description", ""),
                },
                "post_count": len(results),
                "posts": results
            }
        }, default_flow_style=False, sort_keys=False)
        
    except Exception as e:
        raise Exception(f"Error searching X posts: {str(e)}")