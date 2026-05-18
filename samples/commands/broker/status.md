Check the vibe-broker status and agent info.

Arguments: $ARGUMENTS (optional -- "agents" to list all agents)

Steps:
1. Call broker_status to check broker health
2. If registered, also call agent_info with the remembered agent name
3. The broker resolves the name to agent ID automatically
4. If "agents" was specified, call agent_list to show all registered agents
5. Report: broker status, uptime, active agents, and current agent info
