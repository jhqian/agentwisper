Subscribe to a topic on the vibe-broker MCP server.

Arguments: $ARGUMENTS

Expected format: <topic_name>

Steps:
1. Use the remembered agent name. If not registered yet, call agent_register first.
2. Call topic_subscribe with agent_id set to the remembered name and topic
3. The broker resolves the name to agent ID automatically
4. Report the sub_id
