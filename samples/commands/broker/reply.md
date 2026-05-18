Reply to a message via the vibe-broker MCP server.

Arguments: $ARGUMENTS

Expected format: <msg_id> <reply text>

Steps:
1. Use the remembered agent name as sender_id. If not registered yet, call agent_register first.
2. Parse the arguments: first token is the parent_msg_id to reply to, the rest is the reply payload.
3. If no msg_id is provided, first call message_poll to get the latest message, then reply to it.
4. Call message_reply with parent_msg_id, sender_id (name), and payload
5. The broker resolves the name to agent ID automatically
6. Report the new msg_id
