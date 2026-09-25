// Reference TopoJSON implementation, driven from Python over stdin/stdout.
//   node topo.js encode <quantization>     GeoJSON -> TopoJSON (0 = none)
//   node topo.js decode                     TopoJSON -> GeoJSON
//   node topo.js simplify <keep-fraction>   TopoJSON -> simplified GeoJSON
//   node topo.js timing <quantization>      encode/decode ms, best of 5
const { topology } = require("topojson-server");
const { feature, mesh } = require("topojson-client");
const { presimplify, quantile, simplify } = require("topojson-simplify");

const [mode, arg] = process.argv.slice(2);
let text = "";
process.stdin.on("data", (d) => (text += d)).on("end", () => {
  const input = JSON.parse(text);
  const objectName = (topo) => Object.keys(topo.objects)[0];
  if (mode === "encode") {
    const q = Number(arg);
    const topo = q ? topology({ cells: input }, q) : topology({ cells: input });
    process.stdout.write(JSON.stringify(topo));
  } else if (mode === "decode") {
    process.stdout.write(JSON.stringify(feature(input, input.objects[objectName(input)])));
  } else if (mode === "simplify") {
    const pre = presimplify(input);
    const kept = simplify(pre, quantile(pre, Number(arg)));
    process.stdout.write(JSON.stringify(feature(kept, kept.objects[objectName(kept)])));
  } else if (mode === "borders") {
    const inner = mesh(input, input.objects[objectName(input)], (a, b) => a !== b);
    process.stdout.write(JSON.stringify(inner));
  } else if (mode === "timing") {
    const q = Number(arg);
    const best = (fn) => {
      let fastest = Infinity, out;
      for (let i = 0; i < 5; i++) {
        const s = process.hrtime.bigint();
        out = fn();
        fastest = Math.min(fastest, Number(process.hrtime.bigint() - s) / 1e6);
      }
      return [fastest, out];
    };
    const [encMs, topo] = best(() => topology({ cells: input }, q));
    const [decMs] = best(() => feature(topo, topo.objects.cells));
    const [parseMs] = best(() => JSON.parse(text));
    process.stdout.write(JSON.stringify({ encMs, decMs, parseMs }));
  }
});
