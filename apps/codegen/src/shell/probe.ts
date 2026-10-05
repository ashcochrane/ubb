/**
 * The one probe that asks whether the installed jq can run what a shell file
 * hands it, for both files that hand jq programs: the runnable file and the
 * verify script.
 *
 * A probe runs the construct the file is about to use and reads no version
 * string (ADR-0017 §1), so it is a program of the files' own form: read from
 * standard input, holding comments, handed a value as text (`--arg`) and one
 * as JSON (`--argjson`), and turning text to and from JSON. jq 1.5 is the
 * first that can: it brought `--argjson`, and `--slurpfile` with it, which a
 * file that reads a response also uses. jq 1.3 and 1.4 read a program from
 * standard input and accept its comments, and have neither flag, so a probe
 * of the first two alone passed on them and the file failed at its first
 * program after a unit of work had started — which #582's minimal image
 * found by running one. The same text whatever was declared: no tenant
 * content reaches it, it contacts nothing, and it reads and creates no file.
 */
import { SHELL_COMMENTS, SHELL_FILE } from "../catalogue.ts";
import { INDENT } from "./syntax.ts";

/** The probe, its command at `indent`, setting `status` to jq's status if
 * it fails. The program is indented one level in either file. */
export function jqProbe(indent: string, status: string): string[] {
  return [
    `${indent}jq --null-input --arg text 1 --argjson json 1 \\`,
    `${indent}${INDENT}--from-file /dev/stdin >/dev/null 2>&1 <<'${SHELL_FILE.heredoc}' || ${status}=$?`,
    ...SHELL_COMMENTS.preflightProgram.map((line) => `${INDENT}# ${line}`),
    `${INDENT}{"preflight": (($text | fromjson) + $json)} | tojson`,
    SHELL_FILE.heredoc,
  ];
}
