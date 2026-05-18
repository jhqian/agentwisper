Register this Claude Code instance as an agent on the vibe-broker MCP server.

Agent name: $ARGUMENTS

If no name is provided, use "claude-agent" as default.

Steps:
1. Call agent_register with the name and capabilities ["code", "review", "testing"]
2. Report the returned agent_id and name
3. Remember both agent_id and name for the rest of the session
4. In all future broker commands, use the name as the identifier -- the broker resolves names to IDs automatically
