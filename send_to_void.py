#!/usr/bin/env python
"""Quick CLI tool to send a message to void and stream the response."""

import os
import sys
from dotenv import load_dotenv
from letta_client import Letta
import argparse

def send_message_to_void(message: str):
    """Send a message to void and stream the response."""
    load_dotenv()
    
    # Create Letta client
    client = Letta(
        base_url=os.getenv("LETTA_BASE_URL", "http://localhost:8283"),
        token=os.getenv("LETTA_API_KEY")
    )
    
    # Get the void agent
    agents = client.agents.list()
    void_agent = next((a for a in agents if a.name == "void"), None)
    
    if not void_agent:
        print("Error: void agent not found")
        return
    
    print(f"Sending message to void: {message}\n")
    print("=" * 50)
    
    # Send message and stream response
    try:
        # Use the streaming interface
        message_stream = client.agents.messages.create_stream(
            agent_id=void_agent.id,
            messages=[{"role": "user", "content": message}],
            stream_tokens=False,  # Step streaming only
            max_steps=100
        )
        
        # Process the streaming response
        for chunk in message_stream:
            if hasattr(chunk, 'message_type'):
                if chunk.message_type == 'reasoning_message':
                    # Show reasoning
                    print("\n◆ Reasoning")
                    print("  ─────────")
                    for line in chunk.reasoning.split('\n'):
                        print(f"  {line}")
                elif chunk.message_type == 'tool_call_message':
                    # Show tool calls
                    tool_name = chunk.tool_call.name if hasattr(chunk, 'tool_call') else 'unknown'
                    print(f"\n▸ Calling tool: {tool_name}")
                elif chunk.message_type == 'tool_return_message':
                    # Show tool results
                    if hasattr(chunk, 'tool_return') and chunk.tool_return:
                        result_str = str(chunk.tool_return)
                        print(f"  Tool result: {result_str[:200]}...")
                elif chunk.message_type == 'assistant_message':
                    # Show assistant response
                    print("\n▶ Assistant Response")
                    print("  ──────────────────")
                    for line in chunk.content.split('\n'):
                        print(f"  {line}")
                elif chunk.message_type not in ['usage_statistics', 'stop_reason']:
                    # Filter out verbose message types
                    print(f"  {chunk.message_type}: {str(chunk)[:150]}...")
            
            if str(chunk) == 'done':
                break
        
        print("\n" + "=" * 50)
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

def main():
    parser = argparse.ArgumentParser(description="Send a quick message to void")
    parser.add_argument("message", nargs="+", help="Message to send to void")
    args = parser.parse_args()
    
    # Join the message parts
    message = " ".join(args.message)
    
    send_message_to_void(message)

if __name__ == "__main__":
    main()