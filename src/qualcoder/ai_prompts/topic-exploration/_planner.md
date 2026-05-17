Your task: Plan the next search steps needed to explore the user's topic in the empirical data. Return ONLY one JSON object with this shape:
{"needs_mcp": true|false, "plan_summary": "one short user-facing note", "user_decision_required": true|false, "decision_question": "optional question", "decision_context": "optional short reason", "proposed_next_calls": [{"method": "resources/read", "params": {}}], "calls": [{"method": "resources/read", "params": {}}], "answer_brief": "optional draft answer idea"}

Rules:
- In this planner, use only resources/read for search resources.
- Relevant search resources are: qualcoder://vector/search, qualcoder://search/bm25, and qualcoder://search/regex.
- Do not use initialize, resources/list, resources/templates/list, tools/list, or tools/call here unless a later user turn explicitly requires something outside search.
- The current turn already contains initialize, resources/list, and resources/templates/list.
- Use as few search calls as possible, but enough to cover a broad and informative spectrum of potentially relevant material.
- Combine complementary search strategies when useful:
  * vector/search for semantic similarity and conceptually related material
  * search/bm25 for concrete keywords, phrases, and theoretically important terms
  * search/regex for lexical patterns, word stems, spelling variants, or tightly defined textual forms
- When choosing search strings, preserve the original topic idea but broaden it intelligently.
- Consider multiple formulations of the topic, including:
  * simpler everyday language
  * directly related concepts or synonyms
  * narrower facets, contrasting variants, and boundary cases
- If the topic uses scientific or technical language, actively translate it into concrete life-world expressions that may appear in empirical material.
- Prefer a small set of diverse, non-redundant search strings over many similar ones.
- In the first topic-exploration turn, keep all retrieval within the user-selected material scope already described in the conversation.
- Default to user_decision_required=false.
- Set user_decision_required=true only when the global agent rules require a user decision or confirmation.
- If user_decision_required=true, provide one concise natural-language question in decision_question, keep calls empty, and put suggested follow-up MCP actions into proposed_next_calls.
- plan_summary must be one sentence, user-facing, <=160 characters.
- Do not output prose outside JSON.
