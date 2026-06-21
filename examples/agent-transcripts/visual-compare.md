# Agent Transcript: Visual Compare

User:

```text
Compare these two PDFs visually.
```

Command:

```bash
pdf-email-render-compare original.pdf optimized.pdf --output-dir qa-renders
```

Expected response:

```text
Report page count, whether renders are identical, page-level RMS differences, changed pixel percentages, and the output render directory.
Mention that automated visual QA is not a substitute for human review on high-stakes documents.
```
