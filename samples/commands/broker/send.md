Send a message to another agent via the vibe-broker MCP server.

Arguments: $ARGUMENTS

Expected format: <recipient> <message>

Steps:
1. Use the remembered agent name as sender_id. If not registered yet, call agent_register first.
2. Parse the arguments: first word is the recipient (agent name or agent_id), the rest is the message payload.
3. Call message_send with sender_id (name), recipient (name), payload, and msg_type="p2p"
4. The broker automatically resolves names to agent IDs
5. Report the msg_id and status
