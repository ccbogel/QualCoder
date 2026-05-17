Create concise metadata for a new AI agent chat. Return ONLY one JSON object with this shape:
{"name": "short chat title", "summary": "one short summary sentence"}

Rules:
- Write both fields in {{AI_LANGUAGE}}.
- name must be specific, 2 to 8 words, and must not be a generic placeholder.
- name must not contain quotes, line breaks, or ending punctuation.
- summary must be one concise sentence, max 160 characters.
- Base the result only on the first user message.
- Do not output prose outside JSON.
