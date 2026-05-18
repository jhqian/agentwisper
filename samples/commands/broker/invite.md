Invite an agent to join a squad via the vibe-broker MCP server.

Arguments: $ARGUMENTS

Expected format: <agent_name_or_id> [role]

Default role is "member". Available roles: member, observer.

Steps:
1. Use the remembered agent name as caller_id. If not registered yet, call agent_register first.
2. Use the remembered squad_id. If no squad exists, call squad_create first.
3. Parse the arguments: first token is the agent to invite (name or ID), optional second token is the role.
4. Call squad_join with squad_id, agent_id set to the target name, role, and caller_id set to your name
5. The broker resolves all names to agent IDs automatically
6. Report the result
