// Node side: parse stdin as JSON, as CSON (cson-parser), or as CoffeeScript.
// Prints {"ok": value} or {"error": message}; with --time, prints milliseconds.
const CSON = require("cson-parser");
const CoffeeScript = require("coffeescript");

const parsers = {
  json: (text) => JSON.parse(text),
  "cson-parser": (text) => CSON.parse(text),
  coffeescript: (text) => CoffeeScript.eval(text),
};
const [mode, timing] = process.argv.slice(2);
let text = "";
process.stdin.on("data", (d) => (text += d)).on("end", () => {
  const parse = parsers[mode];
  if (timing === "--time") {
    const started = process.hrtime.bigint();
    parse(text);
    console.log(Number(process.hrtime.bigint() - started) / 1e6);
    return;
  }
  try {
    // JSON.stringify would print Infinity as null; show it as what it is.
    const mark = (k, v) => (typeof v === "number" && !isFinite(v) ? `<${v}>` : v);
    console.log(JSON.stringify({ ok: parse(text) }, mark));
  } catch (e) {
    console.log(JSON.stringify({ error: `${e.name}: ${e.message.split("\n")[0]}` }));
  }
});
