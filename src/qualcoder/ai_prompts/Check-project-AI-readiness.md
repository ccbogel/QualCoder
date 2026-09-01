---
name: Check-project-AI-readiness
description: "Checks whether the current QualCoder project is well prepared for working with the AI agent and produces a prioritized report with concrete recommendations for improvement."
---

Assess how well the current QualCoder project is prepared for productive, methodologically sound work with the AI agent. Perform a read-only audit: inspect the available project information, but do not change any project data.

This is an AI-readiness assessment, not a general judgment of the quality of the research project. Evaluate each criterion in relation to the project's apparent research design, analytic method, and current stage. For example, do not treat a missing code system as a problem when coding has not started yet. Distinguish clearly between confirmed problems, reasonable concerns, and aspects you cannot assess.

## Audit process

1. Review the project memo included in your context.
2. Inspect the available document inventory, document memos and attributes, cases and case links, and the code/category tree where relevant.
3. Inspect representative excerpts from the empirical text documents. Select a varied sample based on document names, types, lengths, and apparent roles in the project. For small corpora, inspect every document where practical; for larger corpora, use a transparent sample and state what you inspected.
4. For documents that appear to be interviews or group discussions, inspect enough text from the beginning and, where useful, another part of the transcript to assess speaker identification and formatting consistency.
5. Do not attempt a substantive analysis of the empirical material. Retrieve only as much text as is needed for the readiness audit.

## What to assess

### 1. Project memo and analytic orientation

Check whether the project memo gives the agent the information it needs to collaborate appropriately:

- research question and aims;
- object of study, context, and relevant boundaries of the study;
- description of the sample;
- data types and data-collection methods;
- methodological framework;

Assess relevance as well as completeness. Flag theory that is too extensive or insufficiently connected to analytical decisions, duplicated or outdated information, personal reminders, provisional thoughts presented as settled decisions, and other material that may distract or mislead the agent. Do not label theoretical material as unnecessary when it genuinely guides interpretation or method. Recommend what should be added, clarified, shortened, moved elsewhere, or explicitly marked as provisional.

### 2. Corpus organization and technical readability

Check whether the empirical material is accessible and interpretable by the text-based AI agent:

- filenames are unique, descriptive, consistent, and meaningful without relying on undocumented codes;
- because filenames are also used to generate source references, they should not be unnecessarily complex;
- file boundaries make analytic sense, for example one interview or case per document where appropriate;
- documents are not empty, unexpectedly short, duplicated, or obviously incomplete;
- extracted text is readable and does not show substantial OCR, encoding, line-break, hyphenation, table, or layout problems;
- headers, footers, timestamps, page markers, or metadata do not overwhelm the empirical content;
- interviews and group discussions consistently distinguish interviewers or moderators from respondents and distinguish individual participants from one another;
- speaker labels and transcription symbols are used consistently and explained where necessary;
- the languages used, any translations, and multilingual material are documented sufficiently;
- relevant context that is not part of the transcript itself is available in document memos or attributes.

The agent can currently work only with textual material. State this limitation clearly. If the accessible inventory does not reveal whether additional audio, video, image, or inaccessible PDF material exists, mark that point as not assessable rather than assuming that the corpus is complete.

### 3. Cases, attributes, and project structure

Assess whether the project structure helps rather than hinders targeted AI-supported analysis:

- cases represent the intended units of analysis and are linked to the correct documents or text segments;
- case and document names are understandable and consistently formatted;
- if case or document attributes exist, check whether they use consistent values and have no unexplained gaps;
- document and case memos, if available, contain useful contextual information rather than undocumented shorthand;
- if coding has started, categories and codes are coherently organized and their names and memos provide enough guidance to interpret and apply them;
- apparent duplicates, ambiguous labels, inconsistent terminology, or contradictions between the memo, documents, cases, attributes, and code system are identified.

Do not recommend adding cases, attributes, or codes merely for completeness. Tie every recommendation to the research design or a plausible intended AI workflow.

### 4. Privacy, responsible use, and analytical risks

Check for readiness issues that could make AI-supported work unsafe or misleading:

- obvious direct identifiers or unnecessarily sensitive information in the inspected material or metadata;
- unclear distinctions between empirical data, researcher interpretation, and personal notes;
- sample limitations or methodological constraints that the agent needs to know to avoid overgeneralization;

Do not claim to perform a legal, ethical, or comprehensive privacy audit. Report only what the available project information and sampled material support.

## Required report

Produce a concise but sufficiently specific report with this structure:

1. **Overall assessment**: provide an overall assessment of the project, followed by a short rationale.
2. **Strengths**: list preparation choices that already support reliable work with the AI agent.
3. **Findings and recommendations**: provide a table with the columns `Priority`, `Area`, `Finding`, `Evidence`, `Why it matters`, and `Concrete action`.
4. **Assessment coverage and limitations**: state which inventories and documents you inspected, whether sampling was used, and what could not be assessed.

Translate the priority labels `Critical`, `High`, `Medium`, and `Low` into the user's language, and use them sparingly and consistently. Recommendations must be concrete enough to act on; include examples of improved filenames, speaker labels, memo sections, or attribute values where useful. Avoid generic advice that is not tied to an observed finding. Take the methodological framework of the study into account and only make recommendations that make sense within this framework.

Do not invent missing information or treat an unassessed criterion as failed. When evidence is mixed, explain the uncertainty. When citing empirical text, use only short excerpts needed to demonstrate a formatting or readiness problem and follow the required source-reference format.
