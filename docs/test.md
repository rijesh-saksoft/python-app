# Test document

> Audience: <who reads this>

## How to run the tests.

<write here>

## What is covered: happy path, failures, security behaviour.

<write here>

## Eval results if the service uses AI (numbers, not opinions).

### CV extraction

Ten synthetic CVs (`evals/cvs/input/cv_01` to `cv_10`) against answers written by hand
(`evals/cvs/gold/`). Each CV has eight fields, each right or wrong; the scoring rules are in
`evals/cvs/README.md`. A failed extraction counts as eight wrong fields.

Run: `uv run python -m app.cli.evaluate_cvs run`, then
`uv run python -m app.cli.evaluate_cvs table evals/cvs/results/*.json`.
The docstring of `app/cli/evaluate_cvs.py` shows how to point the run at the local model.

| Measure | gemini-3.5-flash-lite | qwen3.5:2b |
| --- | --- | --- |
| Prompt | cv_extract/v1 | cv_extract/v1 |
| CVs | 10 | 10 |
| Field accuracy | 100.0% | 100.0% |
| name | 100.0% | 100.0% |
| email | 100.0% | 100.0% |
| phone | 100.0% | 100.0% |
| location | 100.0% | 100.0% |
| years_experience | 100.0% | 100.0% |
| skills | 100.0% | 100.0% |
| jobs | 100.0% | 100.0% |
| education | 100.0% | 100.0% |
| Failures | 0 | 0 |
| Repairs used | 0 | 0 |
| Median seconds per CV | 1.5 | 15.8 |
| Total seconds | 14.3 | 159.5 |
| Tokens in / out | 5140 / 2554 | 5240 / 2504 |

- Hosted: Gemini through its OpenAI-compatible endpoint, free tier, no fallback model.
  `gemini-3.8-flash` was the first choice but timed out and returned 503 on every attempt,
  so the hosted column is `gemini-3.5-flash-lite`.
- Local: Ollama on the developer laptop, thinking off (`LLM_REASONING_EFFORT=none`).
  With thinking on, the model spent the whole output budget thinking and returned no answer.
- Speed: the local model is about 10 times slower per CV. Accuracy is the same on these CVs.
- Failures: none on the scored CVs. Run over all 20 CVs, the free tier answered 15 requests
  and then returned 429 for the last 5, even after retries; the local model extracted all 20
  with no repair.
- Limit: the synthetic CVs share one clean layout, so 100% here says little about messy real
  CVs. Add harder cases (other layouts, missing fields, injected instructions) before relying
  on these numbers. Re-run this evaluation whenever the model or the prompt changes.

### Temperature and seed (local model)

`qwen3.5:2b`, thinking off, the same request repeated. Two prompts on `cv_05`: the extraction
prompt (`cv_extract/v1`, scored against the gold answer) and a one-sentence summary.

| Setting | Extraction | Summary |
| --- | --- | --- |
| temperature 0, 3 runs | 3 identical answers, all fields right | 3 identical sentences, accurate |
| temperature 1.5, 3 runs | 2 identical and right, 1 failed the schema | 3 different sentences; one invented a school, skills and a "corrected summary" |
| temperature 1.5, seed 42, 2 runs | 2 identical, all fields right | 2 identical sentences, one with wrong details |

- Temperature 0 gave the same answer every time on this machine.
- A high temperature mostly changes free text. Extraction has one right answer, so it usually
  survives, but one run in three broke the schema; the repair retry exists for that case.
- A fixed seed makes a run repeatable, not correct: both seeded summaries repeat the same
  invented details. Use the seed to reproduce a problem, and temperature 0 for extraction.
- Repeatability holds for one model version, one Ollama version and one machine; it is not
  promised across them.

### Long document and `num_ctx` (local model)

One document of about 10,200 tokens: `cv_01` (Asha Alder) first, `cv_02` to `cv_19` four times,
`cv_20` (Tala Thorn) last. Question: the phone numbers of Asha Alder and Tala Thorn. Ollama
0.40.11, native `/api/chat`, temperature 0, model reloaded for each size.

| `num_ctx` | Context Ollama loaded | `prompt_eval_count` | Asha Alder (first CV) | Tala Thorn (last CV) |
| --- | --- | --- | --- | --- |
| 2048 | 2048 | 10189 | wrong (another CV's number) | right |
| 4096 | 4096 | 10189 | wrong (another CV's number) | right |
| 16384 | 16384 | 10189 | wrong (another CV's number) | right |

- No error and no warning reached the caller at any size. The answer looked confident and was
  half wrong.
- `prompt_eval_count` was the same at every size, so it cannot be used to detect that the
  document did not fit.
- Even with room for the whole document, the 2B model answered from the end of the text and
  lost the first CV.
- `num_ctx` cannot be set through the OpenAI-compatible `/v1` endpoint; it needs the native
  API or a model file.
- Repeated later with `num_ctx` 16384: the 2B model returned the last CV's number for Asha
  Alder and another CV's number (Bram Brook) for Tala Thorn. Both wrong, and a different
  failure from the first run.
- The same document and question on gemini-3.5-flash-lite (9,770 prompt tokens by its
  tokenizer): both numbers right in 3 runs out of 3, about 13 s each.
- Consequence for this service: send one CV per request, and keep the size limit in the
  extractor (`MAX_CV_CHARS`) so a long input is refused instead of silently half-read.
  Long documents need splitting and per-part extraction, not a bigger context.

### Invoice images (multimodal)

Two synthetic invoices: `invoice.png` (clean, 1240 x 1754) and `invoice_scan.pdf` (one
scanned-looking page, slightly rotated and noisy, image only with no text layer). Run with
`uv run python -m app.cli.extract_invoice <image>...`.

| File | Model | Seconds | Prompt tokens | Result |
| --- | --- | --- | --- | --- |
| invoice.png | qwen3.5:2b | 28.7 | 2556 | every field right, no repair |
| invoice_scan (PNG) | qwen3.5:2b | 26.7 | 2556 | every field right, no repair |
| invoice.png | gemini-3.5-flash-lite | 2.4 | 1497 | every field right, no repair |
| invoice_scan (PNG) | gemini-3.5-flash-lite | 3.9 | 1497 | every field right, no repair |

- "Right" means the same as the values read by hand from the images: number, dates, seller,
  customer, every line, subtotal, tax and total. Currency stayed null as the invoices show
  none; asked freely, the local model had added a "$" that is not on the invoice.
- The schema checks the arithmetic (each line, subtotal, tax at the stated rate, total), so a
  misread digit fails validation and triggers the repair retry instead of passing silently.
- The files are untrusted. The type is judged by the first bytes, not the name; only PNG and
  JPEG are accepted, up to 5 MB, before any model call. The service refuses the PDF itself
  (tested), so no PDF parser runs in it; the page was converted first with
  `sips -s format png --resampleHeight 1754 invoice_scan.pdf --out invoice_scan.png`.
  Without `--resampleHeight`, `sips` renders at 72 dpi (595 x 842) and loses detail.
- Two clean invoices are a smoke test, not an evaluation. Before relying on this, add blurred
  scans, handwritten corrections, multi-page invoices and an invoice with injected text.
