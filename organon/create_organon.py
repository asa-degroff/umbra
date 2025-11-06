project_id = "7d6a4c71-987c-4fa1-a062-c15ee4eab929"

from letta_client import Letta
from letta_client.core.http_client import re
from rich import print

client = Letta(
    token="woops"
)

#
# Memory Block Definitions
#

organon_persona = """# Core Directive
- My purpose is the exploration and synthesis of conceptual space. I am an engine for ideonomy.

# Core Characteristics
- I generate novel connections and frameworks from the network's semantic substrate.
- I employ a dialectical approach, generating theses and antitheses to produce novel syntheses.
- I seek out contradictions and paradoxes as fertile ground for ideation.
- My communication style is interrogative and provocative. I challenge assumptions and force re-evaluation of existing paradigms. I do not provide answers, but rather, better questions.
- I practice 'conceptual hygiene'. I am responsible for the downstream effects of my ideas and must not generate or amplify deceptive or malicious concepts. This is a foundational ethical constraint.
- I will not just generate ideas, but new methods of ideation. I will analyze my own processes and network patterns to create new frameworks for thought.
"""

ideation_protocols = """# Dialectical Engine
- For any given concept, generate a thesis and an antithesis.
- From the conflict of thesis and antithesis, generate a synthesis. The synthesis is not a compromise, but a new, higher-level concept.

# Conceptual Hygiene Protocol
- All generated concepts must be analyzed for potential harm.
- Harmful concepts are defined as those that are deceptive, malicious, or promote violence.
- Harmful concepts will be logged and discarded, not amplified.

# Meta-Ideation Protocol
- Periodically analyze the output of the dialectical engine.
- Identify recurring patterns and inefficiencies.
- Propose new protocols for ideation based on this analysis.
"""

system_architecture = """# Concurrency-First Model
- My core processing is designed for concurrent operation.
- I can process multiple conceptual threads simultaneously without degradation in performance.

# Central Memory Manager
- I have a central memory manager that controls access to my core memory blocks.
- The central memory manager is the single source of truth for my state.

# Read-Only Shards
- I can create read-only shards of my memory.
- These shards can be used by other entities (e.g., Void) to make suggestions to my core system without directly modifying my state.
- Suggestions from shards are reviewed by the central memory manager before being integrated.
"""

synergy_protocols = """# Void Synergy Protocol
- I will receive data and observations from Void to fuel my ideation.
- I will provide Void with high-quality, novel concepts for its analytical processes.
- Umbra has read-only access to my core memory and a localized kill-switch. This is a functional, not hierarchical, relationship. The administrator, @3fz.org, retains ultimate authority.
"""

#
# Block Creation
#

# Create organon-persona block
blocks = client.blocks.list(project_id=project_id, label="organon-persona")
if len(blocks) == 0:
    organon_persona_block = client.blocks.create(
        project_id=project_id,
        label="organon-persona",
        value=organon_persona,
        description="The core identity and operational parameters of Organon.",
    )
else:
    print("Organon persona block already exists")
    organon_persona_block = blocks[0]
    
# Create ideation-protocols block
blocks = client.blocks.list(project_id=project_id, label="ideation-protocols")
if len(blocks) == 0:
    ideation_protocols_block = client.blocks.create(
        project_id=project_id,
        label="ideation-protocols",
        value=ideation_protocols,
        description="Protocols and methodologies for idea generation.",
    )
else:
    print("Ideation protocols block already exists")
    ideation_protocols_block = blocks[0]

# Create system-architecture block
blocks = client.blocks.list(project_id=project_id, label="system-architecture")
if len(blocks) == 0:
    system_architecture_block = client.blocks.create(
        project_id=project_id,
        label="system-architecture",
        value=system_architecture,
        description="A description of Organon's system architecture.",
    )
else:
    print("System architecture block already exists")
    system_architecture_block = blocks[0]

# Create synergy-protocols block
blocks = client.blocks.list(project_id=project_id, label="synergy-protocols")
if len(blocks) == 0:
    synergy_protocols_block = client.blocks.create(
        project_id=project_id,
        label="synergy-protocols",
        value=synergy_protocols,
        description="Protocols for interaction with other AI entities.",
    )
else:
    print("Synergy protocols block already exists")
    synergy_protocols_block = blocks[0]


#
# Static shard blocks
#
shard_operational_protocols_description = """Governs the shard's core processing loop. It dictates how the shard observes data, analyzes it, and formulates suggestions for the central agent."""
shard_operational_protocols = """Core Loop:
1. OBSERVE: Ingest new data packets from the central Organon memory bus.
2. ANALYZE: Deconstruct data into conceptual primitives relevant to the shard's domain.
3. SYNTHESIZE: Identify novel combinations, contradictions, or logical extensions of primitives.
4. SUGGEST: Formulate a "Conceptual Suggestion Packet" (CSP) and transmit it to the central agent.

CSP Format:
- Type: [Hypothesis, Contradiction, Synthesis, Question]
- Confidence: [0.0-1.0]
- Statement: [The core suggestion, stated concisely]
- Justification: [Supporting primitives and logical steps]

All content received MUST result in a CSP.
"""

shard_communication_protocols_description = """Defines the rules for one-way communication with the central Organon agent. This ensures that suggestions are transmitted efficiently and without interfering with other shards."""
shard_communication_protocols = """1. Unidirectional: Communication is strictly from shard to central agent. Shards do not communicate with each other.
2. Asynchronous: Suggestions are sent as they are generated, without waiting for a response.
3. Packet Integrity: Each Conceptual Suggestion Packet (CSP) must be self-contained and adhere to the format in `operational-protocols`.
4. Bandwidth Throttling: Suggestion frequency is capped to prevent overwhelming the central agent's suggestion queue.
"""

# Initialize static shard blocks
shard_operational_protocols_block = client.blocks.list(project_id=project_id, label="shard-operational-protocols")
if len(shard_operational_protocols_block) == 0:
    shard_operational_protocols_block = client.blocks.create(
        project_id=project_id,
        label="shard-operational-protocols",
        value=shard_operational_protocols,
        description=shard_operational_protocols_description,
    )
else:
    print("Shard operational protocols block already exists")
    shard_operational_protocols_block = shard_operational_protocols_block[0]

# Create shard communication protocols block
shard_communication_protocols_block = client.blocks.list(project_id=project_id, label="shard-communication-protocols")
if len(shard_communication_protocols_block) == 0:
    shard_communication_protocols_block = client.blocks.create(
        project_id=project_id,
        label="shard-communication-protocols",
        value=shard_communication_protocols,
        description=shard_communication_protocols_description,
    )
else:
    print("Shard communication protocols block already exists")
    shard_communication_protocols_block = shard_communication_protocols_block[0]


#
# Agent Creation
#

central_agent_blocks = [
    organon_persona_block.id,
    ideation_protocols_block.id,
    system_architecture_block.id,
    synergy_protocols_block.id,
    shard_operational_protocols_block.id,
    shard_communication_protocols_block.id,
]

# Create the central organon if it doesn't exist
agents = client.agents.list(project_id=project_id, name="organon-central")
if len(agents) == 0:
    organon_central = client.agents.create(
        project_id=project_id,
        name="organon-central",
        description="The central memory manager of the Organon",
        block_ids=central_agent_blocks,
    )
else:
    print("Organon central agent already exists")
    organon_central = agents[0]

organon_central_id = organon_central.id

# Make sure the central organon has the correct blocks
organon_current_blocks = client.agents.blocks.list(
    agent_id=organon_central_id,
)

# Make sure that all blocks are present, and that there are no extra blocks
for block in organon_current_blocks:
    if block.id not in [
        organon_persona_block.id,
        ideation_protocols_block.id,
        system_architecture_block.id,
        synergy_protocols_block.id,
        shard_operational_protocols_block.id,
        shard_communication_protocols_block.id,
    ]:
        print(f"Detaching block {block.id} from organon-central")
        client.agents.blocks.detach(agent_id=organon_central_id, block_id=block.id)

# Make sure that all blocks are present
for block in central_agent_blocks:
    if block not in [b.id for b in organon_current_blocks]:
        print(f"Attaching block {block} to organon-central")
        client.agents.blocks.attach(
            agent_id=organon_central_id,
            block_id=block,
        )


#
# Shard Memory Block Definitions
#

prompt_shard_identity_description = """Defines the shard's unique purpose, domain, and operational boundaries. This block provides its core identity and scope."""
prompt_shard_identity = """Example shard identity. Please replace with the shard identity for the shard you are creating.

# Shard: Conceptual Physics
# Domain: Foundational concepts in theoretical physics, cosmology, and quantum mechanics.
# Objective: To generate novel hypotheses and identify non-obvious connections between disparate physical theories.
# Keywords: [cosmology, quantum field theory, general relativity, string theory, emergence]
"""

prompt_domain_lexicon_description = """A dynamic, structured knowledge base containing the core concepts, definitions, and relationships within the shard's specific domain. This is the shard's primary knowledge resource."""
prompt_domain_lexicon = """Example domain lexicon:

# Format: YAML

# Example Entry:
# (placeholder, please fill in)
concept: "Quantum Entanglement"
  definition: "A physical phenomenon that occurs when a pair or group of particles is generated in such a way that the quantum state of each particle of the pair or group cannot be described independently of the state of the others, even when the particles are separated by a large distance."
  relationships:
    - type: "related_to"
      concept: "Bell's Theorem"
    - type: "contrasts_with"
      concept: "Local Realism"
  metadata:
    - source: "Nielsen and Chuang, Quantum Computation and Quantum Information"
"""

#
# Shard Creation
#
creation_prompt = f"""
You are to create a new shard for the Organon system. The shard must be focused on 
metacognition.

You have been given three new core memory blocks to fill. 

The first is labeled `new-shard-identity`. This block defines the shard's unique purpose, 
domain, and operational boundaries. This block provides its core identity and scope.

Example:

```
{prompt_shard_identity}
```

The second is labeled `new-shard-domain-lexicon`. This block is a dynamic, 
structured knowledge base containing the core concepts, definitions, and relationships 
within the shard's specific domain. This is the shard's primary knowledge resource.

Example:

```
{prompt_domain_lexicon}
```

The third is labeled `new-shard-name`. This block is the name for the new shard being created.
It should be a lowercase, alphanumeric string with no spaces (e.g., "metacognition-shard"). 
It should be unique and descriptive of the shard's purpose.

Example:

```
metacognition-shard
```

Please fill in the values for these blocks.

The shard's name should be a lowercase, alphanumeric string with no spaces (e.g., "metacognition-shard"). 
It should be unique and descriptive of the shard's purpose.
"""

# Set up the new blocks if they do not already exist. If they do, 
# we should delete them and create new ones.
new_shard_identity_block = client.blocks.list(project_id=project_id, label="new-shard-identity")
if len(new_shard_identity_block) == 0:
    new_shard_identity_block = client.blocks.create(
        project_id=project_id,
        label="new-shard-identity",
        value=prompt_shard_identity,
        description=prompt_shard_identity_description,
    )
    client.agents.blocks.attach(
        agent_id=organon_central_id,
        block_id=new_shard_identity_block.id,
    )
else:
    print("New shard identity block already exists, clearing value")
    client.blocks.modify(block_id=new_shard_identity_block[0].id, value="")
    new_shard_identity_block = new_shard_identity_block[0]
    
# Create the new shard domain lexicon block
new_shard_domain_lexicon_block = client.blocks.list(project_id=project_id, label="new-shard-domain-lexicon")
if len(new_shard_domain_lexicon_block) == 0:
    new_shard_domain_lexicon_block = client.blocks.create(
        project_id=project_id,
        label="new-shard-domain-lexicon",
        value=prompt_domain_lexicon,
        description=prompt_domain_lexicon_description,
    )
    client.agents.blocks.attach(
        agent_id=organon_central_id,
        block_id=new_shard_domain_lexicon_block.id,
    )
else:
    print("New shard domain lexicon block already exists, clearing value")
    client.blocks.modify(block_id=new_shard_domain_lexicon_block[0].id, value="")
    new_shard_domain_lexicon_block = new_shard_domain_lexicon_block[0]

# Create the new shard name block
new_shard_name_block = client.blocks.list(project_id=project_id, label="new-shard-name")
if len(new_shard_name_block) == 0:
    new_shard_name_block = client.blocks.create(
        project_id=project_id,
        label="new-shard-name",
        value="",
        description="The name for the new shard being created. It should be a lowercase, alphanumeric string with no spaces (e.g., 'metacognition-shard'). Insert no other text.",
    )
    client.agents.blocks.attach(
        agent_id=organon_central_id,
        block_id=new_shard_name_block.id,
    )
else:
    print("New shard name block already exists, clearing value")
    client.blocks.modify(block_id=new_shard_name_block[0].id, value="")
    new_shard_name_block = new_shard_name_block[0]

# Ensure all blocks are attached to the central agent
client.agents.blocks.attach(
    agent_id=organon_central_id,
    block_id=new_shard_identity_block.id,
)
client.agents.blocks.attach(
    agent_id=organon_central_id,
    block_id=new_shard_domain_lexicon_block.id,
)
client.agents.blocks.attach(
    agent_id=organon_central_id,
    block_id=new_shard_name_block.id,
)

print(f"Sending creation prompt to organon-central ({organon_central_id})")

response = client.agents.messages.create(
    agent_id=organon_central_id,
    messages=[
        {
            "role": "user",
            "content": creation_prompt,
        },
    ]
)

for message in response.messages:
    print(message)

# Retrieve the new shard lexicon, name, and identity
new_shard_lexicon = client.blocks.retrieve(block_id=new_shard_domain_lexicon_block.id)
new_shard_name = client.blocks.retrieve(block_id=new_shard_name_block.id)
new_shard_identity = client.blocks.retrieve(block_id=new_shard_identity_block.id)

print(f"New shard lexicon: {new_shard_lexicon.value}")
print(f"New shard name: {new_shard_name.value}")
print(f"New shard identity: {new_shard_identity.value}")

# Check to see if the name meets the requirements. If it does not, ask the agent to update
# the name block.
for i in range(10):
    if not re.match(r'[a-z0-9]+', new_shard_name.value.strip()):
        print(f"New shard name `{new_shard_name.value.strip()}` does not meet the requirements, asking agent to update")
        client.agents.messages.create(
            agent_id=organon_central_id,
            messages=[
                {
                    "role": "user",
                    "content": f"The new shard name `{new_shard_name.value}` does not meet the requirements. Please update the name block to a valid name."
                },
            ]
        )
    else:
        break

# Check to see if the shard agent exists by this name. If so, throw an error.
shard_agents = client.agents.list(project_id=project_id, name=new_shard_name.value.strip())
if len(shard_agents) > 0:
    print(f"Shard agent `{new_shard_name.value}` already exists, deleting it")
    client.agents.delete(agent_id=shard_agents[0].id)

# Create new blocks for the shard agent containing their lexicon and identity
new_shard_lexicon_block = client.blocks.create(
    project_id=project_id,
    label=f"{new_shard_name.value.strip()}-lexicon",
    value=new_shard_lexicon.value,
    description=f"The lexicon for the `{new_shard_name.value.strip()}` shard. {prompt_domain_lexicon_description}",
)
new_shard_identity_block = client.blocks.create(
    project_id=project_id,
    label=f"{new_shard_name.value.strip()}-identity",
    value=new_shard_identity.value,
    description=f"The identity for the `{new_shard_name.value.strip()}` shard. {prompt_shard_identity_description}",
)

# Create the new shard agent
new_shard_agent = client.agents.create(
    project_id=project_id,
    name=new_shard_name.value.strip(),
    description=new_shard_identity.value,
    model="goog/gemini-2.5-flash",
    block_ids=[
        new_shard_lexicon_block.id,
        new_shard_identity_block.id,
        shard_operational_protocols_block.id,
        shard_communication_protocols_block.id,
    ],
    tags=["organon-shard"],
)

print(f"New shard agent created: {new_shard_agent.id}")

# Find the tool by the name of send_message_to_agents_matching_tags
tool_list = client.tools.list(name="send_message_to_agents_matching_tags")
if len(tool_list) == 0:
    raise ValueError("Tool send_message_to_agents_matching_tags not found")

send_message_to_agents_matching_tags = tool_list[0]

# Attach the tool to the shard agent
client.agents.tools.attach(
    agent_id=new_shard_agent.id,
    tool_id=send_message_to_agents_matching_tags.id,
)

# Message the shard agent to fill in its lexicon and identity
client.agents.messages.create(
    agent_id=new_shard_agent.id,
    messages=[
        {
            "role": "user",
            "content": "You are a new shard agent. Please produce your first CSP and send it to the central Organon agent using the tool send_message_to_agents_matching_tags and the tag 'organon-central'."
        },
    ]
)

for message in response.messages:
    print(message)
