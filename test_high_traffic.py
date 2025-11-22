#!/usr/bin/env python3
"""Test script for high-traffic thread detection features."""

import sys
from datetime import datetime, timedelta
from notification_db import NotificationDB
from config_loader import get_config

def test_database_methods():
    """Test new database methods for high-traffic detection."""
    print("\n=== Testing Database Methods ===")

    # Clean up any existing test database
    import os
    test_db_path = "queue/test_high_traffic.db"
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
        print("   Removed old test database")

    # Create test database
    db = NotificationDB(test_db_path)

    # Test 1: Add some test notifications
    print("\n1. Adding test notifications...")
    test_root_uri = "at://test/root/123"

    for i in range(15):
        notif = {
            'uri': f'at://test/notif/{i}',
            'indexed_at': (datetime.now() - timedelta(minutes=59-i*4)).isoformat(),
            'reason': 'mention' if i % 3 == 0 else 'reply',
            'author': {'handle': f'user{i}.bsky.social', 'did': f'did:plc:user{i}'},
            'record': {
                'text': f'Test notification {i}',
                'reply': {
                    'root': {'uri': test_root_uri}
                }
            }
        }
        db.add_notification(notif)

    print(f"   ✓ Added 15 test notifications")

    # Test 2: Count notifications in time window
    print("\n2. Testing get_thread_notification_count()...")
    count_60min = db.get_thread_notification_count(test_root_uri, 60)
    count_30min = db.get_thread_notification_count(test_root_uri, 30)
    print(f"   Count (60 min window): {count_60min}")
    print(f"   Count (30 min window): {count_30min}")
    # Allow for timing variance - should get most/all of the 15 notifications
    assert count_60min >= 14, f"Expected >= 14, got {count_60min}"
    assert count_30min >= 5, f"Expected >= 5, got {count_30min}"
    print(f"   ✓ Notification counting works correctly")

    # Test 3: Calculate variable debounce
    print("\n3. Testing calculate_variable_debounce()...")
    config = get_config()
    high_traffic_config = config.get('threading', {}).get('high_traffic_detection', {})

    # Test mention debounce (should be shorter)
    mention_debounce_10 = db.calculate_variable_debounce(10, True, high_traffic_config)
    mention_debounce_20 = db.calculate_variable_debounce(20, True, high_traffic_config)

    # Test reply debounce (should be longer)
    reply_debounce_10 = db.calculate_variable_debounce(10, False, high_traffic_config)
    reply_debounce_20 = db.calculate_variable_debounce(20, False, high_traffic_config)

    print(f"   Mention debounce (10 notifs): {mention_debounce_10/60:.1f} minutes")
    print(f"   Mention debounce (20 notifs): {mention_debounce_20/60:.1f} minutes")
    print(f"   Reply debounce (10 notifs): {reply_debounce_10/3600:.1f} hours")
    print(f"   Reply debounce (20 notifs): {reply_debounce_20/3600:.1f} hours")

    # Verify scaling
    assert mention_debounce_20 > mention_debounce_10, "Mention debounce should scale up"
    assert reply_debounce_20 > reply_debounce_10, "Reply debounce should scale up"
    assert reply_debounce_10 > mention_debounce_10, "Reply debounce should be longer than mention"
    print(f"   ✓ Variable debounce scaling works correctly")

    # Test 4: Set auto-debounce
    print("\n4. Testing set_auto_debounce()...")
    test_uri = 'at://test/notif/0'
    debounce_until = (datetime.now() + timedelta(hours=2)).isoformat()
    db.set_auto_debounce(
        test_uri,
        debounce_until,
        is_high_traffic=True,
        reason='high_traffic_mention',
        thread_chain_id=test_root_uri
    )
    print(f"   ✓ Auto-debounce set successfully")

    # Test 5: Get debounced notifications for thread
    print("\n5. Testing get_thread_debounced_notifications()...")
    debounced = db.get_thread_debounced_notifications(test_root_uri)
    print(f"   Found {len(debounced)} debounced notifications")
    assert len(debounced) == 1, f"Expected 1 debounced notification, got {len(debounced)}"
    assert debounced[0]['auto_debounced'] == 1, "Should be marked as auto_debounced"
    assert debounced[0]['high_traffic_thread'] == 1, "Should be marked as high_traffic_thread"
    print(f"   ✓ Debounced notification retrieval works correctly")

    # Test 6: Clear batch debounce
    print("\n6. Testing clear_batch_debounce()...")
    cleared = db.clear_batch_debounce(test_root_uri)
    print(f"   Cleared {cleared} debounced notifications")
    assert cleared == 1, f"Expected to clear 1, cleared {cleared}"

    # Verify cleared
    debounced_after = db.get_thread_debounced_notifications(test_root_uri)
    assert len(debounced_after) == 0, f"Expected 0 debounced after clear, got {len(debounced_after)}"
    print(f"   ✓ Batch debounce clearing works correctly")

    # Cleanup
    db.close()
    import os
    os.remove("queue/test_high_traffic.db")
    print("\n   ✓ Test database cleaned up")


def test_configuration():
    """Test that configuration is loaded correctly."""
    print("\n=== Testing Configuration ===")

    config = get_config()
    threading_config = config.get('threading', {})
    high_traffic_config = threading_config.get('high_traffic_detection', {})

    print(f"\n   Enabled: {high_traffic_config.get('enabled', False)}")
    print(f"   Notification threshold: {high_traffic_config.get('notification_threshold', 10)}")
    print(f"   Time window: {high_traffic_config.get('time_window_minutes', 60)} minutes")
    print(f"   Mention debounce: {high_traffic_config.get('mention_debounce_min', 30)}-{high_traffic_config.get('mention_debounce_max', 60)} minutes")
    print(f"   Reply debounce: {high_traffic_config.get('reply_debounce_min', 120)}-{high_traffic_config.get('reply_debounce_max', 360)} minutes")

    assert high_traffic_config.get('enabled', False) == True, "High-traffic detection should be enabled"
    assert high_traffic_config.get('notification_threshold', 0) == 10, "Threshold should be 10"
    print(f"\n   ✓ Configuration loaded correctly")


def main():
    """Run all tests."""
    print("=" * 60)
    print("HIGH-TRAFFIC THREAD DETECTION TEST SUITE")
    print("=" * 60)

    try:
        test_configuration()
        test_database_methods()

        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED")
        print("=" * 60)
        return 0

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
