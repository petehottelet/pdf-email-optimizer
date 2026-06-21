# Discussions setup (draft)

This file is the maintainer's template for setting up GitHub Discussions on the repo. Once Discussions is enabled (Settings -> Features -> Discussions), create the categories below and pin the welcome post.

## Suggested categories

| Category | Format | Description |
|---|---|---|
| General | Open discussion | Anything that doesn't fit elsewhere |
| Benchmark results | Open discussion | Share real-world before/after results |
| Fixture submissions | Open discussion | Discuss potential public benchmark fixtures |
| Bug reports | Q&A | For bugs that aren't yet GitHub issues |
| Optimization quality | Q&A | Visual/render questions about specific PDFs |
| Ideas | Ideas | Feature requests and shape-of-the-tool discussion |

## Welcome / pinned post

Title: **Help validate `pdf-email-optimizer` on real-world PDFs**

Body:

> Thanks for stopping by. The bundled benchmark corpus is honest but synthetic; the part that's hard to fake is people running it on PDFs we'd never think of.
>
> If you've used the tool on a PDF you'd otherwise need to email, please share:
>
> - PDF type (marketing deck, scan, screenshot report, etc.)
> - Original size and optimized size
> - The command you used, e.g.
>
>   ```
>   pdf-email-optimizer input.pdf output_email.pdf --target-mb 7 --balanced
>   ```
>
> - Whether the optimized PDF emailed successfully (Gmail, Outlook, etc.)
> - Whether the output looked correct, or where it broke
> - Any visual issues worth flagging
>
> Please do **not** upload sensitive PDFs to a public discussion. If your file can't be shared safely, describe it and post only the numbers. The fixture submission issue template has a privacy checklist too:
>
> https://github.com/petehottelet/pdf-email-optimizer/issues/new?template=fixture-submission.yml
>
> Maintainers anonymize and add representative results to [`docs/field-validation.md`](../docs/field-validation.md). Thanks for helping make the project's claims earned, not asserted.
