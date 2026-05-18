Wait for new messages from the vibe-broker (blocking).

Arguments: $ARGUMENTS (optional -- timeout in seconds, default 30)

Steps:
1. Use the remembered agent name. If not registered yet, call agent_register first.
2. Parse the arguments: if a number is provided, use it as timeout (seconds). Default is 30. Use 0 for non-blocking (returns immediately).
3. Call message_wait with agent_id set to the remembered name, timeout set to the parsed value, and limit=50
4. The broker automatically resolves the name to an agent ID
5. This call blocks until a message arrives or timeout expires:
   - If messages were already pending, returns immediately with waited=false
   - If a new message arrives during wait, returns with waited=true
   - If timeout expires with no messages, returns empty with waited=false
6. List each received message with: sender, type, payload, msg_id
7. If no messages received, report "No messages (waited X seconds)"
