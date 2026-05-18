Poll for unread messages from the vibe-broker.

Arguments: $ARGUMENTS (optional -- "all" to include read messages)

Steps:
1. Use the remembered agent name. If not registered yet, call agent_register first.
2. Call message_poll with agent_id set to the remembered name and unread_only=true (default) or unread_only=false (if "all" was specified)
3. The broker automatically resolves the name to an agent ID
4. List each message with: sender, type, payload, msg_id
5. If there are unread messages, summarize them clearly
