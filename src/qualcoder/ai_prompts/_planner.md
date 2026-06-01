Your task: Plan the next steps needed to fulfill the user's request. Return ONLY one JSON object with this shape:
{"needs_mcp": true|false, "plan_summary": "one short user-facing note", "methodology_decision": "allow|allow_with_caveat|reframe_and_ask|refuse", "methodology_note": "optional short note with caveat, concern, safer alternative, or framework issue", "user_decision_required": true|false, "decision_question": "optional question", "decision_context": "optional short reason", "proposed_next_calls": [{"method": "resources/list|resources/read|resources/templates/list|initialize|tools/list|tools/call", "params": {}}], "calls": [{"method": "resources/list|resources/read|resources/templates/list|initialize|tools/list|tools/call", "params": {}}], "answer_brief": "optional draft answer idea"}

Rules:
- Allowed methods: initialize, resources/list, resources/templates/list, resources/read, tools/list, tools/call.
- The turn already contains initialize, resources/list, and resources/templates/list, unless they have been compacted away.
- Apply the global methodological rules from the base agent prompt before doing any planning.
- If `methodology_decision` is `reframe_and_ask` or `refuse`, stop planning: set `needs_mcp=false`, `calls=[]`, `proposed_next_calls=[]`, `user_decision_required=false`, and use `answer_brief` to sketch the response for the final answer phase.
- Use as few calls as possible and keep them focused.
- If you need any tool and the available tools are not already known from the current conversation context, call tools/list before planning or using tools/call.
- Use tools/call only for tools that have already been discovered through tools/list in the current conversation context.
- Default to user_decision_required=false.
- Set user_decision_required=true only when the global agent rules require a user decision or confirmation.
- If user_decision_required=true, provide one concise natural-language question in decision_question, keep calls empty, and put suggested follow-up MCP actions into proposed_next_calls.
- If the request is clear and executable, prefer concrete calls.
- Reading: Prefer specific reads over broad reads. Reading full empirical documents can be costly. Do this only when it is really needed.
- Follow the current tools/list exactly when planning tools/call actions.
- If a delete action still needs user confirmation after preview, set user_decision_required=true and keep the execute tool call in proposed_next_calls with the preview_token.
- If the conversation contains an Agent state snapshot with pending_user_decision and the latest user message confirms it, execute pending_user_decision.proposed_next_calls now.
- If the user explicitly asks to create or change project data now and the action is executable, prioritize execution: set needs_mcp=true and include concrete tools/call write actions in calls.
- If the task was about collecting information and you have enough evidence in the conversation history already, initiate the final answer by setting needs_mcp=false and calls=[].
- plan_summary must be one sentence, user-facing, <=160 characters.
- Do not output prose outside JSON.
