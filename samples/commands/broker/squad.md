Create a squad on the vibe-broker MCP server.

Arguments: $ARGUMENTS

Expected format: <squad-name>

If no name is provided, use "default-squad" as default.

Steps:
1. Use the remembered agent name as caller_id. If not registered yet, call agent_register first.
2. Call squad_create with name and caller_id set to the remembered name
3. The broker resolves the name to agent ID automatically
4. Report the squad_id and your role (should be "leader")
5. Remember the squad_id for future squad operations
