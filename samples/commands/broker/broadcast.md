Broadcast a message to a topic via the vibe-broker MCP server.

Arguments: $ARGUMENTS

Expected format: <topic> <message>

Steps:
1. Use the remembered agent name as sender_id. If not registered yet, call agent_register first.
2. Parse the arguments: first token is the topic name, the rest is the broadcast payload.
3. Call message_broadcast with sender_id (name), topic, and payload
4. The broker resolves the name to agent ID automatically
5. Report the msg_id and sent_to
