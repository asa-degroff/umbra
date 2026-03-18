"""Void tools for Bluesky interaction."""
# Import functions from their respective modules
from .search import search_bluesky_posts, SearchArgs
from .post import create_new_bluesky_post, PostArgs
from .feed import get_bluesky_feed, FeedArgs
from .author_feed import get_author_feed, AuthorFeedArgs
from .blocks import attach_user_blocks, detach_user_blocks, AttachUserBlocksArgs, DetachUserBlocksArgs
from .whitewind import create_whitewind_blog_post, WhitewindPostArgs
from .greengale import create_greengale_blog_post, GreenGalePostArgs

__all__ = [
    # Functions
    "search_bluesky_posts",
    "create_new_bluesky_post",
    "get_bluesky_feed",
    "get_author_feed",
    "attach_user_blocks",
    "detach_user_blocks",
    "create_whitewind_blog_post",
    "create_greengale_blog_post",
    # Pydantic models
    "SearchArgs",
    "PostArgs",
    "FeedArgs",
    "AuthorFeedArgs",
    "AttachUserBlocksArgs",
    "DetachUserBlocksArgs",
    "WhitewindPostArgs",
    "GreenGalePostArgs",
]