# Free Firefox's Memory Without Closing a Tab: about:unloads on Linux

#### One Stripe dashboard was holding 2.6 GB. A right-click gave it back, and on Linux Firefox never does that for you

**By Tihomir Manushev**

*Oct 31, 2026 · 5 min read*

---

My desktop runs Ubuntu 24.04 with 31 GiB of RAM and 8 GiB of swap, and it had been up for two weeks. It felt slow, though I had little open beyond a browser and a few terminals. `free` showed 19 GiB of RAM in use and swap nearly full. Firefox alone held 14.8 GiB across 43 processes.

I didn't want to close tabs. Most of them were projects in progress. Firefox can **unload** a tab instead: the tab stays in the tab strip, its memory goes back to the system, and clicking it loads the page again. Firefox can do this automatically when memory runs low, but on Linux that feature ships switched off.

Below, I find the heaviest tab, unload it, and measure what came back, all on Firefox 157 (snap).

---

### What Is Holding the Memory

Start with the system view:

```bash
free -m
```

`free` reports in MiB. `used` is memory taken by processes, and `available` is what the kernel can hand out without swapping:

```
       total   used   free  shared  buff/cache  available
Mem:   32009  19352   1121     207        8537      12656
Swap:   8191   7157   1034
```

Next, Firefox's share. Every tab, extension and helper runs in its own process, so you need a total. Adding up each process's resident size (**RSS**) overcounts, because pages shared between processes, like the libraries every content process loads, get counted once per process. **PSS** (proportional set size) splits each shared page among the processes using it, so the sum is honest. The kernel exposes it in `/proc/<pid>/smaps_rollup`:

```bash
for pid in $(pgrep -f '/firefox( |$)'); do
    grep '^Pss:' /proc/$pid/smaps_rollup
done | awk '{s+=$2; n++}
    END {printf "%d processes, %.0f MiB\n", n, s/1024}'
```

The loop finds every process started from a Firefox binary, reads its PSS in kB and sums it. On my machine, PSS came to 15,113 MiB, while the RSS sum claimed 18,731 MiB, overstating it by more than 3.5 GiB.

To find out which tabs those processes belong to, open **about:processes**. It lists every tab with its memory and CPU use, and clicking the Memory column header sorts the heaviest to the top. On my machine, the heaviest tab was a Stripe dashboard: its main process alone held 2,527,371 kB of PSS, second only to Firefox's own parent process.

---

### The Fix: Unload the Tab

There are two ways to unload a tab by hand.

**Right-click → Unload Tab.** Since Firefox 140 (June 2025), the tab context menu has an **Unload Tab** item. Select several tabs with Ctrl+click and it unloads all of them at once. This is the precise option: you pick the tab.

**about:unloads.** This page, in Firefox since 2021, shows the tabs in the order Firefox would unload them itself. Here is Stripe's row from the page, turned on its side to fit:

```
Priority       2
Host           dashboard.stripe.com
Last Accessed  10/31/2026, 4:31:12 PM
Weight         0
Sort Weight    12
Memory         2,644.641 MB
Processes      1988514 1989323 1989465 1989615
```

Priority 1 is unloaded first. A `-` means the tab can't be unloaded at all. **Weight** is the base penalty (pinned tabs get more, so they go later) and **Sort Weight** adds memory and process counts on top. **Processes** lists the process IDs the tab uses, and Stripe used four. The **Unload** button at the top always unloads the row ranked first, which was YouTube, so I used the right-click menu on the Stripe tab instead.

Because the page lists PIDs, you can check them from the shell:

```bash
for pid in 1988514 1989323 1989465 1989615; do
    grep '^Pss:' /proc/$pid/smaps_rollup
done
```

Before unloading, the four processes held 2,724,508 kB of PSS, almost all of it in the first.

**The automatic path.** The pref behind it is `browser.tabs.unloadOnLowMemory`. Firefox's default prefs file sets it to `true` only on Windows and macOS. I checked the copy shipped inside the snap, and it's `false` there. You can flip it in **about:config**, but look at the trigger first. On Linux, Firefox acts when `MemAvailable` falls to 5% of total RAM or under 200 MB, and swap use plays no part. On 31 GiB, that's about 1.5 GiB available. My machine had 12.4 GiB available with swap nearly full, so even with the pref on, nothing would have been unloaded.

---

### Before and After

I ran the same snapshot one minute apart, with the right-click in between. All four Stripe processes had exited:

```
=== watched processes (kB)
PID             PSS       SWAP
1988514      exited          -
1989323      exited          -
1989465      exited          -
1989615      exited          -
...
       total   used   free  shared  buff/cache  available
Mem:   32009  16835   3878     206        8539      15174
Swap:   8191   7155   1036
```

| | Before | After |
|---|---|---|
| RAM used | 19,352 MiB | 16,835 MiB |
| Available | 12,656 MiB | 15,174 MiB |
| Firefox PSS | 15,113 MiB | 12,359 MiB |
| Firefox processes | 43 | 39 |
| Swap used | 7,157 MiB | 7,155 MiB |

Unloading one tab gave back 2,518 MiB of RAM, close to the 2.6 GB Firefox's own page reported for it. Swap didn't move. I had used the Stripe tab about ten minutes earlier, so its memory was still in RAM. The 3.6 GiB of Firefox memory in swap belongs to tabs I hadn't touched in days. To drain swap, unload those old tabs, not the big recent ones.

---

### What Unloading Costs

An unloaded tab keeps its place in the strip, but no page runs behind it. Clicking it reloads the page from the network, so expect a delay, and logins that expired in the meantime will ask again. Firefox's session store usually restores scroll position and simple form fields, but state that lives only in the page's JavaScript, like a half-written message in a web app or an unsaved draft, can be lost. Save first.

Automatic unloading is more cautious than you are. Firefox's own code never picks a tab used in the last ten minutes, and it never touches private tabs or tabs that are playing media, in Picture-in-Picture or on a video call. Unloading by hand has none of those limits, so the cost is a reload and any unsaved state, and you're the one who decides when to pay it.

---

### Conclusion

On Linux, Firefox won't unload tabs by itself until available memory is almost gone, and swap doesn't count toward that. A machine can feel slow for days without ever reaching that point. Unloading by hand fills the gap: **about:processes** shows which tab is heavy, the right-click **Unload Tab** item releases it, and PSS from `/proc` shows how much came back. One tab returned 2.5 GiB here. When the desktop feels slow, check those two pages first and unload a heavy tab before you reach for a reboot.
