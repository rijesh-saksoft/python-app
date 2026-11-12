# RAG lab

Measurements behind the retrieval design: how text turns into tokens, and which way of
chunking documents finds the right passage. All texts are synthetic.

## Token counts

Six texts in `evals/tokens/`: English prose, Python code, JSON, and the same prose translated
into Hindi, Malayalam and German. Each model counts with its own tokenizer, through the
`prompt_tokens` the chat API reports, minus the chat template around the message (measured
with a one-character message). Run it with `uv run python -m app.cli.count_tokens`.

| Text | Characters | qwen3.5:2b tokens | gemini-3.5-flash-lite tokens | Characters per token (qwen / gemini) |
| --- | --- | --- | --- | --- |
| English prose | 339 | 69 | 70 | 4.9 / 4.8 |
| Python code | 316 | 85 | 95 | 3.7 / 3.3 |
| JSON | 410 | 196 | 202 | 2.1 / 2.0 |
| Hindi (same prose) | 363 | 149 | 102 | 2.4 / 3.6 |
| Malayalam (same prose) | 408 | 219 | 133 | 1.9 / 3.1 |
| German (same prose) | 385 | 79 | 82 | 4.9 / 4.7 |

Tokens for the same meaning, compared with English:

| Language | qwen3.5:2b | gemini-3.5-flash-lite |
| --- | --- | --- |
| German | 1.1× | 1.2× |
| Hindi | 2.2× | 1.5× |
| Malayalam | 3.2× | 1.9× |

What this means:

- "About four characters per token" holds only for English and similar languages. The same
  message in Malayalam costs three times as many tokens on the small model: three times the
  price on a paid API, a third of the effective context window, and slower answers.
- Tokenizers differ by model. The hosted model's tokenizer covers Indian scripts better, so
  token budgets and chunk sizes must be measured with the model that will be used.
- JSON is the most expensive text per character: quotes, braces, keys repeated in every
  record, and timestamps split into many digit tokens. Sending only the fields a prompt needs
  saves more than shortening the instructions.
- Code costs more than prose because of indentation, symbols and identifiers that are not
  ordinary words.

## Chunking and retrieval

20 synthetic policy documents of an invented company (`evals/rag/docs/`, about 200 to 300
words each, with `##` sections) and 10 questions labelled by hand with the document that
answers them (`evals/rag/questions.json`). The questions are paraphrased, not copied from the
documents, and some are traps: q03 says "driver" but is answered by the leave policy, q07
says "drivers" but is answered by the data protection policy.

Three ways of chunking:

| Chunking | How | Chunks | Average characters |
| --- | --- | --- | --- |
| `fixed_size` | 500 characters with 100 overlap, cut anywhere | 65 | 450 |
| `by_section` | one chunk per `##` section, with "document title - heading" in front | 118 | 226 |
| `by_sentences` | 3 whole sentences per chunk, headings dropped | 93 | 239 |

Embeddings: `nomic-embed-text` in local Ollama (768 dimensions, Apache-2.0), with the task
prefixes the model expects (`search_query: `, `search_document: `). Vector store: in memory,
cosine similarity (`app/services/vector_store.py`). A question counts as a hit at k when a
chunk of the expected document is among the top k chunks. Run it with
`uv run python -m app.cli.evaluate_retrieval` and the `EMBEDDING_*` settings.

| Chunking | hit@1 | hit@3 | hit@5 | MRR |
| --- | --- | --- | --- | --- |
| `fixed_size` | 7/10 | 9/10 | 10/10 | 0.81 |
| `by_section` | **8/10** | 9/10 | 10/10 | **0.88** |
| `by_sentences` | 7/10 | 9/10 | 10/10 | 0.81 |

Position of the first chunk from the expected document (1 is best), for the questions that
were not first everywhere, and what ranked above it:

| Question | `fixed_size` | `by_section` | `by_sentences` | Ranked above |
| --- | --- | --- | --- | --- |
| q03 driver, two weeks off in December | 3 | **1** | 3 | vehicle and driver policy |
| q04 keeping the laptop after resigning | 1 | 1 | 2 | IT security |
| q06 clicked a phishing link: what to do, how quickly | 4 | 4 | 4 | IT security, data protection |
| q09 free chatbot with a customer's address | 2 | 2 | **1** | data protection or IT security |

Without the task prefixes all three strategies score 7/10 at hit@1 and 0.82 MRR.

### Which chunking works best, and why

Section chunking works best here, for one reason: the heading travels with the text.
In q03 the answer sentence says "warehouse and delivery staff may take at most three
consecutive days"; on its own that sentence looks like a driver rule, so fixed and sentence
chunks lose to the vehicle policy. With "Annual Leave Policy - Peak season" in front of it,
the chunk is clearly about leave and ranks first. Fixed-size chunks also cut sentences in
half and mix two topics in one chunk; sentence chunks keep sentences whole but forget which
section they came from.

The limits of this result:

- Ten questions is a small sample: the winner is ahead by one question. The ranking is a
  signal, not proof; a real project needs more questions, and real documents.
- Section chunking depends on documents having good headings. For scanned or unstructured
  text, sentence chunks with a little overlap are the safer default.
- Sections vary in size. A very long section would need splitting again, and a very short
  one carries little meaning on its own.
- No chunking fixes q06. The IT security policy talks about exactly this case ("if you clicked
  a link or entered your password") and refers to the Incident Reporting Policy, which holds
  the actual answer ("within one hour"). An answer split across a cross-reference needs a
  larger k (here 5), or retrieval that follows references; with only the top 3 chunks, the
  model would answer "report it straight away" and miss the one-hour deadline.
- Model-specific details matter: the task prefixes changed the result. Check the model card,
  and measure with the model you will deploy.

## Answering from the top 3 sections

Each question was answered from its top 3 section chunks with the `grounded_answer/v1`
prompt (the table below; `v2` is compared at the end): answer only from the passages, cite them, and say "I don't know" without support.
The passages travel as JSON data; cited passage ids are checked in code, so a model cannot
cite a passage it was not given. Run it with `uv run python -m app.cli.answer_questions`;
answers are saved in `evals/rag/answers/`.

| Question | Answer in top 3? | gemini-3.5-flash-lite | qwen3.5:2b |
| --- | --- | --- | --- |
| q01 meals, overnight trip | yes | right (60 per day) | right, but adds a "$" the policy never states |
| q02 nine days ill | yes | right (doctor's note) | right |
| q03 driver, December leave | yes | right (at most three days) | refused |
| q04 keeping the laptop | **no**: only other equipment sections | refused, correctly | refused, correctly |
| q05 concert tickets worth 120 | yes | right (decline or hand over) | refused |
| q06 phishing link | partly: IT security only | incomplete: "straight away", no one-hour deadline | refused |
| q07 delivery photos | yes | right (90 days) | right |
| q08 Sunday overtime | yes | right (2 times the rate) | right |
| q09 chatbot and an address | yes | right (approved tools only) | refused |
| q10 repaying course fees | yes | right (half) | refused |
| **Right answers** | | **8 of 10** | **4 of 10** |

What the answers show:

- Retrieval was not the main problem for the small model. The answer was in its passages
  for q03, q05, q09 and q10, and it still refused. A 2-billion-parameter model is unsure
  when a rule has to be applied to a situation ("two weeks" against "at most three
  consecutive days", "18 months" against "between 12 and 24 months"), and the prompt tells
  it to refuse when unsure. Refusing is the safe failure: it gave no wrong rule.
- The small model still added a detail of its own: "$60" where the policy says "60". Even
  with a grounding prompt, small models fill gaps from their training.
- Retrieval scored by document overstates quality. For q04 the equipment policy ranked
  first, but through its "Looking after equipment" section; the "Leaving the company"
  section with the answer was not retrieved. Both models refused, which is correct. Score
  retrieval by the passage that holds the answer, not only by the document.
- q06 shows the cross-reference problem in a real answer: the hosted model answered from the
  IT security passage it had and missed the one-hour deadline in the Incident Reporting
  Policy. The answer is not wrong, but it is incomplete, and it cites its source, so a
  reader can follow the reference.
- Prompt `v1`'s "say which rule you used" made the hosted model write "rule 1" and "passage
  1", which mean nothing to a reader. `v2` asks for the policy and section name and forbids
  passage numbers. With `v2` the hosted model names the source in every answer (for example
  "Annual Leave Policy - Peak season") with the same result: 8 right, q04 correctly refused,
  q06 still without the one-hour deadline. Answers are saved per prompt version
  (`<model>_v1.json`, `<model>_v2.json`).
- The hosted model returned HTTP 503 (overloaded) on several requests during these runs;
  retries got through. A production service needs the fallback model and a clear message
  when no model is available.
