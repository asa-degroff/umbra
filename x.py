import os
import logging
import requests
import yaml
import json
import hashlib
from typing import Optional, Dict, Any, List
from datetime import datetime
from pathlib import Path
from requests_oauthlib import OAuth1
from rich import print as rprint
from rich.panel import Panel
from rich.text import Text


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
    
    def get_thread_context(self, conversation_id: str, use_cache: bool = True) -> Optional[List[Dict]]:
        """
        Get all tweets in a conversation thread.
        
        Args:
            conversation_id: The conversation ID to fetch (should be the original tweet ID)
            use_cache: Whether to use cached data if available
            
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
        
        if tweets:
            # Sort chronologically (oldest first)
            tweets.sort(key=lambda x: x.get('created_at', ''))
            logger.info(f"Retrieved {len(tweets)} tweets in thread")
            
            thread_data = {"tweets": tweets, "users": users_data}
            
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
            'author': author_info
        }
        
        simplified_thread["conversation"].append(tweet_obj)
    
    return yaml.dump(simplified_thread, default_flow_style=False, sort_keys=False)

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
        
        # Save mention data
        with open(queue_file, 'w') as f:
            json.dump({
                'mention': mention,
                'queued_at': datetime.now().isoformat(),
                'type': 'x_mention'
            }, f, indent=2)
        
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

def test_letta_integration(agent_id: str = "agent-94a01ee3-3023-46e9-baf8-6172f09bee99"):
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

        # List out all available agents
        try:
            agents_response = letta_client.projects.list()
            print("📋 Available projects:")
            if isinstance(agents_response, tuple) and len(agents_response) > 1:
                projects = agents_response[1]  # The actual projects list
                for project in projects:
                    print(f"  - {project.name} (ID: {project.id})")
            else:
                print("  No projects found or unexpected response format")
        except Exception as e:
            print(f"❌ Error listing projects: {e}")
        
        print(f"\n🤖 Using agent ID: {agent_id}")

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

def x_notification_loop():
    """
    X notification loop using search-based mention detection.
    Uses search endpoint instead of mentions endpoint for better rate limits.
    """
    import time
    import json
    from pathlib import Path
    
    logger.info("=== STARTING X SEARCH-BASED NOTIFICATION LOOP ===")
    
    try:
        client = create_x_client()
        logger.info("X client initialized")
        
        # Get our username for searching
        user_info = client._make_request("/users/me", params={"user.fields": "username"})
        if not user_info or "data" not in user_info:
            logger.error("Could not get username for search")
            return
        
        username = user_info["data"]["username"]
        logger.info(f"Monitoring mentions of @{username}")
        
    except Exception as e:
        logger.error(f"Failed to initialize X client: {e}")
        return
    
    # Track the last seen mention ID to avoid duplicates
    last_mention_id = None
    cycle_count = 0
    
    # Search-based loop with better rate limits
    while True:
        try:
            cycle_count += 1
            logger.info(f"=== X SEARCH CYCLE {cycle_count} ===")
            
            # Search for mentions using search endpoint
            mentions = client.search_mentions(
                username=username,
                since_id=last_mention_id,
                max_results=10
            )
            
            if mentions:
                logger.info(f"Found {len(mentions)} new mentions via search")
                
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
                logger.info("No new mentions found via search")
            
            # Sleep between cycles - search might have better rate limits
            logger.info("Sleeping for 60 seconds...")
            time.sleep(60)
            
        except KeyboardInterrupt:
            logger.info("=== X SEARCH LOOP STOPPED BY USER ===")
            logger.info(f"Processed {cycle_count} cycles") 
            break
        except Exception as e:
            logger.error(f"Error in X search cycle {cycle_count}: {e}")
            logger.info("Sleeping for 120 seconds due to error...")
            time.sleep(120)

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "loop":
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
        elif sys.argv[1] == "letta":
            # Use specific agent ID if provided, otherwise use default
            agent_id = sys.argv[2] if len(sys.argv) > 2 else "agent-94a01ee3-3023-46e9-baf8-6172f09bee99"
            test_letta_integration(agent_id)
        else:
            print("Usage: python x.py [loop|reply|me|search|queue|thread|letta]")
            print("  loop   - Run the notification monitoring loop")
            print("  reply  - Reply to Cameron's specific post")
            print("  me     - Get authenticated user info and correct user ID")
            print("  search - Test search-based mention detection")
            print("  queue  - Test fetch and queue mentions (single pass)")
            print("  thread - Test thread context retrieval from queued mention")
            print("  letta  - Test sending thread context to Letta agent")
            print("           Optional: python x.py letta <agent-id>")
    else:
        test_x_client()