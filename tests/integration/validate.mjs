// node validate.mjs <dir with node_modules/gltf-validator> <file.glb>...
// Validates each file with the Khronos glTF validator, loading the files it
// points to; exits 1 if any has errors.
import fs from "fs";
import path from "path";
import { createRequire } from "module";

const [dir, ...files] = process.argv.slice(2);
const validator = createRequire(path.join(path.resolve(dir), "/"))("gltf-validator");
let bad = 0;
for (const f of files) {
  const report = await validator.validateBytes(new Uint8Array(fs.readFileSync(f)), {
    externalResourceFunction: (uri) =>
      Promise.resolve(new Uint8Array(fs.readFileSync(path.join(path.dirname(f), decodeURIComponent(uri))))),
  });
  if (report.issues.numErrors) {
    bad++;
    const first = report.issues.messages.filter((m) => m.severity === 0).slice(0, 3);
    console.log(f, first.map((m) => `${m.code} ${m.pointer || ""} ${m.message}`).join(" | "));
  }
}
process.exit(bad ? 1 : 0);
