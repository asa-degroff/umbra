#!/usr/bin/env python3
"""
Show the current capabilities of both agents.
"""

import os
from letta_client import Letta

def show_agent_capabilities():
    """Display the capabilities of both agents."""
    
    client = Letta(token=os.environ["LETTA_API_KEY"])
    
    print("🤖 LETTA AGENT CAPABILITIES")
    print("=" * 50)
    
    # Profile Researcher Agent
    researchers = client.agents.list(name="profile-researcher")
    if researchers:
        researcher = researchers[0]
        print(f"\n📊 PROFILE RESEARCHER AGENT")
        print(f"   ID: {researcher.id}")
        print(f"   Name: {researcher.name}")
        
        researcher_tools = client.agents.tools.list(agent_id=researcher.id)
        print(f"   Tools ({len(researcher_tools)}):")
        for tool in researcher_tools:
            print(f"     - {tool.name}")
        
        researcher_blocks = client.agents.blocks.list(agent_id=researcher.id)
        print(f"   Memory Blocks ({len(researcher_blocks)}):")
        for block in researcher_blocks:
            print(f"     - {block.label}")
    
    # Void Agent
    voids = client.agents.list(name="void")
    if voids:
        void = voids[0]
        print(f"\n🌌 VOID AGENT")
        print(f"   ID: {void.id}")
        print(f"   Name: {void.name}")
        
        void_tools = client.agents.tools.list(agent_id=void.id)
        print(f"   Tools ({len(void_tools)}):")
        for tool in void_tools:
            print(f"     - {tool.name}")
        
        void_blocks = client.agents.blocks.list(agent_id=void.id)
        print(f"   Memory Blocks ({len(void_blocks)}):")
        for block in void_blocks:
            print(f"     - {block.label}")
    
    print(f"\n🔄 WORKFLOW")
    print(f"   1. Profile Researcher: attach_user_block → research_bluesky_profile → update_user_block → detach_user_block")
    print(f"   2. Void Agent: Can attach/detach same user blocks for personalized interactions")
    print(f"   3. Shared Memory: Both agents can access the same user-specific blocks")
    
    print(f"\n💡 USAGE EXAMPLES")
    print(f"   Profile Researcher: 'Research @3fz.org and store findings'")
    print(f"   Umbra Agent: 'Attach user block for 3fz.org before responding'")

if __name__ == "__main__":
    show_agent_capabilities()