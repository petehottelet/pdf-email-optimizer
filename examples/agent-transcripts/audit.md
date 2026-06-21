# Agent Transcript: Audit

User:

```text
Audit this PDF and tell me why it is so large.
```

Command:

```bash
pdf-email-optimizer input.pdf --audit --json
```

Expected response:

```text
Summarize page count, image count, private payload indicators, warnings, and the recommended profile.
Do not write an optimized PDF unless the user asks for one.
```
