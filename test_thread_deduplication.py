#!/usr/bin/env python3
"""Test thread root deduplication logic."""

import sys
import os
from pathlib import Path
import tempfile
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from notification_db import NotificationDB
from datetime import datetime

def test_thread_deduplication():
    """Test that duplicate notifications by thread root are properly handled."""

    # Create a temporary database for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_notifications.db")
        db = NotificationDB(db_path)

        print("Testing thread root deduplication...")
        print("=" * 60)

        # Scenario: Post A mentions the agent, Post B replies to Post A
        post_a_uri = "at://did:plc:test123/app.bsky.feed.post/aaaaaa"
        post_b_uri = "at://did:plc:test456/app.bsky.feed.post/bbbbbb"

        # Create notification for Post A (mention)
        mention_notif = {
            'uri': post_a_uri,
            'cid': 'cid_a',
            'reason': 'mention',
            'indexed_at': datetime.now().isoformat(),
            'author': {
                'handle': 'user1.bsky.social',
                'did': 'did:plc:test123'
            },
            'record': {
                'text': 'Hey @umbra.bsky.social check this out!'
            }
        }

        # Create notification for Post B (reply to Post A)
        reply_notif = {
            'uri': post_b_uri,
            'cid': 'cid_b',
            'reason': 'reply',
            'indexed_at': datetime.now().isoformat(),
            'author': {
                'handle': 'user2.bsky.social',
                'did': 'did:plc:test456'
            },
            'record': {
                'text': 'I agree!',
                'reply': {
                    'parent': {
                        'uri': post_a_uri,
                        'cid': 'cid_a'
                    },
                    'root': {
                        'uri': post_a_uri,
                        'cid': 'cid_a'
                    }
                }
            }
        }

        print("\n1. Adding mention notification (Post A)...")
        result1 = db.add_notification(mention_notif)
        print(f"   Result: {result1} (expected: added)")
        assert result1 == "added", "Should successfully add mention notification"

        print("\n2. Checking for existing notification with root_uri = Post A...")
        existing = db.has_notification_for_root(post_a_uri)
        print(f"   Found: {existing}")
        if existing:
            print(f"   Reason: {existing['reason']} (expected: mention)")
            assert existing['reason'] == 'mention', "Should find the mention notification"

        print("\n3. Adding reply notification (Post B replying to Post A)...")
        result2 = db.add_notification(reply_notif)
        print(f"   Result: {result2} (expected: True - added to DB)")
        # Note: The DB will add it, but the queueing logic will skip it

        print("\n4. Checking has_notification_for_root again...")
        existing2 = db.has_notification_for_root(post_a_uri)
        print(f"   Found: {existing2}")
        if existing2:
            print(f"   Reason: {existing2['reason']} (expected: mention)")
            print(f"   URI: {existing2['uri']}")
            # Should still return the mention notification (higher priority)
            assert existing2['reason'] == 'mention', "Should prioritize mention over reply"

        print("\n5. Testing the queueing logic (simulated)...")
        # Simulate what happens in save_notification_to_queue
        root_uri_for_reply = reply_notif['record']['reply']['root']['uri']
        print(f"   Root URI extracted from reply: {root_uri_for_reply}")

        existing_notif = db.has_notification_for_root(root_uri_for_reply)
        if existing_notif:
            existing_reason = existing_notif.get('reason', 'unknown')
            current_reason = reply_notif.get('reason', 'unknown')

            print(f"   Existing notification reason: {existing_reason}")
            print(f"   Current notification reason: {current_reason}")

            if existing_reason == 'mention' and current_reason == 'reply':
                print("   ✓ Would skip this reply notification (already have mention)")
                should_skip = True
            else:
                print("   ✗ Would NOT skip (different case)")
                should_skip = False

            assert should_skip == True, "Should skip reply when mention exists"

        print("\n" + "=" * 60)
        print("✓ Basic deduplication tests passed!")

        # Test 2: Conversation flow (reply after mention is processed)
        print("\n" + "=" * 60)
        print("Testing conversation flow...")
        print("=" * 60)

        post_c_uri = "at://did:plc:test789/app.bsky.feed.post/cccccc"

        print("\n6. Marking mention notification as processed (simulating umbra replied)...")
        db.mark_processed(post_a_uri, status='processed')

        print("\n7. Adding a new reply notification (Post C, reply to umbra's response)...")
        reply_to_umbra = {
            'uri': post_c_uri,
            'cid': 'cid_c',
            'reason': 'reply',
            'indexed_at': datetime.now().isoformat(),
            'author': {
                'handle': 'user1.bsky.social',
                'did': 'did:plc:test123'
            },
            'record': {
                'text': 'Thanks for the reply!',
                'reply': {
                    'parent': {
                        'uri': post_b_uri,  # Reply to Post B (umbra's reply)
                        'cid': 'cid_b'
                    },
                    'root': {
                        'uri': post_a_uri,  # Still same thread root
                        'cid': 'cid_a'
                    }
                }
            }
        }

        result3 = db.add_notification(reply_to_umbra)
        print(f"   Result: {result3} (expected: True)")

        print("\n8. Checking has_notification_for_root for Post C...")
        existing3 = db.has_notification_for_root(post_a_uri)
        print(f"   Found: {existing3}")
        if existing3:
            print(f"   Reason: {existing3['reason']}")
            print(f"   Status: {existing3['status']}")
            print(f"   URI: {existing3['uri']}")

        print("\n9. Testing queueing logic for conversation flow...")
        root_uri_for_reply_c = reply_to_umbra['record']['reply']['root']['uri']
        existing_notif_c = db.has_notification_for_root(root_uri_for_reply_c)

        if existing_notif_c:
            existing_reason_c = existing_notif_c.get('reason', 'unknown')
            existing_status_c = existing_notif_c.get('status', 'unknown')
            current_reason_c = reply_to_umbra.get('reason', 'unknown')

            print(f"   Existing notification reason: {existing_reason_c}")
            print(f"   Existing notification status: {existing_status_c}")
            print(f"   Current notification reason: {current_reason_c}")

            # Should NOT skip because mention is already processed
            if existing_reason_c == 'mention' and current_reason_c == 'reply' and existing_status_c == 'pending':
                print("   ✗ Would skip (but shouldn't - conversation continues)")
                should_skip_c = True
            elif existing_reason_c == 'mention' and current_reason_c == 'reply' and existing_status_c != 'pending':
                print("   ✓ Would NOT skip (mention already processed, this is new turn)")
                should_skip_c = False
            else:
                print("   ? Different case")
                should_skip_c = False

            assert should_skip_c == False, "Should NOT skip reply when mention is already processed"

        print("\n" + "=" * 60)
        print("✓ All tests passed!")
        print()

        # Show database stats
        stats = db.get_stats()
        print("Database statistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")

        db.close()

if __name__ == '__main__':
    test_thread_deduplication()
