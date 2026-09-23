# Jev: 20 Things You Can Build With a Model That Refuses to Write

#### TypeSafe AI's first model returns typed decisions with calibrated probabilities instead of text — here is what that is good for, and where it breaks

**By Tihomir Manushev**

*Sep 23, 2026 · 8 min read*

---

Most of the LLM calls in a production codebase are not asking for prose. They ask "which team gets this ticket?", "is this tool call safe?", "is this passage relevant?" — and then spend seconds generating tokens that a parser immediately throws away, keeping one word.

Jev, released in early access by TypeSafe AI on 15 September 2026, is built for exactly those calls and nothing else. It does not write. It takes a state and a set of typed questions, and returns answers with probabilities and a confidence score, typically in a few hundred milliseconds.

I do not have early access yet, so nothing below is my own measurement. Every number is attributed to whoever produced it — TypeSafe, or developers who have published their tests. What follows is a short introduction and twenty concrete things you can build with it.

---

### What Jev actually is

TypeSafe calls Jev a **System One model** — a name that echoes the fast, intuitive half of Kahneman's model of thinking. Its founder, Diogo Almeida, spent about four years at OpenAI working on RLHF, InstructGPT and ChatGPT, and the company announced a $40 million seed round led by DCVC alongside the launch.

The interface has three primitives, and every question you ask is one of them:

- **Choice** — pick one option from a set you define. You get the choice, a probability for every option, and a confidence.
- **Score** — place the state on an ordered scale you define. You get a fractional score, per-level probabilities, and a confidence.
- **Noul** — the probability, from 0 to 1, that a statement about the state is true.

Because the options are defined in advance, the model cannot answer outside them. TypeSafe describes this as eliminating type errors and hallucinated values; it does not eliminate *wrong* values, which is a distinction worth keeping in mind for everything that follows.

A request is a state plus named questions, and all the questions are answered in one parallel pass:

```json
{
  "state": {
    "return_note": "Kettle arrived with a cracked lid, box was fine. Want a replacement, not a refund."
  },
  "questions": {
    "reason": {
      "type": "choice",
      "instructions": "Why is the customer returning the item?",
      "criteria": {
        "damaged_in_transit": "Item broken or damaged on arrival",
        "defective": "Item stopped working or never worked",
        "changed_mind": "Customer no longer wants it"
      }
    },
    "wants_replacement": {
      "type": "noul",
      "instructions": "Does the customer ask for a replacement rather than a refund?"
    },
    "urgency": {
      "type": "score",
      "instructions": "How urgent is this return to resolve?",
      "criteria": ["Routine", "Customer inconvenienced", "Customer blocked or upset"]
    }
  }
}
```

The response carries one entry per question name, typed by primitive, so your code reads `answers["reason"]["choice"]` rather than parsing a paragraph.

Two properties make the rest of this article possible. First, **confidence is separate from probability**: TypeSafe trains the model with what it calls Reinforcement Learning for Calibrated Decisions (RLCD), so a confidence of 0.9 is meant to be right about nine times in ten. Second, **questions are nearly free to add**: TypeSafe's docs report that batching every question into one call was 12.2× cheaper and 10.0× faster than asking them one at a time, with no change in answers.

TypeSafe reports end-to-end latency of 70 to 500 milliseconds and a price of $0.042 per million input tokens, with output tokens free. Its headline figure — "193.6× faster, 444.6× cheaper" than frontier LLMs — comes from its own workflow evaluation, and the company itself describes those gains as the high end of what to expect.

---

### Routing and triage

**1. Support ticket triage.** Category, severity and "does it include reproduction steps?" become three questions in one call. Flavio Copes estimated about 300 tokens per ticket, which works out to roughly $1.26 per 100,000 tickets.

**2. Intent routing.** A Choice over handlers — database lookup, LLM, human — decides where a message goes before anything expensive runs. TypeSafe documents this as one of its four core patterns.

**3. Model routing.** Decide per prompt whether the cheap model is enough or the reasoning model is needed. LangChain uses Jev this way inside an agent harness, with the selection criteria written by the developer.

**4. Confidence-gated escalation.** Act automatically when confidence is high and send the rest to a large model or a person. Mariya Mansurova, testing Jev independently, found accuracy rose consistently in higher-confidence buckets — which is exactly the property this pattern depends on.

---

### Guardrails and verification

**5. Agent tool-call guardrails.** Judge every tool call before it executes. Firecrawl reports a guardrail that saw over 17,000 recorded calls, held 42 of them, was roughly 88% correct, and answered in about 250 ms per judgment.

**6. Shell command safety.** A single Choice — read-only, reversible, or destructive — in front of every command an agent runs. Cheap enough to apply to all of them rather than a sampled few.

**7. Prompt-injection screening.** Score pages an agent fetches before the agent reads them. In Firecrawl's test, a page carrying an injected instruction scored 0.99 and was dropped, while 80 legitimate passages passed.

**8. Citation and claim checking.** Ask whether a source actually supports a claim an LLM made. Firecrawl planted four bad citations; all four were caught at 0.99 confidence, and the four accurate ones verified at 0.93 or higher.

**9. Evaluations at scale.** Score every model output against a rubric instead of a sample. TypeSafe files this under "verify everything", and at these prices the evaluation stops being the bottleneck on how many outputs you can check.

---

### Search and data

**10. Search re-ranking.** Score keyword or embedding candidates for relevance before an agent sees them. Firecrawl reports top-1 accuracy rising from 5% to 18% and top-10 from 38% to 62%, for $0.0645 across 1,200 scoring calls.

**11. Filtering retrieved passages.** Keep or drop each chunk a retrieval step returns, so the LLM downstream reads less noise. TypeSafe publishes a cookbook for classifying RAG passages.

**12. Labeling a dataset.** Run one classification over every row. Flavio Copes labeled 1,018 research papers for $0.08, at a median of 256 ms; Firecrawl reports 777 judgments completed in 0.7 seconds.

**13. Features for predictive models.** Turn free text — complaint notes, call transcripts, incident reports — into probability columns a conventional model can train on. TypeSafe lists this as a primary use case.

---

### Business decisions

**14. Content moderation.** Apply your own written policy to chat, listings and comments, with the criteria in the request rather than baked into a vendor's classifier.

**15. Resume screening.** Score candidates against job criteria. Metaview, as cited by Flavio Copes, reports its hiring searches went from minutes to seconds — about 10× faster, at the same accuracy and lower cost.

**16. Lead scoring.** Several Score questions for fit with your ideal customer profile, combined with weights you control in code. This is TypeSafe's composite-scoring pattern: the model judges each dimension, your code decides what matters.

**17. Fraud and claims triage.** Flag suspicious characteristics in transactions or insurance claims and prioritise them for review. The model does the reading; the thresholds stay in your code.

**18. Code review risk scoring.** Security risk, complexity and bad practices per pull request, so reviewers look at the risky ones first.

**19. Log and alert severity.** Separate expected noise from user-facing failures, so a dashboard sorts by meaning rather than by log level.

---

### Real time

**20. Decisions inside a loop.** At a few hundred milliseconds, a model can sit inside a game tick, a robot controller or a browser agent. TypeSafe demonstrated a Doom bot making about ten queries a second, which Flavio Copes costed at roughly $7 an hour, and he reports browser automation choosing the next element in 153 ms per decision.

---

### Where it breaks

TypeSafe publishes a list of Jev's weaknesses, which is more than most model launches offer. It is **not a calculator**: it does not count reliably or do arithmetic. It **reads dates as text**, so comparisons between them are unreliable. Its accuracy **falls as the state fills with irrelevant content**, it answers the question you wrote rather than the one you meant, and indirect or contradictory instructions degrade it. Content written to steer it can move the answer. It takes text only, and it does not generate text at all.

The advice for each is consistent: keep math and dates in code, send only the fields a question needs, and turn anything you would have generated into a Choice over options.

Two caveats from outside TypeSafe matter. The headline benchmarks are the company's own, and score models by agreement with other LLMs' answers rather than a verified ground truth. And in Mariya Mansurova's independent test on the 77-intent banking77 dataset, Jev scored 79.0% against 83.9% and 86.2% for two OpenAI models — improving markedly when the task was cut to seven labels. The most-replied comment on the Hacker News launch thread summed up the rest: it cannot emit an invalid type, but it can still emit a wrong valid value.

---

### Conclusion

Jev is not an LLM replacement, and TypeSafe does not pitch it as one. It is a replacement for the part of your LLM usage that was always a classifier wearing a text generator's clothes: routing, gating, scoring, labeling and checking.

The pattern that makes most of the twenty ideas work is the same one. Batch every question you might need into a single call, act only when confidence clears a threshold you choose, and send the rest somewhere slower. Keep anything numeric in code.

Test it on your own data before trusting the multipliers. The independent results so far suggest the speed is real, the calibration is the best part, and the accuracy depends heavily on how many options you ask it to choose between.
