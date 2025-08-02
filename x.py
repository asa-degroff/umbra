import os
import logging
import requests
import yaml
import json
import hashlib
import random
import time
from typing import Optional, Dict, Any, List, Set
from datetime import datetime
from pathlib import Path
from requests_oauthlib import OAuth1
from rich import print as rprint
from rich.panel import Panel
from rich.text import Text

import bsky_utils

class XRateLimitError(Exception):
    """Exception raised when X API rate limit is exceeded"""
    pass


# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("x_client")

# X-specific file paths
X_QUEUE_DIR = Path("x_queue")
X_CACHE_DIR = Path("x_cache")
X_PROCESSED_MENTIONS_FILE = Path("x_queue/processed_mentions.json")
X_LAST_SEEN_FILE = Path("x_queue/last_seen_id.json")
X_DOWNRANK_USERS_FILE = Path("x_downrank_users.txt")

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
    
    def _make_request(self, endpoint: str, params: Optional[Dict] = None, method: str = "GET", data: Optional[Dict] = None, max_retries: int = 3) -> Optional[Dict]:
        """Make a request to the X API with proper error handling and exponential backoff."""
        url = f"{self.base_url}{endpoint}"
        
        for attempt in range(max_retries):
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
                    return None  # Don't retry auth failures
                elif response.status_code == 403:
                    logger.error(f"X API forbidden with {self.auth_method} - check app permissions")
                    logger.error(f"Response: {response.text}")
                    return None  # Don't retry permission failures
                elif response.status_code == 429:
                    if attempt < max_retries - 1:
                        # Exponential backoff: 60s, 120s, 240s
                        backoff_time = 60 * (2 ** attempt)
                        logger.warning(f"X API rate limit exceeded (attempt {attempt + 1}/{max_retries}) - waiting {backoff_time}s before retry")
                        logger.error(f"Response: {response.text}")
                        time.sleep(backoff_time)
                        continue
                    else:
                        logger.error("X API rate limit exceeded - max retries reached")
                        logger.error(f"Response: {response.text}")
                        raise XRateLimitError("X API rate limit exceeded")
                else:
                    if attempt < max_retries - 1:
                        # Exponential backoff for other HTTP errors too
                        backoff_time = 30 * (2 ** attempt)
                        logger.warning(f"X API request failed (attempt {attempt + 1}/{max_retries}): {e} - retrying in {backoff_time}s")
                        logger.error(f"Response: {response.text}")
                        time.sleep(backoff_time)
                        continue
                    else:
                        logger.error(f"X API request failed after {max_retries} attempts: {e}")
                        logger.error(f"Response: {response.text}")
                        return None
                        
            except Exception as e:
                if attempt < max_retries - 1:
                    backoff_time = 15 * (2 ** attempt)
                    logger.warning(f"Unexpected error making X API request (attempt {attempt + 1}/{max_retries}): {e} - retrying in {backoff_time}s")
                    time.sleep(backoff_time)
                    continue
                else:
                    logger.error(f"Unexpected error making X API request after {max_retries} attempts: {e}")
                    return None
        
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
    
    def search_mentions(self, username: str, max_results: int = 10, since_id: str = None) -> Optional[List[Dict]]:
        """
        Search for mentions using the search endpoint instead of mentions endpoint.
        This might have better rate limits than the direct mentions endpoint.
        
        Args:
            username: Username to search for mentions of (without @)
            max_results: Number of results to return (10-100)
            since_id: Only return results newer than this tweet ID
            
        Returns:
            List of tweets mentioning the username
        """
        endpoint = "/tweets/search/recent"
        
        # Search for mentions of the username
        query = f"@{username}"
        
        params = {
            "query": query,
            "max_results": min(max(max_results, 10), 100),
            "tweet.fields": "id,text,author_id,created_at,in_reply_to_user_id,referenced_tweets,conversation_id",
            "user.fields": "id,name,username",
            "expansions": "author_id,in_reply_to_user_id,referenced_tweets.id"
        }
        
        if since_id:
            params["since_id"] = since_id
        
        logger.info(f"Searching for mentions of @{username}")
        response = self._make_request(endpoint, params)
        
        if response and "data" in response:
            tweets = response["data"]
            logger.info(f"Found {len(tweets)} mentions via search")
            return tweets
        else:
            if response:
                logger.info(f"No mentions found via search. Response: {response}")
            else:
                logger.warning("Search request failed")
            return []
    
    def get_thread_context(self, conversation_id: str, use_cache: bool = True, until_id: Optional[str] = None) -> Optional[List[Dict]]:
        """
        Get all tweets in a conversation thread up to a specific tweet ID.
        
        Args:
            conversation_id: The conversation ID to fetch (should be the original tweet ID)
            use_cache: Whether to use cached data if available
            until_id: Optional tweet ID to use as upper bound (excludes posts after this ID)
            
        Returns:
            List of tweets in the conversation, ordered chronologically
        """
        # Check cache first if enabled
        if use_cache:
            cached_data = get_cached_thread_context(conversation_id)
            if cached_data:
                return cached_data
        
        # First, get the original tweet directly since it might not appear in conversation search
        original_tweet = None
        try:
            endpoint = f"/tweets/{conversation_id}"
            params = {
                "tweet.fields": "id,text,author_id,created_at,in_reply_to_user_id,referenced_tweets,conversation_id",
                "user.fields": "id,name,username",
                "expansions": "author_id"
            }
            response = self._make_request(endpoint, params)
            if response and "data" in response:
                original_tweet = response["data"]
                logger.info(f"Retrieved original tweet: {original_tweet.get('id')}")
        except Exception as e:
            logger.warning(f"Could not fetch original tweet {conversation_id}: {e}")
        
        # Then search for all tweets in this conversation
        endpoint = "/tweets/search/recent"
        params = {
            "query": f"conversation_id:{conversation_id}",
            "max_results": 100,  # Get as many as possible
            "tweet.fields": "id,text,author_id,created_at,in_reply_to_user_id,referenced_tweets,conversation_id",
            "user.fields": "id,name,username", 
            "expansions": "author_id,in_reply_to_user_id,referenced_tweets.id",
            "sort_order": "recency"  # Get newest first, we'll reverse later
        }
        
        # Add until_id parameter to exclude tweets after the mention being processed
        if until_id:
            params["until_id"] = until_id
            logger.info(f"Using until_id={until_id} to exclude future tweets")
        
        logger.info(f"Fetching thread context for conversation {conversation_id}")
        response = self._make_request(endpoint, params)
        
        tweets = []
        users_data = {}
        
        # Collect tweets from search
        if response and "data" in response:
            tweets.extend(response["data"])
            # Store user data for reference
            if "includes" in response and "users" in response["includes"]:
                for user in response["includes"]["users"]:
                    users_data[user["id"]] = user
        
        # Add original tweet if we got it and it's not already in the list
        if original_tweet:
            tweet_ids = [t.get('id') for t in tweets]
            if original_tweet.get('id') not in tweet_ids:
                tweets.append(original_tweet)
                logger.info("Added original tweet to thread context")
        
        # Attempt to fill gaps by fetching referenced tweets that are missing
        # This helps with X API's incomplete conversation search results
        tweet_ids = set(t.get('id') for t in tweets)
        missing_tweet_ids = set()
        critical_missing_ids = set()
        
        # Collect referenced tweet IDs, prioritizing critical ones
        for tweet in tweets:
            referenced_tweets = tweet.get('referenced_tweets', [])
            for ref in referenced_tweets:
                ref_id = ref.get('id')
                ref_type = ref.get('type')
                if ref_id and ref_id not in tweet_ids:
                    missing_tweet_ids.add(ref_id)
                    # Prioritize direct replies and quoted tweets over retweets
                    if ref_type in ['replied_to', 'quoted']:
                        critical_missing_ids.add(ref_id)
        
        # For rate limit efficiency, only fetch critical missing tweets if we have many
        if len(missing_tweet_ids) > 10:
            logger.info(f"Many missing tweets ({len(missing_tweet_ids)}), prioritizing {len(critical_missing_ids)} critical ones")
            missing_tweet_ids = critical_missing_ids
        
        # Context sufficiency check - skip backfill if we already have enough context
        if has_sufficient_context(tweets, missing_tweet_ids):
            logger.info("Thread has sufficient context, skipping missing tweet backfill")
            missing_tweet_ids = set()
        
        # Fetch missing referenced tweets in batches (more rate-limit friendly)
        if missing_tweet_ids:
            missing_list = list(missing_tweet_ids)
            
            # First, check cache for missing tweets
            cached_tweets = get_cached_tweets(missing_list)
            for tweet_id, cached_tweet in cached_tweets.items():
                if cached_tweet.get('conversation_id') == conversation_id:
                    tweets.append(cached_tweet)
                    tweet_ids.add(tweet_id)
                    logger.info(f"Retrieved missing tweet from cache: {tweet_id}")
                    
                    # Add user data if available in cache
                    if cached_tweet.get('author_info'):
                        author_id = cached_tweet.get('author_id')
                        if author_id:
                            users_data[author_id] = cached_tweet['author_info']
            
            # Only fetch tweets that weren't found in cache
            uncached_ids = [tid for tid in missing_list if tid not in cached_tweets]
            
            if uncached_ids:
                batch_size = 100  # X API limit for bulk tweet lookup
                
                for i in range(0, len(uncached_ids), batch_size):
                    batch_ids = uncached_ids[i:i + batch_size]
                    try:
                        endpoint = "/tweets"
                        params = {
                            "ids": ",".join(batch_ids),
                            "tweet.fields": "id,text,author_id,created_at,in_reply_to_user_id,referenced_tweets,conversation_id",
                            "user.fields": "id,name,username",
                            "expansions": "author_id"
                        }
                        response = self._make_request(endpoint, params)
                        
                        if response and "data" in response:
                            fetched_tweets = []
                            batch_users_data = {}
                            
                            for missing_tweet in response["data"]:
                                # Only add if it's actually part of this conversation
                                if missing_tweet.get('conversation_id') == conversation_id:
                                    tweets.append(missing_tweet)
                                    tweet_ids.add(missing_tweet.get('id'))
                                    fetched_tweets.append(missing_tweet)
                                    logger.info(f"Retrieved missing referenced tweet: {missing_tweet.get('id')}")
                            
                            # Add user data if available
                            if "includes" in response and "users" in response["includes"]:
                                for user in response["includes"]["users"]:
                                    users_data[user["id"]] = user
                                    batch_users_data[user["id"]] = user
                            
                            # Cache the newly fetched tweets
                            if fetched_tweets:
                                save_cached_tweets(fetched_tweets, batch_users_data)
                            
                            logger.info(f"Batch fetched {len(response['data'])} missing tweets from {len(batch_ids)} requested")
                        
                        # Handle partial success - log any missing tweets that weren't found
                        if response and "errors" in response:
                            for error in response["errors"]:
                                logger.warning(f"Could not fetch tweet {error.get('resource_id')}: {error.get('title')}")
                                
                    except Exception as e:
                        logger.warning(f"Could not fetch batch of missing tweets {batch_ids[:3]}...: {e}")
            else:
                logger.info(f"All {len(missing_list)} missing tweets found in cache")
        
        if tweets:
            # Filter out tweets that occur after until_id (if specified)
            if until_id:
                original_count = len(tweets)
                # Convert until_id to int for comparison (Twitter IDs are sequential)
                until_id_int = int(until_id)
                tweets = [t for t in tweets if int(t.get('id', '0')) <= until_id_int]
                filtered_count = len(tweets)
                if original_count != filtered_count:
                    logger.info(f"Filtered out {original_count - filtered_count} tweets after until_id {until_id}")
            
            # Sort chronologically (oldest first)
            tweets.sort(key=lambda x: x.get('created_at', ''))
            logger.info(f"Retrieved {len(tweets)} tweets in thread")
            
            thread_data = {"tweets": tweets, "users": users_data}
            
            # Cache individual tweets from the thread for future backfill
            save_cached_tweets(tweets, users_data)
            
            # Cache the result
            if use_cache:
                save_cached_thread_context(conversation_id, thread_data)
            
            return thread_data
        else:
            logger.warning("No tweets found for thread context")
            return None
    
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

def thread_to_yaml_string(thread_data: Dict) -> str:
    """
    Convert X thread context to YAML string for AI comprehension.
    Similar to Bluesky's thread_to_yaml_string function.
    
    Args:
        thread_data: Dict with 'tweets' and 'users' keys from get_thread_context()
        
    Returns:
        YAML string representation of the thread
    """
    if not thread_data or "tweets" not in thread_data:
        return "conversation: []\n"
    
    tweets = thread_data["tweets"]
    users_data = thread_data.get("users", {})
    
    simplified_thread = {
        "conversation": []
    }
    
    for tweet in tweets:
        # Get user info
        author_id = tweet.get('author_id')
        author_info = {}
        if author_id and author_id in users_data:
            user = users_data[author_id]
            author_info = {
                'username': user.get('username'),
                'name': user.get('name')
            }
        
        # Build tweet object (simplified for AI consumption)
        tweet_obj = {
            'text': tweet.get('text'),
            'created_at': tweet.get('created_at'),
            'author': author_info,
            'author_id': author_id  # Include user ID for block management
        }
        
        simplified_thread["conversation"].append(tweet_obj)
    
    return yaml.dump(simplified_thread, default_flow_style=False, sort_keys=False)


def ensure_x_user_blocks_attached(thread_data: Dict, agent_id: Optional[str] = None) -> None:
    """
    Ensure all users in the thread have their X user blocks attached.
    Creates blocks with initial content including their handle if they don't exist.
    
    Args:
        thread_data: Dict with 'tweets' and 'users' keys from get_thread_context()
        agent_id: The Letta agent ID to attach blocks to (defaults to config agent_id)
    """
    if not thread_data or "users" not in thread_data:
        return
    
    try:
        from tools.blocks import attach_x_user_blocks, x_user_note_set
        from config_loader import get_letta_config
        from letta_client import Letta
        
        # Get Letta client and agent_id from config
        config = get_letta_config()
        client = Letta(token=config['api_key'], timeout=config['timeout'])
        
        # Use provided agent_id or get from config
        if agent_id is None:
            agent_id = config['agent_id']
        
        # Get agent info to create a mock agent_state for the functions
        class MockAgentState:
            def __init__(self, agent_id):
                self.id = agent_id
        
        agent_state = MockAgentState(agent_id)
        
        users_data = thread_data["users"]
        user_ids = list(users_data.keys())
        
        if not user_ids:
            return
        
        logger.info(f"Ensuring X user blocks for {len(user_ids)} users: {user_ids}")
        
        # Get current blocks to check which users already have blocks with content
        current_blocks = client.agents.blocks.list(agent_id=agent_id)
        existing_user_blocks = {}
        
        for block in current_blocks:
            if block.label.startswith("x_user_"):
                user_id = block.label.replace("x_user_", "")
                existing_user_blocks[user_id] = block
        
        # Attach all user blocks (this will create missing ones with basic content)
        attach_result = attach_x_user_blocks(user_ids, agent_state)
        logger.info(f"X user block attachment result: {attach_result}")
        
        # For newly created blocks, update with user handle information
        for user_id in user_ids:
            if user_id not in existing_user_blocks:
                user_info = users_data[user_id]
                username = user_info.get('username', 'unknown')
                name = user_info.get('name', 'Unknown')
                
                # Set initial content with handle information
                initial_content = f"# X User: {user_id}\n\n**Handle:** @{username}\n**Name:** {name}\n\nNo additional information about this user yet."
                
                try:
                    x_user_note_set(user_id, initial_content, agent_state)
                    logger.info(f"Set initial content for X user {user_id} (@{username})")
                except Exception as e:
                    logger.error(f"Failed to set initial content for X user {user_id}: {e}")
        
    except Exception as e:
        logger.error(f"Error ensuring X user blocks: {e}")


# X Caching and Queue System Functions

def load_last_seen_id() -> Optional[str]:
    """Load the last seen mention ID for incremental fetching."""
    if X_LAST_SEEN_FILE.exists():
        try:
            with open(X_LAST_SEEN_FILE, 'r') as f:
                data = json.load(f)
                return data.get('last_seen_id')
        except Exception as e:
            logger.error(f"Error loading last seen ID: {e}")
    return None

def save_last_seen_id(mention_id: str):
    """Save the last seen mention ID."""
    try:
        X_QUEUE_DIR.mkdir(exist_ok=True)
        with open(X_LAST_SEEN_FILE, 'w') as f:
            json.dump({
                'last_seen_id': mention_id,
                'updated_at': datetime.now().isoformat()
            }, f)
        logger.debug(f"Saved last seen ID: {mention_id}")
    except Exception as e:
        logger.error(f"Error saving last seen ID: {e}")

def load_processed_mentions() -> set:
    """Load the set of processed mention IDs."""
    if X_PROCESSED_MENTIONS_FILE.exists():
        try:
            with open(X_PROCESSED_MENTIONS_FILE, 'r') as f:
                data = json.load(f)
                # Keep only recent entries (last 10000)
                if len(data) > 10000:
                    data = data[-10000:]
                    save_processed_mentions(set(data))
                return set(data)
        except Exception as e:
            logger.error(f"Error loading processed mentions: {e}")
    return set()

def save_processed_mentions(processed_set: set):
    """Save the set of processed mention IDs."""
    try:
        X_QUEUE_DIR.mkdir(exist_ok=True)
        with open(X_PROCESSED_MENTIONS_FILE, 'w') as f:
            json.dump(list(processed_set), f)
    except Exception as e:
        logger.error(f"Error saving processed mentions: {e}")

def load_downrank_users() -> Set[str]:
    """Load the set of user IDs that should be downranked (responded to 10% of the time)."""
    try:
        if not X_DOWNRANK_USERS_FILE.exists():
            return set()
        
        downrank_users = set()
        with open(X_DOWNRANK_USERS_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if line and not line.startswith('#'):
                    downrank_users.add(line)
        
        logger.info(f"Loaded {len(downrank_users)} downrank users")
        return downrank_users
    except Exception as e:
        logger.error(f"Error loading downrank users: {e}")
        return set()

def should_respond_to_downranked_user(user_id: str, downrank_users: Set[str]) -> bool:
    """
    Check if we should respond to a downranked user.
    Returns True 10% of the time for downranked users, True 100% of the time for others.
    """
    if user_id not in downrank_users:
        return True
    
    # 10% chance for downranked users
    should_respond = random.random() < 0.1
    logger.info(f"Downranked user {user_id}: {'responding' if should_respond else 'skipping'} (10% chance)")
    return should_respond

def save_mention_to_queue(mention: Dict):
    """Save a mention to the queue directory for async processing."""
    try:
        mention_id = mention.get('id')
        if not mention_id:
            logger.error("Mention missing ID, cannot queue")
            return
        
        # Check if already processed
        processed_mentions = load_processed_mentions()
        if mention_id in processed_mentions:
            logger.debug(f"Mention {mention_id} already processed, skipping")
            return
        
        # Create queue directory
        X_QUEUE_DIR.mkdir(exist_ok=True)
        
        # Create filename using hash (similar to Bluesky system)
        mention_str = json.dumps(mention, sort_keys=True)
        mention_hash = hashlib.sha256(mention_str.encode()).hexdigest()[:16]
        filename = f"x_mention_{mention_hash}.json"
        
        queue_file = X_QUEUE_DIR / filename
        
        # Save mention data with enhanced debugging information
        mention_data = {
            'mention': mention,
            'queued_at': datetime.now().isoformat(),
            'type': 'x_mention',
            # Debug info for conversation tracking
            'debug_info': {
                'mention_id': mention.get('id'),
                'author_id': mention.get('author_id'),
                'conversation_id': mention.get('conversation_id'),
                'in_reply_to_user_id': mention.get('in_reply_to_user_id'),
                'referenced_tweets': mention.get('referenced_tweets', []),
                'text_preview': mention.get('text', '')[:200],
                'created_at': mention.get('created_at'),
                'public_metrics': mention.get('public_metrics', {}),
                'context_annotations': mention.get('context_annotations', [])
            }
        }
        
        with open(queue_file, 'w') as f:
            json.dump(mention_data, f, indent=2)
        
        logger.info(f"Queued X mention {mention_id} -> {filename}")
        
    except Exception as e:
        logger.error(f"Error saving mention to queue: {e}")

# X Cache Functions
def get_cached_thread_context(conversation_id: str) -> Optional[Dict]:
    """Load cached thread context if available."""
    cache_file = X_CACHE_DIR / f"thread_{conversation_id}.json"
    if cache_file.exists():
        try:
            with open(cache_file, 'r') as f:
                cached_data = json.load(f)
                # Check if cache is recent (within 1 hour)
                from datetime import datetime, timedelta
                cached_time = datetime.fromisoformat(cached_data.get('cached_at', ''))
                if datetime.now() - cached_time < timedelta(hours=1):
                    logger.info(f"Using cached thread context for {conversation_id}")
                    return cached_data.get('thread_data')
        except Exception as e:
            logger.warning(f"Error loading cached thread context: {e}")
    return None

def save_cached_thread_context(conversation_id: str, thread_data: Dict):
    """Save thread context to cache."""
    try:
        X_CACHE_DIR.mkdir(exist_ok=True)
        cache_file = X_CACHE_DIR / f"thread_{conversation_id}.json"
        
        cache_data = {
            'conversation_id': conversation_id,
            'thread_data': thread_data,
            'cached_at': datetime.now().isoformat()
        }
        
        with open(cache_file, 'w') as f:
            json.dump(cache_data, f, indent=2)
        
        logger.debug(f"Cached thread context for {conversation_id}")
    except Exception as e:
        logger.error(f"Error caching thread context: {e}")

def get_cached_tweets(tweet_ids: List[str]) -> Dict[str, Dict]:
    """
    Load cached individual tweets if available.
    Returns dict mapping tweet_id -> tweet_data for found tweets.
    """
    cached_tweets = {}
    
    for tweet_id in tweet_ids:
        cache_file = X_CACHE_DIR / f"tweet_{tweet_id}.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    cached_data = json.load(f)
                    
                # Use longer cache times for older tweets (24 hours vs 1 hour)
                from datetime import datetime, timedelta
                cached_time = datetime.fromisoformat(cached_data.get('cached_at', ''))
                tweet_created = cached_data.get('tweet_data', {}).get('created_at', '')
                
                # Parse tweet creation time to determine age
                try:
                    from dateutil.parser import parse
                    tweet_age = datetime.now() - parse(tweet_created)
                    cache_duration = timedelta(hours=24) if tweet_age > timedelta(hours=24) else timedelta(hours=1)
                except:
                    cache_duration = timedelta(hours=1)  # Default to 1 hour if parsing fails
                
                if datetime.now() - cached_time < cache_duration:
                    cached_tweets[tweet_id] = cached_data.get('tweet_data')
                    logger.debug(f"Using cached tweet {tweet_id}")
                    
            except Exception as e:
                logger.warning(f"Error loading cached tweet {tweet_id}: {e}")
    
    return cached_tweets

def save_cached_tweets(tweets_data: List[Dict], users_data: Dict[str, Dict] = None):
    """Save individual tweets to cache for future reuse."""
    try:
        X_CACHE_DIR.mkdir(exist_ok=True)
        
        for tweet in tweets_data:
            tweet_id = tweet.get('id')
            if not tweet_id:
                continue
                
            cache_file = X_CACHE_DIR / f"tweet_{tweet_id}.json"
            
            # Include user data if available
            tweet_with_user = tweet.copy()
            if users_data and tweet.get('author_id') in users_data:
                tweet_with_user['author_info'] = users_data[tweet.get('author_id')]
            
            cache_data = {
                'tweet_id': tweet_id,
                'tweet_data': tweet_with_user,
                'cached_at': datetime.now().isoformat()
            }
            
            with open(cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
            
            logger.debug(f"Cached individual tweet {tweet_id}")
            
    except Exception as e:
        logger.error(f"Error caching individual tweets: {e}")

def has_sufficient_context(tweets: List[Dict], missing_tweet_ids: Set[str]) -> bool:
    """
    Determine if we have sufficient context to skip backfilling missing tweets.
    
    Args:
        tweets: List of tweets already in the thread
        missing_tweet_ids: Set of missing tweet IDs we'd like to fetch
    
    Returns:
        True if context is sufficient, False if backfill is needed
    """
    # If no missing tweets, context is sufficient
    if not missing_tweet_ids:
        return True
    
    # If we have a substantial conversation (5+ tweets), likely sufficient
    if len(tweets) >= 5:
        logger.debug(f"Thread has {len(tweets)} tweets, considering sufficient")
        return True
    
    # If only a few missing tweets and we have some context, might be enough
    if len(missing_tweet_ids) <= 2 and len(tweets) >= 3:
        logger.debug(f"Only {len(missing_tweet_ids)} missing tweets with {len(tweets)} existing, considering sufficient")
        return True
    
    # Check if we have conversational flow (mentions between users)
    has_conversation_flow = False
    for tweet in tweets:
        text = tweet.get('text', '').lower()
        # Look for mentions, replies, or conversational indicators
        if '@' in text or 'reply' in text or len([t for t in tweets if t.get('author_id') != tweet.get('author_id')]) > 1:
            has_conversation_flow = True
            break
    
    # If we have clear conversational flow and reasonable length, sufficient
    if has_conversation_flow and len(tweets) >= 2:
        logger.debug("Thread has conversational flow, considering sufficient")
        return True
    
    # Otherwise, we need to backfill
    logger.debug(f"Context insufficient: {len(tweets)} tweets, {len(missing_tweet_ids)} missing, no clear flow")
    return False

def fetch_and_queue_mentions(username: str) -> int:
    """
    Single-pass function to fetch new mentions and queue them.
    Returns number of new mentions found.
    """
    try:
        client = create_x_client()
        
        # Load last seen ID for incremental fetching
        last_seen_id = load_last_seen_id()
        
        logger.info(f"Fetching mentions for @{username} since {last_seen_id or 'beginning'}")
        
        # Search for mentions
        mentions = client.search_mentions(
            username=username,
            since_id=last_seen_id,
            max_results=100  # Get as many as possible
        )
        
        if not mentions:
            logger.info("No new mentions found")
            return 0
        
        # Process mentions (newest first, so reverse to process oldest first)
        mentions.reverse()
        new_count = 0
        
        for mention in mentions:
            save_mention_to_queue(mention)
            new_count += 1
        
        # Update last seen ID to the most recent mention
        if mentions:
            most_recent_id = mentions[-1]['id']  # Last after reverse = most recent
            save_last_seen_id(most_recent_id)
        
        logger.info(f"Queued {new_count} new X mentions")
        return new_count
        
    except Exception as e:
        logger.error(f"Error fetching and queuing mentions: {e}")
        return 0

# Simple test function
def get_my_user_info():
    """Get the authenticated user's information to find correct user ID."""
    try:
        client = create_x_client()
        
        # Use the /2/users/me endpoint to get authenticated user info
        endpoint = "/users/me"
        params = {
            "user.fields": "id,name,username,description"
        }
        
        print("Fetching authenticated user information...")
        response = client._make_request(endpoint, params=params)
        
        if response and "data" in response:
            user_data = response["data"]
            print(f"✅ Found authenticated user:")
            print(f"   ID: {user_data.get('id')}")
            print(f"   Username: @{user_data.get('username')}")
            print(f"   Name: {user_data.get('name')}")
            print(f"   Description: {user_data.get('description', 'N/A')[:100]}...")
            print(f"\n🔧 Update your config.yaml with:")
            print(f"   user_id: \"{user_data.get('id')}\"")
            return user_data
        else:
            print("❌ Failed to get user information")
            print(f"Response: {response}")
            return None
            
    except Exception as e:
        print(f"Error getting user info: {e}")
        return None

def test_search_mentions():
    """Test the search-based mention detection."""
    try:
        client = create_x_client()
        
        # First get our username
        user_info = client._make_request("/users/me", params={"user.fields": "username"})
        if not user_info or "data" not in user_info:
            print("❌ Could not get username")
            return
        
        username = user_info["data"]["username"]
        print(f"🔍 Searching for mentions of @{username}")
        
        mentions = client.search_mentions(username, max_results=5)
        
        if mentions:
            print(f"✅ Found {len(mentions)} mentions via search:")
            for mention in mentions:
                print(f"- {mention.get('id')}: {mention.get('text', '')[:100]}...")
        else:
            print("No mentions found via search")
            
    except Exception as e:
        print(f"Search test failed: {e}")

def test_fetch_and_queue():
    """Test the single-pass fetch and queue function."""
    try:
        client = create_x_client()
        
        # Get our username
        user_info = client._make_request("/users/me", params={"user.fields": "username"})
        if not user_info or "data" not in user_info:
            print("❌ Could not get username")
            return
        
        username = user_info["data"]["username"]
        print(f"🔄 Fetching and queueing mentions for @{username}")
        
        # Show current state
        last_seen = load_last_seen_id()
        print(f"📍 Last seen ID: {last_seen or 'None (first run)'}")
        
        # Fetch and queue
        new_count = fetch_and_queue_mentions(username)
        
        if new_count > 0:
            print(f"✅ Queued {new_count} new mentions")
            print(f"📁 Check ./x_queue/ directory for queued mentions")
            
            # Show updated state
            new_last_seen = load_last_seen_id()
            print(f"📍 Updated last seen ID: {new_last_seen}")
        else:
            print("ℹ️ No new mentions to queue")
            
    except Exception as e:
        print(f"Fetch and queue test failed: {e}")

def test_thread_context():
    """Test thread context retrieval from a queued mention."""
    try:
        import json
        
        # Find a queued mention file
        queue_files = list(X_QUEUE_DIR.glob("x_mention_*.json"))
        if not queue_files:
            print("❌ No queued mentions found. Run 'python x.py queue' first.")
            return
        
        # Read the first mention
        mention_file = queue_files[0]
        with open(mention_file, 'r') as f:
            mention_data = json.load(f)
        
        mention = mention_data['mention']
        print(f"📄 Using mention: {mention.get('id')}")
        print(f"📝 Text: {mention.get('text')}")
        
        # Check if it has a conversation_id
        conversation_id = mention.get('conversation_id')
        if not conversation_id:
            print("❌ No conversation_id found in mention. May need to re-queue with updated fetch.")
            return
        
        print(f"🧵 Getting thread context for conversation: {conversation_id}")
        
        # Get thread context
        client = create_x_client()
        thread_data = client.get_thread_context(conversation_id)
        
        if thread_data:
            tweets = thread_data.get('tweets', [])
            print(f"✅ Retrieved thread with {len(tweets)} tweets")
            
            # Convert to YAML
            yaml_thread = thread_to_yaml_string(thread_data)
            
            # Save thread context for inspection
            thread_file = X_QUEUE_DIR / f"thread_context_{conversation_id}.yaml"
            with open(thread_file, 'w') as f:
                f.write(yaml_thread)
            
            print(f"💾 Saved thread context to: {thread_file}")
            print("\n📋 Thread preview:")
            print(yaml_thread)
        else:
            print("❌ Failed to retrieve thread context")
            
    except Exception as e:
        print(f"Thread context test failed: {e}")

def test_letta_integration(agent_id: str = None):
    """Test sending X thread context to Letta agent."""
    try:
        from letta_client import Letta
        import json
        import yaml
        
        # Load full config to access letta section
        try:
            with open("config.yaml", 'r') as f:
                full_config = yaml.safe_load(f)
            
            letta_config = full_config.get('letta', {})
            api_key = letta_config.get('api_key')
            config_agent_id = letta_config.get('agent_id')
            
            # Use agent_id from config if not provided as parameter
            if not agent_id:
                if config_agent_id:
                    agent_id = config_agent_id
                    print(f"ℹ️ Using agent_id from config: {agent_id}")
                else:
                    print("❌ No agent_id found in config.yaml")
                    print("Expected config structure:")
                    print("  letta:")
                    print("    agent_id: your-agent-id")
                    return
            else:
                print(f"ℹ️ Using provided agent_id: {agent_id}")
            
            if not api_key:
                # Try loading from environment as fallback
                import os
                api_key = os.getenv('LETTA_API_KEY')
                if not api_key:
                    print("❌ LETTA_API_KEY not found in config.yaml or environment")
                    print("Expected config structure:")
                    print("  letta:")
                    print("    api_key: your-letta-api-key")
                    return
                else:
                    print("ℹ️ Using LETTA_API_KEY from environment")
            else:
                print("ℹ️ Using LETTA_API_KEY from config.yaml")
                
        except Exception as e:
            print(f"❌ Error loading config: {e}")
            return
        
        letta_client = Letta(token=api_key, timeout=600)
        print(f"🤖 Connected to Letta, using agent: {agent_id}")
        
        # Find a queued mention file
        queue_files = list(X_QUEUE_DIR.glob("x_mention_*.json"))
        if not queue_files:
            print("❌ No queued mentions found. Run 'python x.py queue' first.")
            return
        
        # Read the first mention
        mention_file = queue_files[0]
        with open(mention_file, 'r') as f:
            mention_data = json.load(f)
        
        mention = mention_data['mention']
        conversation_id = mention.get('conversation_id')
        
        if not conversation_id:
            print("❌ No conversation_id found in mention.")
            return
        
        print(f"🧵 Getting thread context for conversation: {conversation_id}")
        
        # Get thread context
        x_client = create_x_client()
        thread_data = x_client.get_thread_context(conversation_id)
        
        if not thread_data:
            print("❌ Failed to retrieve thread context")
            return
        
        # Convert to YAML
        yaml_thread = thread_to_yaml_string(thread_data)
        
        # Create prompt for the agent
        prompt = f"""You are void, an AI agent operating on X (Twitter). You have received a mention and need to respond appropriately.

Here is the thread context:

{yaml_thread}

Please craft a response that continues this conversation naturally. Keep responses conversational and authentic to your void persona."""
        
        print(f"📤 Sending thread context to Letta agent...")

        # Print the prompt in a rich panel
        rprint(Panel(prompt, title="Prompt", border_style="blue"))

        # Send to Letta agent using streaming
        message_stream = letta_client.agents.messages.create_stream(
            agent_id=agent_id,
            messages=[{"role": "user", "content": prompt}],
            stream_tokens=False,
            max_steps=10
        )
        
        print("🔄 Streaming response from agent...")
        response_text = ""
        
        for chunk in message_stream:
            print(chunk)
            if hasattr(chunk, 'message_type'):
                if chunk.message_type == 'assistant_message':
                    print(f"🤖 Agent response: {chunk.content}")
                    response_text = chunk.content
                elif chunk.message_type == 'reasoning_message':
                    print(f"💭 Agent reasoning: {chunk.reasoning[:100]}...")
                elif chunk.message_type == 'tool_call_message':
                    print(f"🔧 Agent tool call: {chunk.tool_call.name}")
        
        if response_text:
            print(f"\n✅ Agent generated response:")
            print(f"📝 Response: {response_text}")
        else:
            print("❌ No response generated by agent")
            
    except Exception as e:
        print(f"Letta integration test failed: {e}")
        import traceback
        traceback.print_exc()

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

def process_x_mention(void_agent, x_client, mention_data, queue_filepath=None, testing_mode=False):
    """
    Process an X mention and generate a reply using the Letta agent.
    Similar to bsky.py process_mention but for X/Twitter.
    
    Args:
        void_agent: The Letta agent instance
        x_client: The X API client 
        mention_data: The mention data dictionary
        queue_filepath: Optional Path object to the queue file (for cleanup on halt)
        testing_mode: If True, don't actually post to X
    
    Returns:
        True: Successfully processed, remove from queue
        False: Failed but retryable, keep in queue
        None: Failed with non-retryable error, move to errors directory
        "no_reply": No reply was generated, move to no_reply directory
    """
    try:
        logger.debug(f"Starting process_x_mention with mention_data type: {type(mention_data)}")
        
        # Extract mention details
        if isinstance(mention_data, dict):
            # Handle both raw mention and queued mention formats
            if 'mention' in mention_data:
                mention = mention_data['mention']
            else:
                mention = mention_data
        else:
            mention = mention_data
            
        mention_id = mention.get('id')
        mention_text = mention.get('text', '')
        author_id = mention.get('author_id')
        conversation_id = mention.get('conversation_id')
        in_reply_to_user_id = mention.get('in_reply_to_user_id')
        referenced_tweets = mention.get('referenced_tweets', [])
        
        # Check downrank list - only respond to downranked users 10% of the time
        downrank_users = load_downrank_users()
        if not should_respond_to_downranked_user(str(author_id), downrank_users):
            logger.info(f"🔻 Skipping downranked user {author_id} - not in 10% selection")
            return "no_reply"
        
        # Enhanced conversation tracking for debug - especially important for Grok handling
        logger.info(f"🔍 CONVERSATION DEBUG - Mention ID: {mention_id}")
        logger.info(f"   Author ID: {author_id}")
        logger.info(f"   Conversation ID: {conversation_id}")
        logger.info(f"   In Reply To User ID: {in_reply_to_user_id}")
        logger.info(f"   Referenced Tweets: {len(referenced_tweets)} items")
        for i, ref in enumerate(referenced_tweets[:3]):  # Log first 3 referenced tweets
            logger.info(f"     Reference {i+1}: {ref.get('type')} -> {ref.get('id')}")
        logger.info(f"   Text preview: {mention_text[:100]}...")
        
        if not conversation_id:
            logger.warning(f"❌ No conversation_id found for mention {mention_id} - this may cause thread context issues")
            return None
        
        # Get thread context with caching enabled for efficiency
        # Use mention_id as until_id to exclude tweets that occurred after this mention
        try:
            thread_data = x_client.get_thread_context(conversation_id, use_cache=True, until_id=mention_id)
            if not thread_data:
                logger.error(f"❌ Failed to get thread context for conversation {conversation_id}")
                return False
            
            # If this mention references a specific tweet, ensure we have that tweet in context
            if referenced_tweets:
                for ref in referenced_tweets:
                    if ref.get('type') == 'replied_to':
                        ref_id = ref.get('id')
                        # Check if the referenced tweet is in our thread data
                        thread_tweet_ids = [t.get('id') for t in thread_data.get('tweets', [])]
                        if ref_id and ref_id not in thread_tweet_ids:
                            logger.warning(f"Missing referenced tweet {ref_id} in thread context, attempting to fetch")
                            try:
                                # Fetch the missing referenced tweet directly
                                endpoint = f"/tweets/{ref_id}"
                                params = {
                                    "tweet.fields": "id,text,author_id,created_at,in_reply_to_user_id,referenced_tweets,conversation_id",
                                    "user.fields": "id,name,username",
                                    "expansions": "author_id"
                                }
                                response = x_client._make_request(endpoint, params)
                                if response and "data" in response:
                                    missing_tweet = response["data"]
                                    if missing_tweet.get('conversation_id') == conversation_id:
                                        # Add to thread data
                                        if 'tweets' not in thread_data:
                                            thread_data['tweets'] = []
                                        thread_data['tweets'].append(missing_tweet)
                                        
                                        # Add user data if available
                                        if "includes" in response and "users" in response["includes"]:
                                            if 'users' not in thread_data:
                                                thread_data['users'] = {}
                                            for user in response["includes"]["users"]:
                                                thread_data['users'][user["id"]] = user
                                        
                                        logger.info(f"✅ Added missing referenced tweet {ref_id} to thread context")
                                    else:
                                        logger.warning(f"Referenced tweet {ref_id} belongs to different conversation {missing_tweet.get('conversation_id')}")
                            except Exception as e:
                                logger.error(f"Failed to fetch referenced tweet {ref_id}: {e}")
            
            # Enhanced thread context debugging
            logger.info(f"🧵 THREAD CONTEXT DEBUG - Conversation ID: {conversation_id}")
            thread_posts = thread_data.get('tweets', [])
            thread_users = thread_data.get('users', {})
            logger.info(f"   Posts in thread: {len(thread_posts)}")
            logger.info(f"   Users in thread: {len(thread_users)}")
            
            # Log thread participants for Grok detection
            for user_id, user_info in thread_users.items():
                username = user_info.get('username', 'unknown')
                name = user_info.get('name', 'Unknown')
                is_verified = user_info.get('verified', False)
                logger.info(f"   User {user_id}: @{username} ({name}) verified={is_verified}")
                
                # Special logging for Grok or AI-related users
                if 'grok' in username.lower() or 'grok' in name.lower():
                    logger.info(f"   🤖 DETECTED GROK USER: @{username} ({name})")
            
            # Log conversation structure
            for i, post in enumerate(thread_posts[:5]):  # Log first 5 posts
                post_id = post.get('id')
                post_author = post.get('author_id')
                post_text = post.get('text', '')[:50]
                is_reply = 'in_reply_to_user_id' in post
                logger.info(f"   Post {i+1}: {post_id} by {post_author} (reply={is_reply}) - {post_text}...")
                
        except Exception as e:
            logger.error(f"❌ Error getting thread context: {e}")
            return False
        
        # Convert to YAML string
        thread_context = thread_to_yaml_string(thread_data)
        logger.info(f"📄 Thread context generated, length: {len(thread_context)} characters")
        
        # Save comprehensive conversation data for debugging
        try:
            debug_dir = X_QUEUE_DIR / "debug" / f"conversation_{conversation_id}"
            debug_dir.mkdir(parents=True, exist_ok=True)
            
            # Save raw thread data (JSON)
            with open(debug_dir / f"thread_data_{mention_id}.json", 'w') as f:
                json.dump(thread_data, f, indent=2)
            
            # Save YAML thread context
            with open(debug_dir / f"thread_context_{mention_id}.yaml", 'w') as f:
                f.write(thread_context)
            
            # Save mention processing debug info
            debug_info = {
                'processed_at': datetime.now().isoformat(),
                'mention_id': mention_id,
                'conversation_id': conversation_id,
                'author_id': author_id,
                'in_reply_to_user_id': in_reply_to_user_id,
                'referenced_tweets': referenced_tweets,
                'thread_stats': {
                    'total_posts': len(thread_posts),
                    'total_users': len(thread_users),
                    'yaml_length': len(thread_context)
                },
                'users_in_conversation': {
                    user_id: {
                        'username': user_info.get('username'),
                        'name': user_info.get('name'),
                        'verified': user_info.get('verified', False),
                        'is_grok': 'grok' in user_info.get('username', '').lower() or 'grok' in user_info.get('name', '').lower()
                    }
                    for user_id, user_info in thread_users.items()
                }
            }
            
            with open(debug_dir / f"debug_info_{mention_id}.json", 'w') as f:
                json.dump(debug_info, f, indent=2)
                
            logger.info(f"💾 Saved conversation debug data to: {debug_dir}")
            
        except Exception as debug_error:
            logger.warning(f"Failed to save debug data: {debug_error}")
            # Continue processing even if debug save fails
        
        # Check for #voidstop
        if "#voidstop" in thread_context.lower() or "#voidstop" in mention_text.lower():
            logger.info("Found #voidstop, skipping this mention")
            return True
        
        # Ensure X user blocks are attached
        try:
            ensure_x_user_blocks_attached(thread_data, void_agent.id)
        except Exception as e:
            logger.warning(f"Failed to ensure X user blocks: {e}")
            # Continue without user blocks rather than failing completely
        
        # Create prompt for Letta agent
        author_info = thread_data.get('users', {}).get(author_id, {})
        author_username = author_info.get('username', 'unknown')
        author_name = author_info.get('name', author_username)
        
        prompt = f"""You received a mention on X (Twitter) from @{author_username} ({author_name}).

MOST RECENT POST (the mention you're responding to):
"{mention_text}"

FULL THREAD CONTEXT:
```yaml
{thread_context}
```

The YAML above shows the complete conversation thread. The most recent post is the one mentioned above that you should respond to, but use the full thread context to understand the conversation flow.

If you need to update user information, use the x_user_* tools.

To reply, use the add_post_to_x_thread tool:
- Each call creates one post (max 280 characters)
- For most responses, a single call is sufficient
- Only use multiple calls for threaded replies when:
  * The topic requires extended explanation that cannot fit in 280 characters
  * You're explicitly asked for a detailed/long response
  * The conversation naturally benefits from a structured multi-part answer
- Avoid unnecessary threads - be concise when possible"""

        # Log mention processing
        title = f"X MENTION FROM @{author_username}"
        print(f"\n▶ {title}")
        print(f"  {'═' * len(title)}")
        for line in mention_text.split('\n'):
            print(f"  {line}")
        
        # Send to Letta agent
        from config_loader import get_letta_config
        from letta_client import Letta
        
        config = get_letta_config()
        letta_client = Letta(token=config['api_key'], timeout=config['timeout'])
        
        logger.debug(f"Sending to LLM: @{author_username} mention | msg: \"{mention_text[:50]}...\" | context: {len(thread_context)} chars")
        
        try:
            # Use streaming to avoid timeout errors
            message_stream = letta_client.agents.messages.create_stream(
                agent_id=void_agent.id,
                messages=[{"role": "user", "content": prompt}],
                stream_tokens=False,
                max_steps=100
            )
            
            # Collect streaming response (simplified version of bsky.py logic)
            all_messages = []
            for chunk in message_stream:
                if hasattr(chunk, 'message_type'):
                    if chunk.message_type == 'reasoning_message':
                        print("\n◆ Reasoning")
                        print("  ─────────")
                        for line in chunk.reasoning.split('\n'):
                            print(f"  {line}")
                    elif chunk.message_type == 'tool_call_message':
                        tool_name = chunk.tool_call.name
                        if tool_name == 'add_post_to_x_thread':
                            try:
                                args = json.loads(chunk.tool_call.arguments)
                                text = args.get('text', '')
                                if text:
                                    print("\n✎ X Post")
                                    print("  ────────")
                                    for line in text.split('\n'):
                                        print(f"  {line}")
                            except:
                                pass
                        elif tool_name == 'halt_activity':
                            logger.info("🛑 HALT_ACTIVITY TOOL CALLED - TERMINATING X BOT")
                            if queue_filepath and queue_filepath.exists():
                                queue_filepath.unlink()
                                logger.info(f"Deleted queue file: {queue_filepath.name}")
                            logger.info("=== X BOT TERMINATED BY AGENT ===")
                            exit(0)
                    elif chunk.message_type == 'tool_return_message':
                        tool_name = chunk.name
                        status = chunk.status
                        if status == 'success' and tool_name == 'add_post_to_x_thread':
                            print("\n✓ X Post Queued")
                            print("  ──────────────")
                            print("  Post queued successfully")
                    elif chunk.message_type == 'assistant_message':
                        print("\n▶ Assistant Response")
                        print("  ──────────────────")
                        for line in chunk.content.split('\n'):
                            print(f"  {line}")
                
                all_messages.append(chunk)
                if str(chunk) == 'done':
                    break
            
            # Convert streaming response for compatibility
            message_response = type('StreamingResponse', (), {
                'messages': [msg for msg in all_messages if hasattr(msg, 'message_type')]
            })()
            
        except Exception as api_error:
            logger.error(f"Letta API error: {api_error}")
            raise

        # Extract successful add_post_to_x_thread tool calls
        reply_candidates = []
        tool_call_results = {}
        ignored_notification = False
        ack_note = None  # Track any note from annotate_ack tool
        
        # First pass: collect tool return statuses
        for message in message_response.messages:
            if hasattr(message, 'tool_call_id') and hasattr(message, 'status') and hasattr(message, 'name'):
                if message.name == 'add_post_to_x_thread':
                    tool_call_results[message.tool_call_id] = message.status
                elif message.name == 'ignore_notification':
                    if message.status == 'success':
                        ignored_notification = True
                        logger.info("🚫 X notification ignored")
        
        # Second pass: collect successful tool calls
        for message in message_response.messages:
            if hasattr(message, 'tool_call') and message.tool_call:
                # Collect annotate_ack tool calls
                if message.tool_call.name == 'annotate_ack':
                    try:
                        args = json.loads(message.tool_call.arguments)
                        note = args.get('note', '')
                        if note:
                            ack_note = note
                            logger.debug(f"Found annotate_ack with note: {note[:50]}...")
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse annotate_ack arguments: {e}")
                
                # Collect add_post_to_x_thread tool calls - only if they were successful
                elif message.tool_call.name == 'add_post_to_x_thread':
                    tool_call_id = message.tool_call.tool_call_id
                    tool_status = tool_call_results.get(tool_call_id, 'unknown')
                    
                    if tool_status == 'success':
                        try:
                            args = json.loads(message.tool_call.arguments)
                            reply_text = args.get('text', '')
                            if reply_text:
                                reply_candidates.append(reply_text)
                                logger.debug(f"Found successful add_post_to_x_thread candidate: {reply_text[:50]}...")
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse tool call arguments: {e}")
        
        # Save agent response data to debug folder
        try:
            debug_dir = X_QUEUE_DIR / "debug" / f"conversation_{conversation_id}"
            
            # Save complete agent interaction
            agent_response_data = {
                'processed_at': datetime.now().isoformat(),
                'mention_id': mention_id,
                'conversation_id': conversation_id,
                'prompt_sent': prompt,
                'reply_candidates': reply_candidates,
                'ignored_notification': ignored_notification,
                'ack_note': ack_note,
                'tool_call_results': tool_call_results,
                'all_messages': []
            }
            
            # Convert messages to serializable format
            for message in message_response.messages:
                msg_data = {
                    'message_type': getattr(message, 'message_type', 'unknown'),
                    'content': getattr(message, 'content', ''),
                    'reasoning': getattr(message, 'reasoning', ''),
                    'status': getattr(message, 'status', ''),
                    'name': getattr(message, 'name', ''),
                }
                
                if hasattr(message, 'tool_call') and message.tool_call:
                    msg_data['tool_call'] = {
                        'name': message.tool_call.name,
                        'arguments': message.tool_call.arguments,
                        'tool_call_id': getattr(message.tool_call, 'tool_call_id', '')
                    }
                
                agent_response_data['all_messages'].append(msg_data)
            
            with open(debug_dir / f"agent_response_{mention_id}.json", 'w') as f:
                json.dump(agent_response_data, f, indent=2)
                
            logger.info(f"💾 Saved agent response debug data")
            
        except Exception as debug_error:
            logger.warning(f"Failed to save agent response debug data: {debug_error}")
        
        # Handle conflicts
        if reply_candidates and ignored_notification:
            logger.error("⚠️ CONFLICT: Agent called both add_post_to_x_thread and ignore_notification!")
            return False
        
        if reply_candidates:
            # Post replies to X
            logger.debug(f"Found {len(reply_candidates)} add_post_to_x_thread calls, posting to X")
            
            if len(reply_candidates) == 1:
                content = reply_candidates[0]
                title = f"Reply to @{author_username}"
            else:
                content = "\n\n".join([f"{j}. {msg}" for j, msg in enumerate(reply_candidates, 1)])
                title = f"Reply Thread to @{author_username} ({len(reply_candidates)} messages)"
            
            print(f"\n✎ {title}")
            print(f"  {'─' * len(title)}")
            for line in content.split('\n'):
                print(f"  {line}")
            
            if testing_mode:
                logger.info("TESTING MODE: Skipping actual X post")
                return True
            else:
                # Post to X using thread approach
                success = post_x_thread_replies(x_client, mention_id, reply_candidates)
                if success:
                    logger.info(f"Successfully replied to @{author_username} on X")
                    
                    # Acknowledge the post we're replying to
                    try:
                        ack_result = acknowledge_x_post(x_client, mention_id, ack_note)
                        if ack_result:
                            if ack_note:
                                logger.info(f"Successfully acknowledged X post from @{author_username} (note: \"{ack_note[:50]}...\")")
                            else:
                                logger.info(f"Successfully acknowledged X post from @{author_username}")
                        else:
                            logger.warning(f"Failed to acknowledge X post from @{author_username}")
                    except Exception as e:
                        logger.error(f"Error acknowledging X post from @{author_username}: {e}")
                        # Don't fail the entire operation if acknowledgment fails
                    
                    return True
                else:
                    logger.error(f"Failed to send reply to @{author_username} on X")
                    return False
        else:
            if ignored_notification:
                logger.info(f"X mention from @{author_username} was explicitly ignored")
                return "ignored"
            else:
                logger.warning(f"No add_post_to_x_thread tool calls found for mention from @{author_username} - keeping in queue for next pass")
                return False  # Keep in queue for retry instead of removing
                
    except Exception as e:
        logger.error(f"Error processing X mention: {e}")
        return False

def acknowledge_x_post(x_client, post_id, note=None):
    """
    Acknowledge an X post that we replied to.
    Uses the same Bluesky client and uploads to the void data repository on atproto,
    just like Bluesky acknowledgments.
    
    Args:
        x_client: XClient instance (not used, kept for compatibility)
        post_id: The X post ID we're acknowledging
        note: Optional note to include with the acknowledgment
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Use Bluesky client to upload acks to the void data repository on atproto
        bsky_client = bsky_utils.default_login()
        
        # Create a synthetic URI and CID for the X post
        # X posts don't have atproto URIs/CIDs, so we create identifiers
        post_uri = f"x://twitter.com/post/{post_id}"
        post_cid = f"x_{post_id}_cid"  # Synthetic CID for X posts
        
        # Use the same acknowledge_post function as Bluesky
        ack_result = bsky_utils.acknowledge_post(bsky_client, post_uri, post_cid, note)
        
        if ack_result:
            logger.debug(f"Acknowledged X post {post_id} via atproto" + (f" with note: {note[:50]}..." if note else ""))
            return True
        else:
            logger.error(f"Failed to acknowledge X post {post_id}")
            return False
            
    except Exception as e:
        logger.error(f"Error acknowledging X post {post_id}: {e}")
        return False

def post_x_thread_replies(x_client, in_reply_to_tweet_id, reply_messages):
    """
    Post a series of replies to X, threading them properly.
    
    Args:
        x_client: XClient instance
        in_reply_to_tweet_id: The original tweet ID to reply to
        reply_messages: List of reply text strings
        
    Returns:
        True if successful, False otherwise
    """
    try:
        current_reply_id = in_reply_to_tweet_id
        
        for i, reply_text in enumerate(reply_messages):
            logger.info(f"Posting X reply {i+1}/{len(reply_messages)}: {reply_text[:50]}...")
            
            result = x_client.post_reply(reply_text, current_reply_id)
            
            if result and 'data' in result:
                new_tweet_id = result['data']['id']
                logger.info(f"Successfully posted X reply {i+1}, ID: {new_tweet_id}")
                # For threading, the next reply should reply to this one
                current_reply_id = new_tweet_id
            else:
                logger.error(f"Failed to post X reply {i+1}")
                return False
        
        return True
        
    except Exception as e:
        logger.error(f"Error posting X thread replies: {e}")
        return False

def load_and_process_queued_x_mentions(void_agent, x_client, testing_mode=False):
    """
    Load and process all X mentions from the queue.
    Similar to bsky.py load_and_process_queued_notifications but for X.
    """
    try:
        # Get all X mention files in queue directory
        queue_files = list(X_QUEUE_DIR.glob("x_mention_*.json"))
        
        if not queue_files:
            return
        
        # Load file metadata and sort by creation time (chronological order)
        file_metadata = []
        for filepath in queue_files:
            try:
                with open(filepath, 'r') as f:
                    queue_data = json.load(f)
                mention_data = queue_data.get('mention', queue_data)
                created_at = mention_data.get('created_at', '1970-01-01T00:00:00.000Z')  # Default to epoch if missing
                file_metadata.append((created_at, filepath))
            except Exception as e:
                logger.warning(f"Error reading queue file {filepath.name}: {e}")
                # Add with default timestamp so it still gets processed
                file_metadata.append(('1970-01-01T00:00:00.000Z', filepath))
        
        # Sort by creation time (oldest first)
        file_metadata.sort(key=lambda x: x[0])
        
        logger.info(f"Processing {len(file_metadata)} queued X mentions in chronological order")
        
        for i, (created_at, filepath) in enumerate(file_metadata, 1):
            logger.info(f"Processing X queue file {i}/{len(file_metadata)}: {filepath.name} (created: {created_at})")
            
            try:
                # Load mention data
                with open(filepath, 'r') as f:
                    queue_data = json.load(f)
                
                mention_data = queue_data.get('mention', queue_data)
                
                # Process the mention
                success = process_x_mention(void_agent, x_client, mention_data, 
                                          queue_filepath=filepath, testing_mode=testing_mode)
            
            except XRateLimitError:
                logger.info("Rate limit hit - breaking out of queue processing to restart from beginning")
                break
            
            except Exception as e:
                logger.error(f"Error processing X queue file {filepath.name}: {e}")
                continue
            
            # Handle file based on processing result
            if success:
                if testing_mode:
                    logger.info(f"TESTING MODE: Keeping X queue file: {filepath.name}")
                else:
                    filepath.unlink()
                    logger.info(f"Successfully processed and removed X file: {filepath.name}")
                    
                    # Mark as processed
                    processed_mentions = load_processed_mentions()
                    processed_mentions.add(mention_data.get('id'))
                    save_processed_mentions(processed_mentions)
            
            elif success is None:  # Move to error directory
                error_dir = X_QUEUE_DIR / "errors"
                error_dir.mkdir(exist_ok=True)
                error_path = error_dir / filepath.name
                filepath.rename(error_path)
                logger.warning(f"Moved X file {filepath.name} to errors directory")
                
            elif success == "no_reply":  # Move to no_reply directory
                no_reply_dir = X_QUEUE_DIR / "no_reply"
                no_reply_dir.mkdir(exist_ok=True)
                no_reply_path = no_reply_dir / filepath.name
                filepath.rename(no_reply_path)
                logger.info(f"Moved X file {filepath.name} to no_reply directory")
                
            elif success == "ignored":  # Delete ignored notifications
                filepath.unlink()
                logger.info(f"🚫 Deleted ignored X notification: {filepath.name}")
                
            else:
                logger.warning(f"⚠️  Failed to process X file {filepath.name}, keeping in queue for retry")
    
    except Exception as e:
        logger.error(f"Error loading queued X mentions: {e}")

def process_x_notifications(void_agent, x_client, testing_mode=False):
    """
    Fetch new X mentions, queue them, and process the queue.
    Similar to bsky.py process_notifications but for X.
    """
    try:
        # Get username for fetching mentions
        user_info = x_client._make_request("/users/me", params={"user.fields": "username"})
        if not user_info or "data" not in user_info:
            logger.error("Could not get username for X mentions")
            return
        
        username = user_info["data"]["username"]
        
        # Fetch and queue new mentions
        new_count = fetch_and_queue_mentions(username)
        
        if new_count > 0:
            logger.info(f"Found {new_count} new X mentions to process")
        
        # Process the entire queue
        load_and_process_queued_x_mentions(void_agent, x_client, testing_mode)
        
    except Exception as e:
        logger.error(f"Error processing X notifications: {e}")

def initialize_x_void():
    """Initialize the void agent for X operations."""
    logger.info("Starting void agent initialization for X...")
    
    from config_loader import get_letta_config
    from letta_client import Letta
    
    # Get config
    config = get_letta_config()
    client = Letta(token=config['api_key'], timeout=config['timeout'])
    agent_id = config['agent_id']
    
    try:
        void_agent = client.agents.retrieve(agent_id=agent_id)
        logger.info(f"Successfully loaded void agent for X: {void_agent.name} ({agent_id})")
    except Exception as e:
        logger.error(f"Failed to load void agent {agent_id}: {e}")
        raise e
    
    # Ensure correct tools are attached for X
    logger.info("Configuring tools for X platform...")
    try:
        from tool_manager import ensure_platform_tools
        ensure_platform_tools('x', void_agent.id)
    except Exception as e:
        logger.error(f"Failed to configure platform tools: {e}")
        logger.warning("Continuing with existing tool configuration")
    
    # Log agent details
    logger.info(f"X Void agent details - ID: {void_agent.id}")
    logger.info(f"Agent name: {void_agent.name}")
    
    return void_agent

def x_main_loop(testing_mode=False):
    """
    Main X bot loop that continuously monitors for mentions and processes them.
    Similar to bsky.py main() but for X/Twitter.
    """
    import time
    from time import sleep
    
    logger.info("=== STARTING X VOID BOT ===")
    
    # Initialize void agent
    void_agent = initialize_x_void()
    logger.info(f"X void agent initialized: {void_agent.id}")
    
    # Initialize X client
    x_client = create_x_client()
    logger.info("Connected to X API")
    
    # Main loop
    FETCH_DELAY_SEC = 120  # Check every 2 minutes for X mentions (reduced from 60s to conserve API calls)
    logger.info(f"Starting X mention monitoring, checking every {FETCH_DELAY_SEC} seconds")
    
    if testing_mode:
        logger.info("=== RUNNING IN X TESTING MODE ===")
        logger.info("   - No messages will be sent to X")
        logger.info("   - Queue files will not be deleted")
    
    cycle_count = 0
    start_time = time.time()
    
    while True:
        try:
            cycle_count += 1
            logger.info(f"=== X CYCLE {cycle_count} ===")
            
            # Process X notifications (fetch, queue, and process)
            process_x_notifications(void_agent, x_client, testing_mode)
            
            # Log cycle completion
            elapsed_time = time.time() - start_time
            logger.info(f"X Cycle {cycle_count} complete. Elapsed: {elapsed_time/60:.1f} minutes")
            
            sleep(FETCH_DELAY_SEC)
            
        except KeyboardInterrupt:
            elapsed_time = time.time() - start_time
            logger.info("=== X BOT STOPPED BY USER ===")
            logger.info(f"Final X session: {cycle_count} cycles in {elapsed_time/60:.1f} minutes")
            break
        except Exception as e:
            logger.error(f"=== ERROR IN X MAIN LOOP CYCLE {cycle_count} ===")
            logger.error(f"Error details: {e}")
            logger.info(f"Sleeping for {FETCH_DELAY_SEC * 2} seconds due to error...")
            sleep(FETCH_DELAY_SEC * 2)

def process_queue_only(testing_mode=False):
    """
    Process all queued X mentions without fetching new ones.
    Useful for rate limit management - queue first, then process separately.
    
    Args:
        testing_mode: If True, don't actually post to X and keep queue files
    """
    logger.info("=== PROCESSING X QUEUE ONLY ===")
    
    if testing_mode:
        logger.info("=== RUNNING IN X TESTING MODE ===")
        logger.info("   - No messages will be sent to X")
        logger.info("   - Queue files will not be deleted")
    
    try:
        # Initialize void agent
        void_agent = initialize_x_void()
        logger.info(f"X void agent initialized: {void_agent.id}")
        
        # Initialize X client
        x_client = create_x_client()
        logger.info("Connected to X API")
        
        # Process the queue without fetching new mentions
        logger.info("Processing existing X queue...")
        load_and_process_queued_x_mentions(void_agent, x_client, testing_mode)
        
        logger.info("=== X QUEUE PROCESSING COMPLETE ===")
        
    except Exception as e:
        logger.error(f"Error processing X queue: {e}")
        raise

def x_notification_loop():
    """
    DEPRECATED: Old X notification loop using search-based mention detection.
    Use x_main_loop() instead for the full bot experience.
    """
    logger.warning("x_notification_loop() is deprecated. Use x_main_loop() instead.")
    x_main_loop()

if __name__ == "__main__":
    import sys
    import argparse

    if len(sys.argv) > 1:
        if sys.argv[1] == "bot":
            # Main bot with optional --test flag
            parser = argparse.ArgumentParser(description='X Void Bot')
            parser.add_argument('command', choices=['bot'])
            parser.add_argument('--test', action='store_true', help='Run in testing mode (no actual posts)')
            args = parser.parse_args()
            x_main_loop(testing_mode=args.test)
        elif sys.argv[1] == "loop":
            x_notification_loop()
        elif sys.argv[1] == "reply":
            reply_to_cameron_post()
        elif sys.argv[1] == "me":
            get_my_user_info()
        elif sys.argv[1] == "search":
            test_search_mentions()
        elif sys.argv[1] == "queue":
            test_fetch_and_queue()
        elif sys.argv[1] == "thread":
            test_thread_context()
        elif sys.argv[1] == "process":
            # Process all queued mentions with optional --test flag
            testing_mode = "--test" in sys.argv
            process_queue_only(testing_mode=testing_mode)
        elif sys.argv[1] == "letta":
            # Use specific agent ID if provided, otherwise use from config
            agent_id = sys.argv[2] if len(sys.argv) > 2 else None
            test_letta_integration(agent_id)
        elif sys.argv[1] == "downrank":
            # View or manage downrank list
            if len(sys.argv) > 2 and sys.argv[2] == "list":
                downrank_users = load_downrank_users()
                if downrank_users:
                    print(f"📋 Downrank users ({len(downrank_users)} total):")
                    for user_id in sorted(downrank_users):
                        print(f"  - {user_id}")
                else:
                    print("📋 No downrank users configured")
            else:
                print("Usage: python x.py downrank list")
                print("  list - Show all downranked user IDs")
                print(f"  Edit {X_DOWNRANK_USERS_FILE} to modify the list")
        else:
            print("Usage: python x.py [bot|loop|reply|me|search|queue|process|thread|letta|downrank]")
            print("  bot      - Run the main X bot (use --test for testing mode)")
            print("             Example: python x.py bot --test")
            print("  queue    - Fetch and queue mentions only (no processing)")
            print("  process  - Process all queued mentions only (no fetching)")
            print("             Example: python x.py process --test")
            print("  downrank - Manage downrank users (10% response rate)")
            print("             Example: python x.py downrank list")
            print("  loop     - Run the old notification monitoring loop (deprecated)")
            print("  reply    - Reply to Cameron's specific post")
            print("  me       - Get authenticated user info and correct user ID")
            print("  search   - Test search-based mention detection")
            print("  thread   - Test thread context retrieval from queued mention")
            print("  letta    - Test sending thread context to Letta agent")
            print("             Optional: python x.py letta <agent-id>")
    else:
        test_x_client()