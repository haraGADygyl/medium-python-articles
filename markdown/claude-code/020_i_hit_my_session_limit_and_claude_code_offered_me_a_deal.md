# I Hit My Session Limit and Claude Code Offered Me a Deal

#### `/low-priority` trades latency for quota — and the 20-second retry loop, the 20-minute ceiling and the cool-off it can drop you into are all sitting in the binary

**By Tihomir Manushev**

*Sep 5, 2026 · 6 min read*

---

I was mid-task — article written, lab torn down, two repos staged and waiting for a `git push` — when the five-hour session limit landed. Normally that is the end of the afternoon. This time the terminal offered me something I had never seen:

```
/low-priority to continue now at lower priority · uses your weekly limit
```

I typed it. It kept working. Then I went looking for documentation and found none, so I read the binary instead: everything below comes either from my own terminal or from `grep` over `~/.local/share/claude/versions/2.1.261`, the bundled executable your `claude` symlink points at.

---

### The offer, and what it actually promises

Accepting prints one sentence, and every clause in it is load-bearing:

```
Continuing now at lower priority until your limit resets at 6pm. Your weekly
limit still applies, and responses may pause while waiting for spare capacity.
Run /low-priority to stop.
```

"Until your limit resets" is the important scope: this is a lease that expires when the five-hour window you just exhausted rolls over, not a permanent mode. "Your weekly limit still applies" is the clause people misread as hedging. It is literal — low-priority requests bill against your weekly budget at full price. You are not getting cheaper tokens.

What you are buying is the right to keep going *now*. The command's own description, from the command table in the bundle, is blunt about the shape of it:

```
Continue now at lower priority after reaching your session limit; run again to stop
```

Run it once to start, run it again to stop. It is a toggle, not a setting.

---

### It is a queue, not a discount

The mechanism is a retry loop with a server in charge of the timing. Anthropic ships a family of response headers for exactly this, and they are all visible as string literals in the binary:

```
anthropic-ratelimit-unified-slow-offer
anthropic-ratelimit-unified-slow-status
anthropic-ratelimit-unified-slow-retry-after
anthropic-ratelimit-unified-slow-max-wait
anthropic-ratelimit-unified-slow-budget-utilization
```

The first one is why the offer appeared at all — the server decides whether you get it. Once the mode is active, a request can come back two ways instead of served: a `429` carrying `slot_busy` means no low-priority slot is free, and an overload while the status header still reads `active` is classified `capacity_busy`. Either way the client does not fail the turn — it waits and re-dispatches, and you get a status line instead of an error:

```
Working at lower priority · waiting for capacity
 · next try in 18s · attempt 3 · esc to interrupt
```

The defaults behind that loop, straight out of the bundle: a **20-second** base retry, **±30% jitter** on each delay, and a hard ceiling of **20 minutes** of accumulated waiting for a single request. The server can override the first two via `slow-retry-after` and `slow-max-wait`, so treat those numbers as the floor of the client's own behaviour rather than a contract.

The jitter is the detail I appreciated most. Without it, every client that hit the limit at the same moment would retry on the same schedule and arrive back in a synchronized wave — the thundering herd that makes retry storms worse than the outage they follow.

---

### The three ways it ends

Low-priority mode does not just quietly persist. It terminates for one of a handful of reasons, and two of them are worth knowing before you rely on it.

**You stop it, or the window resets.** The clean cases. Switching accounts or resetting the conversation also ends it.

**You wait too long.** If a single request burns through the whole 20-minute ceiling, the client gives up on the mode entirely and starts a **cool-off** — 10 minutes by default, and it tells you so:

```
Lower-priority mode is taking a break until 2:35pm, after waiting too long
for spare capacity. Try /low-priority again then.
```

**You run out of low-priority allowance.** This is the one nobody expects, because it means the discount lane has its own budget:

```
You've used this week's lower-priority allowance. Lower-priority mode is
offered again after your weekly limit resets.
```

While the mode is running, the status line carries `Lower priority until {reset}` and, when the server has sent a budget-utilization header, a `{percent} allowance left` note beside it. If you see that number dropping, that is the allowance above, not your weekly quota.

---

### Why it is not in your `/help` output

Here is the gotcha, and it explains the confusion I found on every forum thread about this command. In the command table, `/low-priority` is declared with `isHidden: true` and:

```
isEnabled: () => gt() && (vF() || V0e())
```

In English: it is available only when the mode is already active — so you can turn it off — or when a remote flag is switched on for your account. I checked three consecutive versions on my disk, 2.1.259 through 2.1.261, and the code is byte-identically present in all of them. **The command does not arrive with an upgrade. It arrives when the server decides you can see it.** Typing it before then does nothing, which is exactly why people report it appearing "out of nowhere" on a version they have been running for a week.

The same table sets `supportsNonInteractive: false`. That is the practical limitation worth planning around: `/low-priority` is a TTY feature. A `claude -p` invocation in CI that hits the session limit cannot opt into it, so an unattended pipeline still stops dead. Anything you automate around usage limits has to assume the mode is unavailable.

One more caution. The user-visible strings — the label, the notice line, the wait banner, even the cool-off duration — are all remote-configurable, with the hardcoded copy acting only as a fallback. Do not build a hook that greps for `Working at lower priority`. That string is a default, not an interface.

---

### `/limit-reset`, the other half of the pair

Sitting immediately beside it in the same table is a second hidden command with the same shape and a very different trade:

```
Reset your session limit now and keep working; once a week, still counts
toward your weekly limit
```

`/limit-reset` clears the five-hour window outright — once per week, and the work still draws on your weekly budget. So the two commands answer the same problem from opposite directions. `/low-priority` gives you unlimited turns for the rest of the window at unpredictable latency. `/limit-reset` gives you full-speed turns immediately, and you can only do it once.

The heuristic I have settled on: if the remaining work is mechanical — pushing commits, updating a list, fixing lint — take the latency. If you are mid-debug and thinking at the speed of the replies, a 20-minute stall costs more than the wait would, and that is what the weekly reset is for.

---

### Conclusion

`/low-priority` is the first Claude Code feature I have seen that prices *your patience* instead of your tokens, and it is unusually honest about it: the message says "responses may pause", the client shows the countdown, and escape gets you out.

What is not honest is the discoverability. A hidden, server-gated, interactive-only command with three termination states and its own weekly allowance deserves a documentation page, not a one-line notice that appears the moment you are already blocked. Until it gets one: it costs full price against your weekly budget, it cannot help your CI, and one 20-minute stall takes the mode away for the next ten minutes.
