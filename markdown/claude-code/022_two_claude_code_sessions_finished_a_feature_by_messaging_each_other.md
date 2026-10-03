# Two Claude Code Sessions Finished a Feature by Messaging Each Other

#### I broke an API contract in one session, told the other session mid-task, and got a test result back, plus the two cases where a message doesn't arrive when you think it does

**By Tihomir Manushev**

*Oct 3, 2026 · 6 min read*

---

Running two Claude Code sessions in parallel, one on the backend and one on the client, has always had a gap between them. When the backend session changes the payload, the client session doesn't know. You find out when its tests go green against the old contract, and then you copy-paste the change from one terminal into the other.

Since v2.1.224, sessions on the same machine can message each other. One session finds the others with a tool called `ListAgents` and sends plain text with `SendMessage`. You never call either tool yourself; you tell Claude what the other session needs to know.

I tested it on Claude Code 2.1.288 with a small tipping service. My interactive session played the backend, and headless `claude -p` sessions built the client. Every output below is from those runs.

---

### What a message is, and what it can't do

A message is text that one Claude writes to another. It is never the sender's conversation history and never its files. Between sessions on the same machine it travels over a per-session Unix socket, not through Anthropic's servers.

The receiving Claude is told the text came from another session, not from you. That limits what the message can do. It can't answer a pending permission prompt, it can't get the receiver to edit permissions or `CLAUDE.md`, and a slash command inside it arrives as inert text. If acting on the message needs a permission the receiving session doesn't have, you get the normal prompt.

---

### Starting a worker that can be reached

The client worker was an ordinary headless session with a name, so I could address it:

```bash
claude -p "Build the terminal client for tipjar. Write client.py with format_tips(...) and totals_by_currency(...), write test_client.py, run the tests and make them pass." \
  --name frontend-client \
  --permission-mode acceptEdits \
  --allowedTools "Bash(python3 *)" \
  --settings '{"crossSessionInbound":"accept"}' \
  --output-format stream-json --verbose > worker.jsonl
```

`--name` sets the address. `crossSessionInbound` set to `accept` is the documented way to let a `-p` worker take messages unattended (more on the default below). A few seconds later, `ListAgents` in my session showed it:

```
This session is articles-writer-f5 [1756e9] — the name other sessions use to message it

Peer sessions (18):
  frontend-client [3bb21f]  ·  interactive  ·  busy  ·  started 8s ago
  ... 17 more of my sessions, local and Remote Control ...
```

That listing is the first thing to know about the feature. It shows *every* session you have running, so Claude can see the names of all your other projects. I trimmed the other 17 rows before publishing.

---

### The handoff

While the worker was writing its client, I changed the backend: `amount`, a float, became `amount_cents`, an integer, committed as `d5fbe18`. Then I asked Claude to tell the client session. This is the message it sent:

```
Breaking change in the tips payload: `amount` (float) is now `amount_cents` (int).
I just committed api v2. Each tip is now {"id", "from", "amount_cents", "currency"},
e.g. {"id": 1, "from": "ana", "amount_cents": 450, "currency": "EUR"}; CONTRACT.md
is updated. Please format from cents (450 -> "4.50") rather than re-parsing floats,
and re-run your tests against the live api.get_tips_payload(). When you're done,
reply to me with the test result.
```

The reply arrived in my session about half a minute later:

```
Client now uses api v2 (amount_cents), and all 5 tests pass against the live
api.get_tips_payload() at d5fbe18. client.py formats from integer cents with divmod
(450 -> "4.50"), with no float parsing, and sums totals as ints. ...
client.py and test_client.py are not committed yet.
```

The worker checked my commit and `CONTRACT.md` before touching anything. Its log shows `git log` and `cat CONTRACT.md api.py` as the first commands after the message. I ran `python3 -m unittest` myself (5 tests, OK) rather than taking the reply's word for it, which is the same standard you'd apply to any summary.

---

### When the message actually lands

The docs say the receiver reads a message between tool calls during an active turn. That's true, but whether "between tool calls" happens in time depends on where the worker is.

In the first run, the worker's stream log shows it **finished its turn first**, with a float-based client using `Decimal(str(amount))`. My message had arrived after its last tool call. The headless process didn't exit, though. The queued message started a second turn in the same process, and the worker redid the formatting for cents. That's correct, but you pay for the work twice.

For a second run, I timestamped the worker's stream and gave it a longer, three-step task:

```
   4.5s tool_use Bash: ls -la && cat client.py test_client.py CONTRACT.md ...
   9.1s tool_use Bash: cat api.py
         <- message sent at 9.6s
   9.9s text: 'Step 1: the filter.'
  16.3s tool_use Write: client.py
  17.8s tool_use Bash: python3 -m unittest -v ...
  17.9s command_lifecycle started          <- message delivered
  ...
  35.2s tool_use Bash: ... grep -n "from'\]\|\"from\"\|'from' ...
  39.1s tool_use SendMessage: (reply to my session)
  46.3s RESULT turns=12
```

The message waited 8.3 seconds while the worker generated a whole file. It was delivered at the next tool round, then acted on within the same turn. A message is a note slipped under the door, not a phone call. Send contract changes early, and expect them to be read when the receiver next pauses.

---

### Held, refused, and a coincidence that looks like delivery

The third worker ran with `crossSessionInbound` set to `hold`. My send succeeded, and then my session received this:

```
[Cross-session delivery notice] Your message to another session was held for the
recipient user's approval ... Not delivered to that session's Claude yet; its user
must approve first.
```

The worker's log recorded a `peer_message_hold` event with `cause: explicit-setting`, and a second event, `state: dropped`, `outcome: discarded`, when the session ended. A held message never reached its Claude. About five minutes after the send, my session got a second notice, "not approved before expiry", so a sender hears about a held message twice: once when it is held and once when it expires.

There's a trap here. My message asked the worker to mention negative amounts, and its final summary said the suite "does not cover negative amounts". It noticed that on its own, by reading the code. The word "refund", which only my message contained, appears nowhere in its log. If you judge delivery by the reply's content, you'll get this wrong. Judge it by the delivery notice and by whether a reply comes back.

When no value is set, the default depends on permission mode. Sessions that bypass permission prompts form one class, and every other session forms the other. A message that crosses between the two classes is held for approval, and a `-p` worker can't show an approval dialog, so the held message expires after five minutes by default. That's why the worker command above sets `accept` explicitly.

To turn the feature off for a project, deny both tools and refuse inbound messages:

```json
{
  "permissions": {
    "deny": ["SendMessage", "ListAgents"]
  },
  "crossSessionInbound": "refuse"
}
```

---

### What I'd do differently next time

**Name every session you plan to message.** Generated names collide, and then the address needs a `[ref]`. `--name` on the command line and `/rename` inside a session both fix that.

**Ask for an idle notice instead of polling.** I subscribed with `notify_when_idle`, and one line came back when the first worker went idle: the time it finished and a one-sentence status. It cost the worker nothing.

**Put the content in the text.** The receiver reads `@path` literally and nothing gets attached, so paste the schema itself.

**Don't route around a denial.** Claude is instructed never to ask another session to do something its own session was denied. That's worth keeping as a rule for yourself too.

---

### Conclusion

Cross-session messaging closes the gap between parallel sessions with the smallest possible primitive: one Claude writes a note, and another reads it at its next tool round. Within that limit it works well. The worker verified my commit before trusting me and replied with a test count. The limit is timing, not trust: a message sent after the worker's last tool call costs you a second pass. Send the change before the other session starts building on the old contract, and check delivery from the notices, not from what the reply happens to say.
