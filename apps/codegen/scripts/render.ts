/**
 * `render`, from another process: a Blueprint in on standard input, the files
 * it renders out on standard output, as one JSON array (#582).
 *
 * The renderer is one pure function and its lint holds it to that: nothing
 * under `src/` reads a stream, the environment or the filesystem. Whatever
 * hands it a Blueprint from outside this package therefore lives outside
 * `src/`, here. Node runs it straight from the TypeScript, as the package has
 * no build step and its syntax is erasable.
 *
 * It decides nothing and adds nothing: what it prints is what `render`
 * returned, file for file and in order, and `tests/render-script.test.ts`
 * holds it to that for every committed Blueprint. A document `render`
 * refuses fails the process, with the refusal on standard error and nothing
 * on standard output.
 *
 * The execution suite at the git root (`tests/code_builder_execution`) is
 * what calls it. That suite writes the files to disk itself and takes a
 * checksum of each as it writes it, so nothing between this script and the
 * running code can change a rendered file unnoticed.
 *
 *     node --experimental-strip-types apps/codegen/scripts/render.ts < blueprint.json
 */
import { readFileSync } from "node:fs";

import { render } from "../src/index.ts";

process.stdout.write(JSON.stringify(render(JSON.parse(readFileSync(0, "utf-8")))));
