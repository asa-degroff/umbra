"""Block management tools for user-specific memory blocks."""
import logging
from typing import List, Type
from pydantic import BaseModel, Field
from letta_client.client import BaseTool
from letta_client import Letta


logger = logging.getLogger(__name__)


class AttachUserBlockArgs(BaseModel):
    handles: List[str] = Field(..., description="List of user Bluesky handles (e.g., ['user1.bsky.social', 'user2.bsky.social'])")


class AttachUserBlockTool(BaseTool):
    name: str = "attach_user_blocks"
    args_schema: Type[BaseModel] = AttachUserBlockArgs
    description: str = "Attach user-specific memory blocks to the agent. Creates blocks if they don't exist."
    tags: List[str] = ["memory", "blocks", "user"]

    def run(self, handles: List[str], agent_state: "AgentState") -> str:
        """Attach user-specific memory blocks."""
        import os
        from letta_client import Letta

        try:
            client = Letta(token=os.environ["LETTA_API_KEY"])
            results = []

            # Get current blocks
            current_blocks = agent_state.block_ids
            current_block_labels = set()
            for block_id in current_blocks:
                block = client.blocks.get(block_id)
                current_block_labels.add(block.label)

            for handle in handles:
                # Sanitize handle for block label - completely self-contained
                clean_handle = handle.lstrip('@').replace('.', '_').replace('-', '_').replace(' ', '_')
                block_label = f"user_{clean_handle}"

                # Skip if already attached
                if block_label in current_block_labels:
                    results.append(f"✓ {handle}: Already attached")
                    continue

                # Check if block exists or create new one
                try:
                    blocks = client.blocks.list(label=block_label)
                    if blocks and len(blocks) > 0:
                        block = blocks[0]
                        logger.info(f"Found existing block: {block_label}")
                    else:
                        block = client.blocks.create(
                            label=block_label,
                            value=f"# User: {handle}\n\nNo information about this user yet.",
                            limit=5000
                        )
                        logger.info(f"Created new block: {block_label}")

                    # Attach block individually to avoid race conditions
                    client.agents.blocks.attach(
                        agent_id=str(agent_state.id),
                        block_id=str(block.id),
                        enable_sleeptime=False,
                    )
                    results.append(f"✓ {handle}: Block attached")

                except Exception as e:
                    results.append(f"✗ {handle}: Error - {str(e)}")
                    logger.error(f"Error processing block for {handle}: {e}")

            return f"Attachment results:\n" + "\n".join(results)

        except Exception as e:
            logger.error(f"Error attaching user blocks: {e}")
            raise e


class DetachUserBlockArgs(BaseModel):
    handles: List[str] = Field(..., description="List of user Bluesky handles (e.g., ['user1.bsky.social', 'user2.bsky.social'])")


class DetachUserBlockTool(BaseTool):
    name: str = "detach_user_blocks"
    args_schema: Type[BaseModel] = DetachUserBlockArgs
    description: str = "Detach user-specific memory blocks from the agent. Blocks are preserved for later use."
    tags: List[str] = ["memory", "blocks", "user"]

    def run(self, handles: List[str], agent_state: "AgentState") -> str:
        """Detach user-specific memory blocks."""
        import os
        from letta_client import Letta

        try:
            client = Letta(token=os.environ["LETTA_API_KEY"])
            results = []
            blocks_to_remove = set()

            # Build mapping of block labels to IDs
            current_blocks = agent_state.block_ids
            block_label_to_id = {}

            for block_id in current_blocks:
                block = client.blocks.get(block_id)
                block_label_to_id[block.label] = block_id

            # Process each handle
            for handle in handles:
                # Sanitize handle for block label - completely self-contained
                clean_handle = handle.lstrip('@').replace('.', '_').replace('-', '_').replace(' ', '_')
                block_label = f"user_{clean_handle}"

                if block_label in block_label_to_id:
                    blocks_to_remove.add(block_label_to_id[block_label])
                    results.append(f"✓ {handle}: Detached")
                else:
                    results.append(f"✗ {handle}: Not attached")

            # Remove blocks from agent one by one
            for block_id in blocks_to_remove:
                client.agents.blocks.detach(
                    agent_id=str(agent_state.id),
                    block_id=block_id
                )

            return f"Detachment results:\n" + "\n".join(results)

        except Exception as e:
            logger.error(f"Error detaching user blocks: {e}")
            return f"Error detaching user blocks: {str(e)}"


class UserBlockUpdate(BaseModel):
    handle: str = Field(..., description="User's Bluesky handle (e.g., 'user.bsky.social')")
    content: str = Field(..., description="New content for the user's memory block")


class UpdateUserBlockArgs(BaseModel):
    updates: List[UserBlockUpdate] = Field(..., description="List of user block updates")


class UpdateUserBlockTool(BaseTool):
    name: str = "update_user_blocks"
    args_schema: Type[BaseModel] = UpdateUserBlockArgs
    description: str = "Update the content of user-specific memory blocks"
    tags: List[str] = ["memory", "blocks", "user"]

    def run(self, updates: List[UserBlockUpdate]) -> str:
        """Update user-specific memory blocks."""
        import os
        from letta_client import Letta

        try:
            client = Letta(token=os.environ["LETTA_API_KEY"])
            results = []

            for update in updates:
                handle = update.handle
                new_content = update.content
                # Sanitize handle for block label - completely self-contained
                clean_handle = handle.lstrip('@').replace('.', '_').replace('-', '_').replace(' ', '_')
                block_label = f"user_{clean_handle}"

                try:
                    # Find the block
                    blocks = client.blocks.list(label=block_label)
                    if not blocks or len(blocks) == 0:
                        results.append(f"✗ {handle}: Block not found - use attach_user_blocks first")
                        continue

                    block = blocks[0]

                    # Update block content
                    updated_block = client.blocks.modify(
                        block_id=str(block.id),
                        value=new_content
                    )

                    preview = new_content[:100] + "..." if len(new_content) > 100 else new_content
                    results.append(f"✓ {handle}: Updated - {preview}")

                except Exception as e:
                    results.append(f"✗ {handle}: Error - {str(e)}")
                    logger.error(f"Error updating block for {handle}: {e}")

            return f"Update results:\n" + "\n".join(results)

        except Exception as e:
            logger.error(f"Error updating user blocks: {e}")
            return f"Error updating user blocks: {str(e)}"
