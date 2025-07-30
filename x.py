import os
import logging
import requests
import yaml
import json
from typing import Optional, Dict, Any, List
from datetime import datetime
from requests_oauthlib import OAuth1

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("x_client")

class XClient:
    """X (Twitter) API client for fetching mentions and managing interactions."""
    
    def __init__(self, api_key: str, user_id: str, access_token: str = None, 
                 consumer_key: str = None, consumer_secret: str = None, 
                 access_token_secret: str = None):
        self.api_key = api_key
        self.access_token = access_token
        self.user_id = user_id
        self.base_url = "https://api.x.com/2"
        
        # Check if we have OAuth 1.0a credentials
        if (consumer_key and consumer_secret and access_token and access_token_secret):
            # Use OAuth 1.0a for User Context
            self.oauth = OAuth1(
                consumer_key,
                client_secret=consumer_secret,
                resource_owner_key=access_token,
                resource_owner_secret=access_token_secret
            )
            self.headers = {"Content-Type": "application/json"}
            self.auth_method = "oauth1a"
            logger.info("Using OAuth 1.0a User Context authentication for X API")
        elif access_token:
            # Use OAuth 2.0 Bearer token for User Context
            self.oauth = None
            self.headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            self.auth_method = "oauth2_user"
            logger.info("Using OAuth 2.0 User Context access token for X API")
        else:
            # Use Application-Only Bearer token
            self.oauth = None
            self.headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            self.auth_method = "bearer"
            logger.info("Using Application-Only Bearer token for X API")
    
    def _make_request(self, endpoint: str, params: Optional[Dict] = None, method: str = "GET", data: Optional[Dict] = None) -> Optional[Dict]:
        """Make a request to the X API with proper error handling."""
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method.upper() == "GET":
                if self.oauth:
                    response = requests.get(url, headers=self.headers, params=params, auth=self.oauth)
                else:
                    response = requests.get(url, headers=self.headers, params=params)
            elif method.upper() == "POST":
                if self.oauth:
                    response = requests.post(url, headers=self.headers, json=data, auth=self.oauth)
                else:
                    response = requests.post(url, headers=self.headers, json=data)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
                
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if response.status_code == 401:
                logger.error(f"X API authentication failed with {self.auth_method} - check your credentials")
                logger.error(f"Response: {response.text}")
            elif response.status_code == 403:
                logger.error(f"X API forbidden with {self.auth_method} - check app permissions")
                logger.error(f"Response: {response.text}")
            elif response.status_code == 429:
                logger.error("X API rate limit exceeded")
                logger.error(f"Response: {response.text}")
            else:
                logger.error(f"X API request failed: {e}")
                logger.error(f"Response: {response.text}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error making X API request: {e}")
            return None
    
    def get_mentions(self, since_id: Optional[str] = None, max_results: int = 10) -> Optional[List[Dict]]:
        """
        Fetch mentions for the configured user.
        
        Args:
            since_id: Minimum Post ID to include (for getting newer mentions)
            max_results: Number of results to return (5-100)
        
        Returns:
            List of mention objects or None if request failed
        """
        endpoint = f"/users/{self.user_id}/mentions"
        params = {
            "max_results": min(max(max_results, 5), 100),  # Ensure within API limits
            "tweet.fields": "id,text,author_id,created_at,in_reply_to_user_id,referenced_tweets",
            "user.fields": "id,name,username",
            "expansions": "author_id,in_reply_to_user_id,referenced_tweets.id"
        }
        
        if since_id:
            params["since_id"] = since_id
        
        logger.info(f"Fetching mentions for user {self.user_id}")
        response = self._make_request(endpoint, params)
        
        if response:
            logger.debug(f"X API response: {response}")
        
        if response and "data" in response:
            mentions = response["data"]
            logger.info(f"Retrieved {len(mentions)} mentions")
            return mentions
        else:
            if response:
                logger.info(f"No mentions in response. Full response: {response}")
            else:
                logger.warning("Request failed - no response received")
            return []
    
    def get_user_info(self, user_id: str) -> Optional[Dict]:
        """Get information about a specific user."""
        endpoint = f"/users/{user_id}"
        params = {
            "user.fields": "id,name,username,description,public_metrics"
        }
        
        response = self._make_request(endpoint, params)
        return response.get("data") if response else None
    
    def post_reply(self, reply_text: str, in_reply_to_tweet_id: str) -> Optional[Dict]:
        """
        Post a reply to a specific tweet.
        
        Args:
            reply_text: The text content of the reply
            in_reply_to_tweet_id: The ID of the tweet to reply to
        
        Returns:
            Response data if successful, None if failed
        """
        endpoint = "/tweets"
        
        payload = {
            "text": reply_text,
            "reply": {
                "in_reply_to_tweet_id": in_reply_to_tweet_id
            }
        }
        
        logger.info(f"Attempting to post reply with {self.auth_method} authentication")
        result = self._make_request(endpoint, method="POST", data=payload)
        
        if result:
            logger.info(f"Successfully posted reply to tweet {in_reply_to_tweet_id}")
            return result
        else:
            logger.error("Failed to post reply")
            return None

def load_x_config(config_path: str = "config.yaml") -> Dict[str, str]:
    """Load X configuration from config file."""
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        x_config = config.get('x', {})
        if not x_config.get('api_key') or not x_config.get('user_id'):
            raise ValueError("X API key and user_id must be configured in config.yaml")
        
        return x_config
    except Exception as e:
        logger.error(f"Failed to load X configuration: {e}")
        raise

def create_x_client(config_path: str = "config.yaml") -> XClient:
    """Create and return an X client with configuration loaded from file."""
    config = load_x_config(config_path)
    return XClient(
        api_key=config['api_key'],
        user_id=config['user_id'],
        access_token=config.get('access_token'),
        consumer_key=config.get('consumer_key'),
        consumer_secret=config.get('consumer_secret'),
        access_token_secret=config.get('access_token_secret')
    )

def mention_to_yaml_string(mention: Dict, users_data: Optional[Dict] = None) -> str:
    """
    Convert a mention object to a YAML string for better AI comprehension.
    Similar to thread_to_yaml_string in bsky_utils.py
    """
    # Extract relevant fields
    simplified_mention = {
        'id': mention.get('id'),
        'text': mention.get('text'),
        'author_id': mention.get('author_id'),
        'created_at': mention.get('created_at'),
        'in_reply_to_user_id': mention.get('in_reply_to_user_id')
    }
    
    # Add user information if available
    if users_data and mention.get('author_id') in users_data:
        user = users_data[mention.get('author_id')]
        simplified_mention['author'] = {
            'username': user.get('username'),
            'name': user.get('name')
        }
    
    return yaml.dump(simplified_mention, default_flow_style=False, sort_keys=False)

# Simple test function
def test_x_client():
    """Test the X client by fetching mentions."""
    try:
        client = create_x_client()
        mentions = client.get_mentions(max_results=5)
        
        if mentions:
            print(f"Successfully retrieved {len(mentions)} mentions:")
            for mention in mentions:
                print(f"- {mention.get('id')}: {mention.get('text')[:50]}...")
        else:
            print("No mentions retrieved")
            
    except Exception as e:
        print(f"Test failed: {e}")

def reply_to_cameron_post():
    """
    Reply to Cameron's specific X post.
    
    NOTE: This requires OAuth User Context authentication, not Bearer token.
    Current Bearer token is Application-Only which can't post.
    """
    try:
        client = create_x_client()
        
        # Cameron's post ID from the URL: https://x.com/cameron_pfiffer/status/1950690566909710618
        cameron_post_id = "1950690566909710618"
        
        # Simple reply message
        reply_text = "Hello from void! 🤖 Testing X integration."
        
        print(f"Attempting to reply to post {cameron_post_id}")
        print(f"Reply text: {reply_text}")
        print("\nNOTE: This will fail with current Bearer token (Application-Only)")
        print("Posting requires OAuth User Context authentication")
        
        result = client.post_reply(reply_text, cameron_post_id)
        
        if result:
            print(f"✅ Successfully posted reply!")
            print(f"Reply ID: {result.get('data', {}).get('id', 'Unknown')}")
        else:
            print("❌ Failed to post reply (expected with current auth)")
            
    except Exception as e:
        print(f"Reply failed: {e}")

def x_notification_loop():
    """
    Simple X notification loop that fetches mentions and logs them.
    Very basic version to understand the platform needs.
    """
    import time
    import json
    from pathlib import Path
    
    logger.info("=== STARTING X NOTIFICATION LOOP ===")
    
    try:
        client = create_x_client()
        logger.info("X client initialized")
    except Exception as e:
        logger.error(f"Failed to initialize X client: {e}")
        return
    
    # Track the last seen mention ID to avoid duplicates
    last_mention_id = None
    cycle_count = 0
    
    # Simple loop similar to bsky.py but much more basic
    while True:
        try:
            cycle_count += 1
            logger.info(f"=== X CYCLE {cycle_count} ===")
            
            # Fetch mentions (newer than last seen)
            mentions = client.get_mentions(
                since_id=last_mention_id,
                max_results=10
            )
            
            if mentions:
                logger.info(f"Found {len(mentions)} new mentions")
                
                # Update last seen ID
                if mentions:
                    last_mention_id = mentions[0]['id']  # Most recent first
                
                # Process each mention (just log for now)
                for mention in mentions:
                    logger.info(f"Mention from {mention.get('author_id')}: {mention.get('text', '')[:100]}...")
                    
                    # Convert to YAML for inspection
                    yaml_mention = mention_to_yaml_string(mention)
                    
                    # Save to file for inspection (temporary)
                    debug_dir = Path("x_debug")
                    debug_dir.mkdir(exist_ok=True)
                    
                    mention_file = debug_dir / f"mention_{mention['id']}.yaml"
                    with open(mention_file, 'w') as f:
                        f.write(yaml_mention)
                    
                    logger.info(f"Saved mention debug info to {mention_file}")
            else:
                logger.info("No new mentions found")
            
            # Sleep between cycles (shorter than bsky for now)
            logger.info("Sleeping for 60 seconds...")
            time.sleep(60)
            
        except KeyboardInterrupt:
            logger.info("=== X LOOP STOPPED BY USER ===")
            logger.info(f"Processed {cycle_count} cycles")
            break
        except Exception as e:
            logger.error(f"Error in X cycle {cycle_count}: {e}")
            logger.info("Sleeping for 120 seconds due to error...")
            time.sleep(120)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        if sys.argv[1] == "loop":
            x_notification_loop()
        elif sys.argv[1] == "reply":
            reply_to_cameron_post()
        else:
            print("Usage: python x.py [loop|reply]")
            print("  loop  - Run the notification monitoring loop")
            print("  reply - Reply to Cameron's specific post")
    else:
        test_x_client()