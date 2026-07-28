# I Asked Claude Code Why It Writes So Many Comments — Then I Measured

#### Two of every five lines in the newest module are prose. One in thirty-three in the oldest. Same repo, same conventions file.

**By Tihomir Manushev**

*Jul 28, 2026 · 5 min read*

---

Six months into a TypeScript/NestJS backend where Claude Code writes most of the code, the comments started to stand out. Docblocks above every guard. Three lines of prose above a one-line condition. Explanations of things the type signature already said.

So I asked: do these comments help you navigate the codebase, or are they just more tokens for you to read?

The question assumes the answer is one or the other. It isn't. But the first half of it — *did the comments actually pile up?* — was checkable in a minute, and the number was worse than I suspected.

---

### The measurement

Comment lines as a share of non-blank lines, per feature module, excluding tests. Roughly sixty modules; nine representative ones:

| Module | Comment density | Built |
|---|---|---|
| `payouts` | **39%** | most recent |
| `withdrawals` | **36%** | most recent |
| `wallet` | 24% | recent |
| `ads` | 18% | recent |
| `feed` | 14% | mid |
| `topics` | 11% | mid |
| `auth` | 6% | early |
| `videos` | 5% | early |
| `users` | **3%** | earliest |

Same codebase, same primary author, same `CLAUDE.md`. A **tenfold drift**, invisible to everyone including the agent, because no single commit ever looked unreasonable.

```bash
files=$(find src/modules/payouts -name '*.ts' ! -name '*.spec.ts')
total=$(cat $files | grep -c '[^[:space:]]')
comment=$(cat $files | grep -cE '^\s*(//|\*|/\*)')
echo "$(( comment * 100 / total ))%"
```

The method is crude on purpose: any line starting with `//`, `*`, or `/*` counts, so JSDoc gets lumped in with inline notes. Run it on your own repo and expect a surprise — nobody tracks this.

---

### Why it drifted

Not "the model got chattier." Two mechanisms are visible in the data.

**The review ratchet.** The dense modules aren't just the newest — they absorbed the most review cycles. Payouts and withdrawals went through eight-plus rounds, because they were the first code paths that moved real money. The oldest module went through roughly none.

Every round works the same way. A reviewer finds a subtle bug. The fix is small and, once applied, looks arbitrary — an order that appears interchangeable, a condition that appears redundant. So a comment goes in to stop the next reader from "simplifying" it back into a bug. Comments get added at every round and removed at none. That ratchet compounds with review pressure, so the most scrutinized code — the code handling money — carries the most prose.

**Rationale displacement.** The project's `CLAUDE.md` bans rationale from the changelog: entries state *what* changed, and "the why belongs in the PR description and commit body." Good rule. But this project holds commits local until I approve a push, and I merge by hand — so in practice no PR description was being written at all. The ban evicted rationale from the changelog and pointed it at a destination that didn't exist.

Rationale doesn't evaporate when you ban it from one surface. It relocates to the nearest available one, and here that was the code. If your comment density is climbing, check whether some other part of your process recently got stricter.

---

### How an agent actually reads your code

A human opening an unfamiliar file reads it top to bottom, once. A comment three hundred lines above the function they care about still lands, because they passed through it on the way.

An agent greps for a symbol and reads a narrow window around each hit — fifty lines, sometimes the matched line and a handful either side. It may never see the top of the file. Three consequences follow, and each inverts the usual advice.

**Comments are read only if they're adjacent.** A well-written module-header docblock rarely enters the agent's context, because nothing it searches for matches it. The comment that changes agent behaviour is the one physically touching the line it landed on.

**Code-shaped text inside comments poisons search.** In the same session, I sent an Explore agent to inventory the codebase's HTTP routes. It came back flagging a stray route declaration inside a guard file as suspicious. It was a JSDoc usage example — a `@Controller('...')` line under an asterisk, showing how to apply the guard. Documentation to a human, indistinguishable from a real declaration to a grep-shaped reader, and a false positive that cost a verification round-trip.

**A stale comment is worse than no comment, and the agent can't tell.** A human reading `// this is always non-null` next to a nullable field feels friction and investigates. An agent is far more likely to take it at face value and propagate the error into whatever it writes next. Comments are load-bearing input to an agent in a way they aren't to a skeptical human, which makes their decay rate a bigger problem than their token cost.

---

### Derivability, not density

Density is the wrong metric. A module at 39% could be perfectly calibrated; a module at 3% could be under-documented in exactly the way that gets someone paged at 3am.

The metric that survives contact is **derivability**: a comment earns its place in inverse proportion to how easily its content could be recovered from somewhere else.

- **Code behaviour** → derivable. Restating it adds a second thing that can rot.
- **Change history** → derivable. `git log` and `git blame` are better at it.
- **Type shapes** → derivable. The DTO is right there.
- **Empirical behaviour of an external system** → **not derivable from anywhere.**
- **Which invariant a piece of code is load-bearing for** → **not derivable, and expensive to rediscover.**

The last two are worth almost any number of tokens, and worth *more* to an agent than to a human — a human can go run the thing and watch it fail. The agent can't call your payment provider or observe your production traffic.

Ours reports a bank account as an outstanding requirement on every freshly created account, because none has been given one yet. A guard that checked that flag before checking whether onboarding had started classified *"never started"* as *"bank details broken"* and sent people to a dead-end screen. The fix is two clauses swapped — it looks exactly like the kind of thing you'd simplify, and *why* is unrecoverable from the code, the types, or git. That comment should be long, and it should stay forever.

By the same test, the worst category is bug-history narration:

```ts
// Fields are mapped by hand instead of spreading the entity, so internal
// flags cannot leak onto the public response. The cost is that a new field
// on the view is silently dropped here unless someone adds it — which is
// what happened to `payoutAccountBlocked`, leaving the client unable to
// route a creator whose bank account had been disabled while the
// eligibility check refused every new withdrawal.
```

The first sentence is excellent: it explains why the mapping is verbose instead of a one-line spread, a "don't simplify this" warning nothing else records. Everything after it is a changelog entry that wandered into a source file. In six months it names a bug nobody remembers, in a file everyone still has to read — and it will never be deleted, because deleting comments isn't a task anyone gets assigned. If a sentence would be equally at home in a commit message, that's where it belongs.

---

### Fix the process before the prose

The first change isn't to the comments. It's to the destination the rationale was looking for and couldn't find:

```markdown
## Commit and changelog rules

- Changelog entries state *what* changed, one sentence, no rationale.
- Every commit body states *why*, even when the branch never becomes a PR.
- If a fix is non-obvious, the commit body must answer one question:
  what breaks if someone "simplifies" this later?
```

With a real destination in place, the rest is a budget rather than a ban: keep non-derivable external behaviour, load-bearing invariants, and "if you simplify this, X breaks" warnings; cut restatements of the code and bug-history narration. Then measure the percentage once a quarter, because the ratchet is invisible per-commit and obvious in aggregate.

---

### Conclusion

Having found two modules at 36–39%, the tempting move is to trim them. That would be a mistake made confidently. Those comments were written during review of code that moves money, and an unknown fraction encode invariants a blind pass would delete along with the padding — the reordered guard most of all, where the code is *designed* to look redundant. Deciding a comment is worthless means proving its content derivable, and that proof is real work.

"Too many comments" was the wrong diagnosis. **Too many *derivable* comments** was the right one, and the two have very different remedies: one is a trim, the other is a change to where rationale is allowed to live.
