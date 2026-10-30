# Screenshots for 000 — Firefox tab unloading

Save PNGs here with these exact names. Take the "before" shots first, then unload
tabs, then take the "after" shot. Crop out or blur anything private (tab titles,
URLs, account names) before saving.

| File | What to capture |
| --- | --- |
| `01-about-processes-before.png` | `about:processes`, sorted by Memory (click the column header), heaviest tabs at the top |
| `02-about-unloads.png` | `about:unloads` with the Unload button and the top rows: Priority, Host, Last Accessed, Memory |
| `03-unload-tab-menu.png` | Right-click on a tab, context menu open with **Unload Tab** visible (ideally with several tabs selected) |
| `04-about-config-unload-pref.png` | `about:config`, search `browser.tabs.unloadOnLowMemory`, showing its default `false` |
| `05-about-processes-after.png` | `about:processes` again, sorted by Memory, after unloading |

Optional:

| File | What to capture |
| --- | --- |
| `06-unloaded-tab-strip.png` | The tab strip showing unloaded tabs still in place (they look dimmed) |

Firefox's own window chrome is fine to include; the system's numbers come from the
measurement script in `../lab/`, not from screenshots.
