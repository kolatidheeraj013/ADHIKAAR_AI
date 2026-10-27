# Bot Interface and Internal Data Improvements

## Scope and Constraint

Implement the improvements below to the bot interface and internal data handling.

**Do not change anything else in `bot.py` beyond the changes required to implement these requirements.**

## 1. Show “Browser Schemes” Only When Appropriate

- Do not display the **Browser Schemes** option by default or on every screen.
- Show it only after the user has uploaded documents and the bot has successfully understood enough relevant information to search for applicable schemes.
- If the uploaded information is missing, unreadable, or insufficient, keep the option hidden and explain what additional information is needed when appropriate.

## 2. Return Person-Specific Scheme Matches

When a user types **“Browser Schemes”** or another supported hint or trigger phrase after uploading documents, find schemes using the available Kaggle CSV files and, only when necessary and feasible, clearly sourced web-derived data already loaded into the system.

Return fewer than four schemes (**at most three**), selected according to their relevance to the person's available information.

For each scheme, display the following information in a simple format:

1. **Scheme name**
2. **Benefit amount**
3. **Number of missing document types**
4. **Names of the missing document types**
5. **Missing user information** required to assess eligibility or complete the application

Only report missing items supported by the scheme requirements and the user's known information. Do not present an item as definitely missing when the available data is inconclusive.

If no suitable scheme can be identified, explain this clearly instead of listing unrelated schemes.

### Scheme Data Sources

- Use the Kaggle CSV files as the primary source where they contain relevant scheme details.
- If required details are absent, use reliable, clearly sourced web-derived data that has already been collected and loaded into the system, where available and appropriate.
- Store the source and relevant metadata for imported scheme information so details can be verified and refreshed.
- Do not make direct website access a requirement of this implementation. Use the approved, pre-collected data available to the bot.

### Fine-Tuning Versus Loading Web-Derived Data

**Loading scheme information does not, by itself, require fine-tuning.**

In most cases, adding curated scheme data to the CSV files, data store, or retrieval system is a separate and simpler process.

Fine-tuning changes model behaviour and is a larger, separate workflow. It should not be assumed necessary simply because new scheme data is added.

First, implement and evaluate retrieval using the existing CSV files and loaded data. Consider fine-tuning only if testing identifies a specific problem that retrieval and prompt or application logic cannot adequately solve.

## 3. Show Citizen-Output Buttons Only When Relevant

The bot currently supports 14 defined citizen outputs, including:

- Submitted
- Not eligible
- Missing documents
- Question
- Extra verification
- Could not complete
- Expired
- Cancelled
- Browse results
- Status update
- Other existing outputs

These buttons must not all appear at once.

- Show only the buttons relevant to the current conversation state, user intent, and available application or scheme information.
- Keep unrelated actions hidden.
- Update the available buttons as the conversation progresses.
- Preserve all existing citizen-output features and their functionality.

## 4. Clear User Chat Every 30 Minutes

User chat and session data must expire and be cleared every **30 minutes**, whether or not the LMS server is running.

- The expiry mechanism must not depend exclusively on the LMS server starting or remaining online.
- Apply the timeout consistently, including to stale sessions.
- Handle cleanup safely so one user's session does not affect another user's data.
- Define which session data is cleared.
- Ensure the required persistence, privacy, and data-retention behaviour remains consistent with the application's design.

## 5. Keep Responses Relevant to the User

- Return only information relevant to the user's question, uploaded documents, known context, and scheme-search intent.
- Do not generate generic or unrelated scheme suggestions.
- Clearly distinguish confirmed facts from unknown or incomplete information.
- Ask for the minimum additional information needed when the current context is insufficient.
- Do not claim that a user is eligible or ineligible unless the available information supports that conclusion.
- Ensure scheme recommendations are based on the particular user's information rather than generic responses.

## 6. Handle User Queries and Input Exceptions

Implement robust exception handling for user inputs and interaction paths, including:

- Text queries, including empty, unclear, malformed, or unrelated queries.
- Voice messages, including transcription failures and empty transcripts.
- Supported commands and hint or trigger phrases.
- Document uploads, including unsupported formats, unreadable files, extraction failures, and incomplete uploads.
- Text context extracted from documents or provided during the conversation.
- Missing, inconsistent, or insufficient user data.
- Missing or malformed scheme data, CSV read errors, and retrieval failures.
- Model, network, or optional data-source failures.

### Exception-Handling Requirements

- Display clear, user-friendly error messages.
- Prevent recoverable input or processing errors from crashing the conversation.
- Log diagnostic details safely for troubleshooting.
- Do not expose internal errors, sensitive document content, or private user information to the user.
- Handle failures gracefully when optional web-derived data is unavailable.
- Do not invent scheme details when the CSV or other available data is incomplete.

### Scope of the Chatbot

The chatbot is specifically designed for browsing and identifying applicable schemes and handling actions directly related to that process.

It must handle the following when directly or indirectly related to scheme browsing:

- The initial user query
- Subsequent text messages
- Voice messages
- Supported commands
- Document uploads
- Extracted document content
- User-provided text context
- Scheme searches and related follow-up questions

Unrelated requests should receive a brief, relevant redirection rather than an unrelated answer.

## Acceptance Criteria

1. The **Browser Schemes** option remains hidden until sufficient relevant user or document information has been uploaded and understood.
2. A scheme search returns at most three relevant schemes and includes all five requested information fields wherever the available data supports them.
3. Scheme results are based primarily on the available Kaggle CSV data, supplemented only by available, sourced web-derived data when necessary.
4. Citizen-output buttons appear contextually instead of all at once.
5. User chat and session data expire after 30 minutes, independently of LMS server startup.
6. Responses remain specific to the user's context and do not assert unsupported eligibility conclusions or missing-document details.
7. Exceptions across supported input types and data-processing paths are handled without crashing the conversation or exposing sensitive internal information.
8. No unrelated changes are made to `bot.py`.