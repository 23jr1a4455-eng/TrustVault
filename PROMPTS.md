\# PROMPTS.md



\## Reusable instructions

1\. Every route touching a document calls `authorize(user, doc, action)`.

2\. Deny by default. Unknown role, action, or state means deny.

3\. Never put permissions in tokens; read grants from the DB each request.

4\. Log every ALLOW AND DENY to `audit\_events` before replying.

5\. `audit\_events` is append-only. Never write code that edits or deletes it.

6\. Return 404, not 403, for documents the user cannot read.

7\. Never trust uploaded filenames or content types.

8\. Any auth change needs a test that fails when the check is removed.



\## Entries



\### 2026-10-19: Setup repository and environment files

\- Asked: Initialize project structure, set up .env configs, CLAUDE.md rules, and PROMPTS.md tracking.

\- Produced: Repository configuration files and security rules.

\- Wrong (specific): N/A

\- Did instead (commit link): Pending initial commit.

\- Area: other

