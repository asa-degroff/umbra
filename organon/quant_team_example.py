"""
Letta Multi-Agent Financial Analysis Team Example
================================================

This example demonstrates how to create a team of autonomous AI agents that work together
to analyze financial markets, each with their own specialized knowledge and shared data.

Key Concepts:
------------
1. **Memory Blocks**: Letta agents use "memory blocks" to store and access information.
   Think of these as persistent knowledge bases that agents can read and write to.

2. **Shared vs Private Memory**: 
   - Shared blocks (like market data) are attached to multiple agents
   - Private blocks (like proprietary models) are only attached to specific agents

3. **Agent Communication**: Agents can send messages to each other using tools,
   allowing them to share findings and coordinate analysis.

Architecture:
------------
- 3 Quant Agents: Each analyzes markets using different strategies
  - Momentum Quant: Uses price momentum signals
  - Value Quant: Uses fundamental value metrics  
  - ML Quant: Uses machine learning predictions
  
- 1 Portfolio Manager: Receives and consolidates findings from all quants

Memory Design:
-------------
- Global Shared Memory: "market-data" - All agents see the same market data
- Local Private Memory: Each quant has their own model/strategy block
- PM Aggregation Memory: "aggregated-signals" - Stores consolidated findings

Workflow:
--------
1. All agents read shared market data
2. Each quant analyzes using their unique approach
3. Quants send findings to the Portfolio Manager
4. PM aggregates insights and produces final report
"""

from letta_client import Letta
import os

client = Letta(token=os.environ["LETTA_API_KEY"])
project_id = "your-project-id"

# 1. Create shared memory blocks (global data)
market_data = client.blocks.create(
    project_id=project_id,
    label="market-data",
    value="S&P500: 4800, VIX: 15.2, DXY: 102.5...",
    description="Shared financial market data"
)

# 2. Create individual quant memory blocks
quant1_model = client.blocks.create(
    project_id=project_id,
    label="quant1-momentum-model",
    value="Momentum factor model: 12-month return signals...",
    description="Quant 1's proprietary momentum model"
)

quant2_model = client.blocks.create(
    project_id=project_id,
    label="quant2-value-model", 
    value="Value factor model: P/E ratios, book values...",
    description="Quant 2's value investing model"
)

quant3_model = client.blocks.create(
    project_id=project_id,
    label="quant3-ml-model",
    value="LSTM predictions, feature importance weights...",
    description="Quant 3's ML model"
)

# 3. Create agents with mixed memory (shared + individual)
quant1 = client.agents.create(
    project_id=project_id,
    name="quant-momentum",
    block_ids=[market_data.id, quant1_model.id]  # Shared + Individual
)

quant2 = client.agents.create(
    project_id=project_id,
    name="quant-value",
    block_ids=[market_data.id, quant2_model.id]
)

quant3 = client.agents.create(
    project_id=project_id,
    name="quant-ml",
    block_ids=[market_data.id, quant3_model.id]
)

# 4. Create portfolio manager with access to all findings
pm_findings = client.blocks.create(
    project_id=project_id,
    label="aggregated-signals",
    value="",  # Will be populated by quant reports
    description="Consolidated findings from all quants"
)

portfolio_manager = client.agents.create(
    project_id=project_id,
    name="portfolio-manager",
    block_ids=[market_data.id, pm_findings.id],
    tags=["pm"]  # Tag for message routing
)

# 5. Give quants ability to send findings to PM
send_to_pm_tool = client.tools.list(name="send_message_to_agents_matching_tags")[0]
for quant in [quant1, quant2, quant3]:
    client.agents.tools.attach(agent_id=quant.id, tool_id=send_to_pm_tool.id)

# 6. Run analysis
for quant in [quant1, quant2, quant3]:
    response = client.agents.messages.create(
        agent_id=quant.id,
        messages=[{"role": "user", "content": "Analyze market and send findings to PM (tag: pm)"}]
    )