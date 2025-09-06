#!/usr/bin/env python3
"""Test script for X user block management functionality."""

import sys
import json
from pathlib import Path

# Add the current directory to path so we can import modules
sys.path.append(str(Path(__file__).parent))

from x import ensure_x_user_blocks_attached, get_cached_thread_context
from tools.blocks import x_user_note_view

def test_x_user_blocks():
    """Test X user block creation and attachment."""
    
    # Ensure we're using config file, not environment variable
    import os
    if 'LETTA_API_KEY' in os.environ:
        print("⚠️  Removing LETTA_API_KEY environment variable to use config file")
        del os.environ['LETTA_API_KEY']
    
    # Use the cached thread data for testing
    conversation_id = "1950690566909710618"
    thread_data = get_cached_thread_context(conversation_id)
    
    if not thread_data:
        print("❌ No cached thread data found")
        return False
    
    print(f"✅ Loaded cached thread data for conversation {conversation_id}")
    print(f"📊 Users in thread: {list(thread_data.get('users', {}).keys())}")
    
    # Get the configured void agent ID
    from config_loader import get_letta_config
    letta_config = get_letta_config()
    agent_id = letta_config['agent_id']
    print(f"🎯 Using configured void agent {agent_id} for testing")
    
    try:
        # Test user block attachment
        print(f"\n🔗 Testing X user block attachment for agent {agent_id}")
        ensure_x_user_blocks_attached(thread_data, agent_id)
        print("✅ X user block attachment completed")
        
        # Test viewing created blocks
        print("\n👀 Testing X user block viewing:")
        for user_id in thread_data.get('users', {}):
            try:
                # Create mock agent state for testing
                class MockAgentState:
                    def __init__(self, agent_id):
                        self.id = agent_id
                
                agent_state = MockAgentState(agent_id)
                content = x_user_note_view(user_id, agent_state)
                print(f"📋 Block content for user {user_id}:")
                print(content)
                print("-" * 50)
            except Exception as e:
                print(f"❌ Error viewing block for user {user_id}: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing X user blocks: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing X User Block Management")
    print("=" * 40)
    
    success = test_x_user_blocks()
    
    if success:
        print("\n✅ All X user block tests completed successfully!")
    else:
        print("\n❌ X user block tests failed!")
        sys.exit(1)