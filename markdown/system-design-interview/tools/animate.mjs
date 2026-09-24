// Animated GIF export for Mermaid diagrams.
//
//   node animate.mjs <input.mmd> <output.gif>
//
// Flowcharts: edges declared with `e1@{ animate: true }` get "marching ants" —
// the dash offset is stepped frame by frame over exactly one dash period, so the
// loop is seamless. Sequence diagrams: messages and notes are revealed one step
// at a time, top to bottom, then the finished diagram holds before looping.
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME || "/usr/bin/google-chrome";
const SCALE = Number(process.env.GIF_SCALE || 2);
const ANT_FRAMES = 14;          // one frame per pixel of a 9+5 dash period
const ANT_FPS = 14;             // one period per second
const STEP_SECONDS = 1.1;       // sequence diagrams: time per revealed step
const HOLD_SECONDS = 3.0;       // sequence diagrams: finished diagram hold

const [input, output] = process.argv.slice(2).map((p) => resolve(p));
if (!input || !output) {
  console.error("usage: node animate.mjs <input.mmd> <output.gif>");
  process.exit(1);
}

const work = mkdtempSync(join(tmpdir(), "mmd-gif-"));
const svgPath = join(work, "diagram.svg");
const puppeteerConfig = join(work, "pconf.json");
writeFileSync(puppeteerConfig, JSON.stringify({ args: ["--no-sandbox"] }));
execFileSync("npx", ["-y", "@mermaid-js/mermaid-cli", "-i", input, "-o", svgPath,
  "-b", "white", "-p", puppeteerConfig], { stdio: "ignore" });

const browser = await puppeteer.launch({
  executablePath: CHROME,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});
const page = await browser.newPage();
await page.setContent(`<!doctype html><html><body style="margin:0;background:#fff">
  ${readFileSync(svgPath, "utf8")}</body></html>`);
const box = await page.evaluate(() => {
  const svg = document.querySelector("svg");
  // Mermaid emits width="100%"; pin the SVG to its own viewBox size instead,
  // or it stretches to whatever width the page happens to have.
  const [, , vbWidth, vbHeight] = svg.getAttribute("viewBox").split(/[ ,]+/)
    .map(Number);
  svg.setAttribute("width", vbWidth);
  svg.setAttribute("height", vbHeight);
  svg.style.maxWidth = "none";
  const r = svg.getBoundingClientRect();
  return { width: Math.ceil(r.width), height: Math.ceil(r.height),
           kind: svg.getAttribute("aria-roledescription") };
});
await page.setViewport({ width: box.width, height: box.height,
                         deviceScaleFactor: SCALE });

const frames = [];
async function shoot(seconds) {
  const file = join(work, `f${String(frames.length).padStart(3, "0")}.png`);
  await page.screenshot({ path: file, omitBackground: false });
  frames.push({ file, seconds });
}

if (box.kind && box.kind.startsWith("flowchart")) {
  const period = await page.evaluate(() => {
    const edges = [...document.querySelectorAll(
      "path[class*='edge-animation']")];
    window.__edges = edges;
    if (!edges.length) return 0;
    const dash = (getComputedStyle(edges[0]).strokeDasharray || "9, 5")
      .split(/[ ,]+/).map(parseFloat).filter((n) => !Number.isNaN(n));
    // A 1px dashed edge carries about a third less ink than the solid edges
    // around it and reads as washed out; thicken the dash and lengthen it
    // within the same 14px period so the loop timing is unchanged.
    for (const e of edges) {
      e.style.animation = "none";
      e.style.strokeWidth = "2px";
      e.style.strokeDasharray = "10 4";
      e.style.setProperty("stroke-dasharray", "10 4", "important");
    }
    return 14;
  });
  if (!period) throw new Error("no animated edges: add e1@{ animate: true }");
  for (let i = 0; i < ANT_FRAMES; i++) {
    const offset = period * (1 - i / ANT_FRAMES);
    await page.evaluate((o) => {
      for (const e of window.__edges) e.style.strokeDashoffset = String(o);
    }, offset);
    await shoot(1 / ANT_FPS);
  }
} else if (box.kind === "sequence") {
  const steps = await page.evaluate(() => {
    const top = (el) => el.getBoundingClientRect().top;
    const lines = [...document.querySelectorAll(
      "[class^=messageLine], [class*=' messageLine']")];
    const notes = [...document.querySelectorAll("rect.note")];
    const events = [
      ...lines.map((el) => ({ y: top(el), els: [el] })),
      ...notes.map((el) => ({ y: top(el), els: [el], note: el })),
    ].sort((a, b) => a.y - b.y);
    // Message labels and step numbers belong to the line just below them;
    // note text belongs to the note rectangle that contains it.
    const attach = (el) => {
      const r = el.getBoundingClientRect();
      const host = events.find((ev) => ev.note &&
        r.top >= ev.note.getBoundingClientRect().top - 2 &&
        r.bottom <= ev.note.getBoundingClientRect().bottom + 2);
      if (host) return host.els.push(el);
      const below = events.filter((ev) => !ev.note && ev.y >= r.top - 4);
      (below[0] || events[events.length - 1]).els.push(el);
    };
    // Labels, note text and autonumber digits — plus the circle each digit
    // sits in, which Mermaid draws as a zero-length, unclassed <line> whose
    // only job is to carry the sequencenumber marker.
    document.querySelectorAll(
      ".messageText, .noteText, .sequenceNumber, " +
      "line[marker-start*='sequencenumber']").forEach(attach);
    // A `rect` highlight block belongs with the first step drawn inside it, so
    // it appears together with its contents rather than as an empty band.
    document.querySelectorAll("rect.rect").forEach((el) => {
      const blockTop = top(el);
      const first = events.find((ev) => ev.y >= blockTop - 1);
      (first || events[events.length - 1]).els.push(el);
    });
    window.__events = events.map((ev) => ev.els);
    return events.length;
  });
  for (let shown = 0; shown <= steps; shown++) {
    await page.evaluate((n) => {
      window.__events.forEach((els, i) =>
        els.forEach((el) => { el.style.opacity = i < n ? "1" : "0"; }));
    }, shown);
    await shoot(shown === steps ? HOLD_SECONDS : STEP_SECONDS);
  }
} else {
  throw new Error(`unsupported diagram type: ${box.kind}`);
}
await browser.close();

// Evenly timed frames (marching ants) go in at a fixed frame rate so the loop
// has no repeated frame; stepped frames use the concat demuxer for durations,
// which needs the last file listed twice to honour its duration.
const list = join(work, "frames.txt");
writeFileSync(list, frames.map((f) => `file '${f.file}'\nduration ${f.seconds}`)
  .join("\n") + `\nfile '${frames[frames.length - 1].file}'\n`);
const evenlyTimed = frames.every((f) => f.seconds === frames[0].seconds);
const source = evenlyTimed
  ? ["-framerate", String(1 / frames[0].seconds), "-i", join(work, "f%03d.png")]
  : ["-f", "concat", "-safe", "0", "-i", list];
const PALETTE = process.env.GIF_PALETTE ||
  "palettegen=max_colors=256:stats_mode=full";
const DITHER = process.env.GIF_DITHER || "paletteuse=dither=none:diff_mode=rectangle";
if (process.env.GIF_KEEP_FRAMES) {
  execFileSync("cp", ["-r", work, process.env.GIF_KEEP_FRAMES]);
}
execFileSync("ffmpeg", ["-y", "-loglevel", "error", ...source, "-vf",
  `split[a][b];[a]${PALETTE}[p];[b][p]${DITHER}`,
  "-loop", "0", output]);
rmSync(work, { recursive: true, force: true });
console.log(`${box.kind}: ${frames.length} frames -> ${output}`);
