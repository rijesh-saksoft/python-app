# What an LLM cannot do

A large language model (LLM) writes fluent text by predicting likely words. That makes it
very useful for reading, summarising and drafting. It also has limits that do not show in
a demo. Knowing them helps us decide together where it is safe to use one, and where a
person or ordinary software must stay in charge.

## The limits

- **It does not know your business.** A model knows only its training text. It has never
  seen your policies, customers or prices. It can use them only when we give it the
  relevant passages with each question, and it is only as good as those passages.
- **It is not up to date.** Its knowledge stops at a training date. Anything newer must be
  supplied, like your own data.
- **It can be confidently wrong.** When it lacks the answer, it may still produce one that
  sounds right: an invented figure, a mixed-up name. It does not warn you when this
  happens.
- **It does not reliably apply rules.** Deciding whether 18 months falls "between 12 and 24
  months", or whether "two weeks" breaks a "three day" limit, is easy for ordinary software
  and unreliable for a model, especially a small one.
- **It does not read long documents evenly.** A model can only take in a limited amount of
  text at once. Even within that limit, details in the middle or at the start can be lost.
- **It can be misled by the text it reads.** A document or an email that contains
  instructions can try to steer the model. The model cannot always tell your instructions
  from instructions hidden in the data.
- **It can answer the same question differently twice.** We can reduce this, not remove it.
- **It cannot take responsibility.** It cannot approve a payment, make a hiring decision or
  sign off a safety check. A person must.

## An example: small local model against large hosted model

We gave two models the same 20 CVs in one document of about 10,000 words, and asked for the
phone numbers of the first and the last candidate.

| | Small local model (2 billion parameters, on a laptop) | Large hosted model (in the provider's data centre) |
| --- | --- | --- |
| Result | Both numbers wrong: it gave the last candidate's number for the first one, and another candidate's number for the last one | Both numbers right, in three runs out of three |
| Warning given | None. The answer looked confident | Not needed |
| Time | 30 seconds | 13 seconds |

**Why:** the main reason is **size**. The small model had enough room for the whole document,
because we set its context window large enough, and still lost track of which number
belonged to whom across 10,000 words. A much larger model has far more capacity to keep
many similar details apart over a long text. With the small model's default context window,
the start of the document does not even fit, which makes the result worse.

We saw the same pattern in a second test: answering 10 policy questions from the right
policy passages, the large model answered 8 correctly; the small model answered 4 and
refused the rest, because it could not apply the rule in the passage to the question.

A small local model still has a place: the data never leaves your network, it costs nothing
per question, and it works well for short, simple tasks, such as one CV at a time.

## How we design around these limits

- Give the model your own documents with each question, and make it cite them, so every
  answer can be checked against its source.
- Let it say "I don't know" when the sources do not answer, rather than guess.
- Keep exact rules, calculations and permissions in ordinary software, not in the model.
- Send one document at a time, or split long ones, instead of relying on a long input.
- Check its output against a fixed format, and test it on labelled examples before use.
- Keep a person in charge of every decision with real consequences.
