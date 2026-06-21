# Private benchmark fixtures (local only)

This directory is for **local-only** PDFs that you cannot share publicly: client work, internal documents, NDA material, or anything containing personal information.

Everything under `private/` is `.gitignore`d. Files here will never be committed.

## How to use it

1. Drop the PDF into a per-fixture subdirectory:

   ```
   private/<id>/input.pdf
   ```

2. Run the optimizer however you would normally:

   ```bash
   pdf-email-optimizer benchmarks/corpus/private/<id>/input.pdf benchmarks/corpus/private/<id>/output.pdf \
     --target-mb 7 --balanced --report benchmarks/corpus/private/<id>/report.md
   ```

3. If the result is interesting (an edge case, a regression, an unusual savings number), file an issue with the **redacted** numbers and visual notes. Do not attach the source PDF unless it is safe to share.

The goal: let maintainers validate against realistic, sensitive PDFs without leaking them.
