// Prints range-parser's answer for each [size, header, combine] JSON line on stdin.
// Usage: node range_parser_oracle.js <path to range-parser's index.js>
"use strict";
const path = require("path");
const fs = require("fs");
const rangeParser = require(path.resolve(process.argv[2]));
const lines = fs.readFileSync(0, "utf8").split("\n").filter(Boolean);
const out = lines.map((line) => {
  const [size, header, combine] = JSON.parse(line);
  const result = rangeParser(size, header, { combine: combine });
  if (typeof result === "number") return JSON.stringify(result);
  return JSON.stringify({ type: result.type, ranges: result.map((r) => [r.start, r.end]) });
});
process.stdout.write(out.join("\n") + "\n");
