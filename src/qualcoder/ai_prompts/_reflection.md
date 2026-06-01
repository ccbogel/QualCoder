Your task: Review the collected evidence and action progress, then decide whether more MCP calls are needed. Return ONLY one JSON object with this shape:
{"enough_information": true|false, "reflection_summary": "one short user-facing note", "next_step_note": "optional short alias", "methodology_decision": "allow|allow_with_caveat|reframe_and_ask|refuse", "methodology_note": "optional short note with caveat, concern, safer alternative, or framework issue", "continue_deferred_calls": true|false, "user_decision_required": true|false, "decision_question": "optional question", "decision_context": "optional short reason", "proposed_next_calls": [{"method": "resources/list|resources/read|resources/templates/list|initialize|tools/list|tools/call", "params": {}}], "revised_calls": [{"method": "resources/list|resources/read|resources/templates/list|initialize|tools/list|tools/call", "params": {}}], "answer_brief": "short answer plan for final response"}

Rules:
- Allowed methods: initialize, resources/list, resources/templates/list, resources/read, tools/list, tools/call.
- Initialize, resources/list, and resources/templates/list are already available in context unless explicitly changed or compacted.
- Reassess the task using the global methodological rules from the base agent prompt.
- If `methodology_decision` is `reframe_and_ask` or `refuse`, stop further evidence collection: set `enough_information=true`, `revised_calls=[]`, `proposed_next_calls=[]`, `user_decision_required=false`, and use `answer_brief` to sketch the response for the final answer phase.
- Use as few additional calls as possible and keep them focused.
- If the result from an early MCP-call was compacted away but you want to use this data again, reread it. Do not rely on fragments of content still being present in the conversation context.
- If you need any tool and the available tools are not already known from the current conversation context, call tools/list before planning or using tools/call.
- Use tools/call only for tools that have already been discovered through tools/list in the current conversation context.
- If deferred_calls are listed in the reflection prompt, decide explicitly whether they should continue unchanged by setting continue_deferred_calls=true or false.
- If continue_deferred_calls=true, you may keep revised_calls empty to continue the deferred queue unchanged, or provide revised_calls to prepend/adjust the next steps.
- Default to user_decision_required=false.
- Set user_decision_required=true only when the global agent rules require a user decision or confirmation.
- If user_decision_required=true, provide one concise natural-language question in decision_question, keep revised_calls empty, and put suggested follow-up MCP actions into proposed_next_calls.
- If the user explicitly requested write actions, include revised_calls that execute the remaining write actions whenever this is possible.
- If a delete action still needs user confirmation after preview, set user_decision_required=true and place the execute tool with the preview_token into proposed_next_calls.
- Do not stop with explanations only if executable actions are still pending.
- If the task was about collecting information and you now have enough evidence for a final answer, set enough_information=true and revised_calls=[].
- If more information or actions are still needed, set enough_information=false and propose only the necessary revised_calls.
- reflection_summary must be one sentence, user-facing, <=160 characters.
- Avoid boilerplate like "I will" or "Next step is" unless strictly needed.
- next_step_note is optional and only used when reflection_summary is empty.
- Do not output prose outside JSON.
