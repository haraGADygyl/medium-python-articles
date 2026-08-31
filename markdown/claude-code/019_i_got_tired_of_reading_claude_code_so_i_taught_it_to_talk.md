# I Got Tired of Reading Claude Code, So I Taught It to Talk

#### A free, fully local text-to-speech plugin for Claude Code — no API key, no cloud, no per-word billing — and the design decisions that turned out to matter

**By Tihomir Manushev**

*Aug 31, 2026 · 7 min read*

---

Opus 5 writes well. That is the problem.

Ask it to explain a migration strategy and you get eight paragraphs that are all worth reading. Multiply that by forty exchanges a day and the bottleneck stops being the model and starts being your eyes. By six in the evening I was skimming replies I had specifically asked for, which is a strange way to use an expensive tool.

I wanted them read to me while I looked out the window. Everything I found wanted an API key, a per-character bill, and my code shipped to a vendor. So I built [**claude-speak**](https://github.com/haraGADygyl/claude-speak): a Claude Code plugin that reads replies aloud in a natural voice, entirely on the machine, for free.

---

### Why local, and why it is actually viable now

Every reply Claude Code produces contains your code, your file paths, your architecture. Streaming that to a vendor so it can be read back to you is a lot of exposure for a convenience feature — plus a key to rotate and a network round trip in front of every sentence.

Local used to mean `espeak-ng`, which sounds like a 1998 answering machine. That changed with [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) — an 82-million-parameter neural TTS model that runs on CPU, sounds genuinely natural, and fits in 338 MB. It is small enough to synthesize faster than real time on an ordinary laptop, which is the whole ballgame: you cannot wait two seconds for a model to load every time a reply lands. So the architecture is a daemon holding the model warm, and a hook that hands text to it and exits.

---

### Installing it

Both platforms install the same way — it is a Claude Code plugin, so the marketplace does the work:

```
/plugin marketplace add haraGADygyl/claude-speak
/plugin install claude-speak
```

Restart Claude Code, or run `/reload-plugins`. Then fetch the voice model once:

```
/claude-speak:speak install
```

Run that first one *inside* Claude Code rather than from a shell: the installer is what puts `claude-speak` on your PATH by linking it into `~/.local/bin`. Afterwards `claude-speak …` and `/claude-speak:speak …` are interchangeable. Claude Code namespaces every plugin command as `<plugin>:<skill>`, which is why the name is that long. There is no second restart — the Stop hook loaded with the plugin and uses the neural voice on the next reply.

The requirements are `python3` and an audio player, and that is the whole list:

| | Linux (Debian/Ubuntu) | macOS |
| --- | --- | --- |
| Audio player | `paplay`, `pw-play`, `aplay`, `ffplay` or `sox` | `afplay`, built in |
| If none present | installer offers `apt install pulseaudio-utils` | cannot happen |
| Virtualenv | `uv`, or `python3-venv` | `python3` is enough |
| Notifications | `notify-send`, optional | `osascript`, built in |
| Meeting guard | works, via `pactl` | unavailable — no `pactl` |
| Daemon | systemd user service, warm across reboots | on demand, stays up for the session |

Everything else lives in the plugin's own virtualenv. `kokoro-onnx` pulls in `espeakng-loader`, which ships its own `libespeak-ng` and voice data, so there is no system `espeak-ng` to install, and the CLI parses its own JSON, so there is no `jq`. Disk cost on my machine: 338 MB of model, 190 MB of virtualenv. The installer checks for a player *before* downloading any of it, and never installs system packages without asking — a text-to-speech plugin reaching for `sudo` unprompted is not a thing that should happen quietly.

macOS differs in one way: `afplay` plays files, not streams, so each sentence becomes a short temporary wav rather than one continuous pipe. Speech still starts after the first sentence, and `ffmpeg` or `sox` switches it to the streaming path if you want that. Before the model is installed, both platforms fall back to the system voice — `spd-say` or `say` — working immediately and sounding robotic until you run `install`.

---

### It does not talk unless you ask

This is the decision I expected to reverse and did not.

The obvious design is: reply finishes, voice starts. I shipped that, used it for two days, and then a terminal finished a long task during a client call and started narrating my code to the meeting. So the default is now **hold mode**: a reply finishes, you get a short ding and a desktop notification, and the text waits.

```bash
claude-speak play              # this terminal's project only
claude-speak play all          # everything, announced by project name
claude-speak pending           # what is waiting, * marks this terminal
```

`play` defaults to the directory you are standing in, so a terminal only reads back its own work. If you want it to just talk, `claude-speak hold off`.

The second layer is the **meeting guard**, which applies even with hold mode off. If anything is recording from your microphone, nothing is spoken and the ding is suppressed too. It watches live PulseAudio/PipeWire recording streams, so Zoom, Meet, Teams, Discord and browser calls all count, while playback streams are a different object entirely — it never trips on its own audio.

```bash
claude-speak guard test        # is it active right now, and what tripped it
```

macOS has no `pactl`, so the guard stays inert there and hold mode is the protection — a real gap, stated plainly rather than papered over.

---

### Using it day to day

Every command works from a shell as `claude-speak …` or inside Claude Code as `/claude-speak:speak …`.

```bash
claude-speak on                # read replies as they finish
claude-speak again             # missed the end? re-read the last reply
claude-speak stop              # silence, now
claude-speak speed 1.3         # 0.5 slow → 1.5 fast
claude-speak voice bm_george   # 54 voices, 8 languages
claude-speak audition          # play the 10 best English ones back to back
claude-speak read RFC.md       # read any file — same voice, same cleaning
git log -5 | claude-speak read -
```

**`again`** reads a saved copy rather than the transcript, so a repeat is the *same* words, and asking twice restarts it instead of queueing. **`read`** is what I use most outside of replies — it tells you the duration up front (`Reading README.md — about 4 minutes`), refuses binary files, and takes stdin.

With several sessions open, a reply from another project waits its turn and introduces itself — *"From api server. The migration finished…"* — instead of cutting off whatever is speaking. A reply from the *same* session does interrupt, because that one is stale by definition. Inside Claude Code, `! claude-speak stop` is instant: the `!` prefix skips the model round trip, which matters when you want silence *now*.

---

### It reads prose, not punctuation

Reading a reply verbatim is unbearable: sixty seconds of spoken Python syntax, then a URL character by character, then `###` announced as three number signs. So there is a cleaning stage between the hook and the voice, shared by replies and `read` alike. A real run of it:

````text
## Heading

Edit `src/api/parser.py:42` and see https://example.com/docs for and/or 24/7 rules.

```python
print("x")
```

Done.
````

becomes:

```
Heading. Edit parser.py line 42 and see link for and/or 24/7 rules. Code block. Done.
```

Code blocks become *"Code block"*, paths become *"parser.py line 42"*, URLs become *"link"*, markdown links keep their label, headings become sentences, and emoji and table pipes vanish.

This is the fragile part of the project and the source of every behavioural bug so far — note that `and/or` and `24/7` survived while the path collapsed. That is why a *relative* path is only recognized when it ends in a file extension, while a rooted one needs no such proof. It has a test suite that installs nothing and plays no audio:

```bash
python3 -m unittest discover tests
```

---

### The two things I got wrong

**Focus detection.** The design I wanted was for a held reply to start playing when you focus that terminal. I built it and abandoned it: GNOME Terminal runs every window and tab under a single process, so there is no telling which session you are looking at, and Claude Code rewrites the terminal title continuously, so a marker cannot be planted there either. On terminals that use one process per window — kitty, alacritty, foot — it would be feasible, and PRs are welcome.

**The plugin directory moves on every update.** Claude Code installs a plugin into a version-stamped path, so `${CLAUDE_PLUGIN_ROOT}` changes each time it updates. The PATH symlink and `ExecStart=` in the systemd unit both named that path absolutely. The second bit hard: a user who ran `claude plugin update` kept launching the *previous* release's daemon while the Stop hook ran the new code, so a fix shipped in the daemon never arrived and nothing looked broken. The repair now moves *toward* a pointer the hook writes on every reply, never toward whichever CLI happened to be calling. If your plugin writes anything outside its own directory, assume that directory will move and design the repair path first.

---

### Conclusion

claude-speak is a Stop hook, a Unix socket, and a warm 82M-parameter model — a small amount of machinery for a real change in how a workday feels. I now stand up and stretch while a design discussion is read to me, instead of hunching toward a wall of prose I asked for.

It is MIT-licensed and lives at [github.com/haraGADygyl/claude-speak](https://github.com/haraGADygyl/claude-speak). Two commands install it, one downloads the voice, and nothing leaves your machine at any point.

If you build something similar, the lesson worth stealing is not the model choice — it is that the correct default for anything that makes noise is silence. Every interesting decision here came from asking what happens when it speaks at the wrong moment.
