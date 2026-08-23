# Stop Re-Prompting Claude Code for the Same Format Every Turn

#### Output styles rewrite Claude Code's system prompt — here is what they change, what they quietly remove, and the one flag that decides both

**By Tihomir Manushev**

*Aug 23, 2026 · 6 min read*

---

There is a particular kind of friction that shows up once you have used Claude Code for a few months. You are not fighting the model on correctness anymore. You are fighting it on shape. Every architecture question comes back as three paragraphs of prose when you wanted a decision record. Every status check comes back with a preamble, a plan, and a recap of what it just said. So you start each message with the same twelve words: *answer as an ADR*, *skip the narration*, *just the diff*.

That instruction lives in a user message, so it competes with everything else in the conversation and it decays. Twenty turns later you are typing it again.

Output styles fix this at the layer where it belongs: they modify Claude Code's system prompt directly, before the conversation starts. Here is what they do to that prompt, how to write one worth keeping, and the four ways I have watched them fail silently.

---

### What an output style actually changes

Claude Code assembles a system prompt at session start. The bulk of it is software engineering instruction: how to scope a change, when to verify work, how much to comment, what to do before overwriting a file. An output style appends your instructions to the end of that prompt — and, by default, **removes the built-in engineering instructions entirely**.

That default is the single most important thing to internalize. A custom style is not additive unless you say so, and `keep-coding-instructions: true` is the frontmatter field that makes it additive again.

My rule: if Claude is still writing code and I am only changing how it *talks*, keep them. If the job is not software engineering at all — release notes, a data set, an interview drill — leave them out, because those instructions are dead weight and occasionally wrong for the task.

The neighbouring features overlap enough to be worth pinning down:

| Feature | Where it lands | Reach for it when |
|---|---|---|
| Output style | Replaces or extends the system prompt | You want a different voice or default format on *every* turn |
| `CLAUDE.md` | A user message injected after the system prompt | Claude needs to know your conventions and your codebase |
| `--append-system-prompt` | Appended to the system prompt, removes nothing | One invocation, usually a script or CI job |
| Agents | A separate system prompt, model, and tool set | A focused helper that runs and reports back |
| Skills | Instructions loaded on demand when relevant | A reusable workflow with steps |

The distinction that matters is *always* versus *sometimes*. A style is unconditional; a skill is conditional. If you are writing a style that applies to only one kind of task, you wanted a skill.

---

### The built-ins are worth trying before you write your own

Claude Code ships five styles. **Default** is the standard engineering prompt. Beyond that:

**Concise** leads with the result and drops preamble and narration while doing the same work underneath. It is the one I run day to day, and it does not withhold: ask for detail and you get it, and failing test output and destructive-action confirmations keep their full content. Needs v2.1.237 or later.

**Proactive** pushes Claude to act on reasonable assumptions instead of pausing on routine decisions. That is a prompt change, not a permissions change — your permission mode still decides what runs without approval.

**Explanatory** interleaves short insights about why an implementation went the way it did, and **Learning** goes further, leaving `TODO(human)` markers for you to fill in. Both are useful in an unfamiliar codebase and irritating in a familiar one.

Set one from `/config`, under **Output style**. The standalone `/output-style` command was deprecated in v2.1.73 and removed in v2.1.91, so if you have muscle memory for it — I did — it is gone. You can also write the setting by hand:

```json
{
  "outputStyle": "Concise"
}
```

---

### Writing one that earns its place

A custom style is a Markdown file: frontmatter, then instructions. Put it in `~/.claude/output-styles/` for everything you do, or `.claude/output-styles/` for one project. The filename becomes the style name unless `name` overrides it.

Here is one I built for a service where design discussions were supposed to land in the repo as decision records and never did, because reformatting the conversation afterwards was tedious enough that nobody bothered:

```markdown
---
name: ADR author
description: Answer architecture questions as a decision record
keep-coding-instructions: true
---

Answer every architecture or design question as an Architecture Decision Record.

Use exactly these sections, in order: Context, Decision, Consequences, Alternatives rejected.
Keep each section to at most three sentences. Name a concrete trade-off in Consequences.
```

Three things make it work. The format is a hard constraint, not a preference. The length is capped, because an unbounded "write an ADR" instruction produces an essay with headings. And it demands a named trade-off in Consequences, the section most likely to fill up with reassurance.

With the style active, a routine caching question produces this — real output, trimmed for width:

```
# Context
Rendered Markdown output is deterministic per input document and used across
requests; the working directory has no existing cache infrastructure to inspect.
The choice is between a shared Redis cache and a per-process local LRU.

# Decision
Use a local in-process LRU cache as the default, keyed on a content hash of the
source Markdown plus renderer version. Only introduce Redis if the service runs
multiple instances that need cache-hit consistency.

# Consequences
Local LRU gives lower latency and zero extra infrastructure, but each instance
keeps a cold, independent cache, so horizontal scaling multiplies redundant
render work. Redis avoids that duplication at the cost of a network hop per
lookup and an added operational dependency.

# Alternatives rejected
A two-tier cache was rejected for now as premature complexity. No caching at all
was rejected since Markdown rendering is pure.
```

That is paste-ready. No reformatting step, no forgetting the alternatives section.

---

### The four ways this fails silently

**The style is read once, at session start.** Change it mid-conversation and nothing happens until you `/clear` or open a new session. Every "my style isn't working" report I have chased ended here.

**A stale `settings.local.json` does nothing at the user level.** Auditing my own machine while writing this, I found `outputStyle: "Explanatory"` in `~/.claude/settings.local.json` while my sessions ran Concise from `~/.claude/settings.json`. The local variant is a *project*-level file; the copy in my home directory had been inert for weeks. Grep every file that might define the setting before you touch the style itself.

```bash
grep -rn outputStyle ~/.claude/settings*.json .claude/settings*.json
```

**Subagents do not inherit it.** A subagent runs its own system prompt, so your tuned voice evaporates the moment work is delegated. Forks are the exception, carrying the parent's full system prompt. For consistent delegated output, the instruction belongs in the agent definition, not the style.

**Dropping the coding instructions is easy to do by accident.** Omit `keep-coding-instructions` and you have quietly removed how Claude scopes changes and verifies work. If a styled session starts making sloppier edits than usual, check that field first.

---

### Conclusion

Output styles solve exactly one problem: you keep asking for the same shape of answer and you are tired of typing it. They are wrong for project conventions, which belong in `CLAUDE.md`; for one-off runs, which want `--append-system-prompt`; and for anything conditional, which wants a skill.

Start with the built-ins — Concise alone removed most of my re-prompting. When you write your own, set `keep-coding-instructions: true` unless you are genuinely leaving software engineering behind, constrain the format hard rather than suggesting it, and remember to `/clear`. A good style is one you stop noticing, because you stopped typing the same twelve words.
