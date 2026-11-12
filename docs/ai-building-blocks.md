# AI building blocks

A map of the parts an AI feature is built from, beyond "call a model". For each: what it
is, when to use it, and what it costs or risks. Start from the simplest design that works:
a model, a good prompt and your own data in the context. Add a block only when a measured
problem needs it.

```
 user ──► app ──► AI gateway ──► model(s)
           │                        ▲
           ├─ context management ───┤  (what goes into each request)
           │    ├─ retrieved documents (RAG)
           │    ├─ memory
           │    └─ skills
           └─ agents: one or several, calling tools
```

## Multimodal input

- **What:** models that take images, audio, scanned pages or video as input, not only text.
  The same chat request carries a picture next to the question.
- **Use when:** the information only exists as an image or a recording: scanned invoices,
  photos of damaged parcels, voice notes. Text that is already digital should be sent as
  text.
- **Cost and risk:** an image costs many tokens and is slower than text; small local models
  read images poorly. Errors in reading numbers are silent, so validate extracted values
  (our invoice model checks that the line amounts add up to the subtotal, and subtotal plus
  tax to the total).

## Fine-tuning

- **What:** further training of an existing model on your own examples, which changes its
  weights. It teaches a style, a format or a narrow task; it is a poor way to teach facts.
- **Use when:** a prompt with examples cannot get a consistent format or tone, the task is
  narrow and repeated at high volume, and you have hundreds to thousands of checked
  examples. Facts that change belong in retrieval instead.
- **Cost and risk:** labelled data, training runs, and a new evaluation every time the base
  model changes. The tuned model can lose general ability, can memorise and leak training
  data, and is tied to one provider or base model.

## Multi-agent systems

- **What:** several model "agents", each with its own instructions and tools, that hand work
  to each other or are coordinated by a supervisor agent. For example, one plans, one
  searches, one checks the result.
- **Use when:** a task really splits into parts that need different tools or permissions,
  or parts that can run in parallel. A single agent with good tools is the default.
- **Cost and risk:** many more model calls, so more tokens, latency and failure points.
  Errors compound from agent to agent and loops are possible, so set step and budget
  limits. Harder to test and to explain afterwards. Every tool with a side effect needs
  least privilege and human approval.

## Memory

- **What:** information kept between requests or conversations, because the model itself
  remembers nothing. Short-term memory is the conversation so far; long-term memory is
  stored facts or summaries that are retrieved later.
- **Use when:** users return and expect continuity, such as preferences or an ongoing case.
  Keep it out of one-off tasks such as extraction, where it only adds noise.
- **Cost and risk:** stored memory is personal data: it needs consent, retention limits,
  deletion on request and strict separation per user. Wrong or outdated memories are
  repeated with confidence. Memory text can carry injected instructions.

## Context management

- **What:** choosing what goes into each request within the model's context window:
  instructions, retrieved passages, history and tool results. Everything must fit, and the
  most relevant part must not get lost.
- **Use when:** always, in every feature. It becomes critical with long documents, long
  conversations and agents that collect tool output.
- **Cost and risk:** every token costs money and time. Overfull contexts are silently cut or
  read unevenly (our 2B model lost track of 20 CVs even when they fitted). Too little
  context gives incomplete answers (our phishing question missed a cross-referenced rule).
  Count tokens with the deployed model's tokenizer; languages differ by up to three times.

## AI gateway

- **What:** a service between your applications and the model providers. All model traffic
  goes through it, so keys, routing, fallback, rate limits, logging and cost tracking live
  in one place.
- **Use when:** several applications or teams use models, you need a budget per user or
  team, provider switching without code changes, or one audit trail. For one service, a
  single client module (our `llm_client`) does the same job.
- **Cost and risk:** one more component to run and secure, and a single point of failure;
  it adds latency. It sees every prompt and answer, so it holds sensitive data and must not
  log personal data.

## Skills

- **What:** packaged instructions, and sometimes scripts or reference files, that an agent
  loads only when a task needs them. They teach an agent a procedure, such as "how we write
  a release note", without filling every request's context.
- **Use when:** an agent handles many kinds of task, each with its own procedure, and putting
  all the procedures into one prompt would be too long or would confuse it.
- **Cost and risk:** a skill is code and instructions the agent will follow, so treat it like
  a dependency: review it, version it, and only install skills from trusted sources. A
  skill with scripts can do anything those scripts can do. Overlapping skills make the
  agent's choice unpredictable.
