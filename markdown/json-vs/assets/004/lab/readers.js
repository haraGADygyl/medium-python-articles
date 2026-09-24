// Node side: JSON.parse, the json5 reference parser, and VS Code's JSONC parser.
const fs = require("fs");
const JSON5 = require("json5");
const jsonc = require("jsonc-parser");

const text = fs.readFileSync(process.argv[2], "utf8");
const out = {};

try { out["Node JSON.parse"] = JSON.parse(text); }
catch (e) { out["Node JSON.parse"] = `${e.name}: ${e.message.split("\n")[0]}`; }

out["npm json5 " + require("json5/package.json").version] = JSON5.parse(text);

const errors = [];
const value = jsonc.parse(text, errors, { allowTrailingComma: true });
out["npm jsonc-parser " + require("jsonc-parser/package.json").version] =
  errors.length
    ? `${errors.length} errors, first: ${jsonc.printParseErrorCode(errors[0].error)}` +
      ` at offset ${errors[0].offset}`
    : value;

console.log(JSON.stringify(out, (k, v) => (v === Infinity ? "<Infinity>" : v)));
