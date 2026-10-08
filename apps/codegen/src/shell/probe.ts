/**
 * The probe that asks whether the installed jq can run what a shell file
 * hands it — derived from that file's own programs.
 *
 * A probe runs the construct the file is about to use and reads no version
 * string (ADR-0017 §1). So it asks for exactly what the file's programs ask
 * for, and nothing else (owner's review of #602): preflight succeeds if and
 * only if this jq can run this file's programs. It is a program of their own
 * form — read from standard input, holding comments — that passes each
 * option they pass, uses each keyword form they use, and names each function
 * they call. The functions are named inside a branch that is never taken, so
 * jq must resolve every one of them to compile the probe, and runs none.
 *
 * What a file's programs ask for is read off the programs as rendered
 * (`jqNeedsOf`), and every option, function and keyword is held to the closed
 * tables below: a program that used one they do not list would refuse to
 * render rather than be probed for less than it needs.
 *
 * Why this matters, and how it was found: the first probe asked only for a
 * program read from standard input that holds comments. jq 1.3 and 1.4 do
 * both and have no `--argjson` or `--slurpfile` (1.5 brought both), so a
 * file passed preflight on them, started a unit of work and failed at its
 * first program — which #582's minimal image found by running one.
 *
 * The probe contacts nothing, reads no file but `/dev/null` and creates
 * nothing, and no declared name reaches it: what varies between files is
 * which of the tables' entries their programs use.
 */
import { SHELL_COMMENTS, SHELL_FILE } from "../catalogue.ts";
import { INDENT } from "./syntax.ts";

/** What a file's jq programs ask of the jq that runs them. */
export interface JqNeeds {
  readonly options: readonly string[];
  readonly forms: readonly string[];
  readonly functions: readonly string[];
}

/** What the probe passes itself, so a program passing it asks nothing more:
 * every program reads its program from standard input, and every one but
 * the read of a response as text (#583), which names the file it reads, has
 * no input of its own. */
const ALWAYS = ["--null-input", "--from-file"];

/** Each option a program may pass, how the probe passes it, and how the
 * probe reads what it passed (a variable jq must then know). */
const OPTIONS: Readonly<Record<string, { pass: string; read: string | null }>> = {
  "--arg": { pass: "--arg probe_text 1", read: "$probe_text" },
  "--argjson": { pass: "--argjson probe_json 1", read: "$probe_json" },
  "--slurpfile": { pass: "--slurpfile probe_file /dev/null", read: "$probe_file" },
  "--raw-output": { pass: "--raw-output", read: null },
  "--compact-output": { pass: "--compact-output", read: null },
  "--raw-input": { pass: "--raw-input", read: null },
  "--slurp": { pass: "--slurp", read: null },
};

/** Each keyword form a program may use, how it is seen, and the smallest
 * use of it. A form whose use is a definition puts it before the probe. */
const FORMS: Readonly<Record<string, { seen: RegExp; use: string; define?: string }>> = {
  "def with $ parameters": {
    seen: /\bdef\s+[A-Za-z_]\w*\(\s*\$/,
    use: "probe_definition(1; 2)",
    define: "def probe_definition($first; $second): $first + $second;",
  },
  "as $variable": { seen: /\bas\s+\$/, use: "(1 as $probe_value | $probe_value)" },
  elif: { seen: /\belif\b/, use: "(if false then 1 elif false then 2 else 3 end)" },
  reduce: { seen: /\breduce\b/, use: "(reduce (1, 2) as $probe_item (0; . + $probe_item))" },
  foreach: {
    seen: /\bforeach\b/,
    use: "([foreach (1, 2) as $probe_item (0; . + $probe_item; .)])",
  },
  "try catch": { seen: /\btry\b/, use: "(try 1 catch 2)" },
};

/** The keywords every jq has, which need no form of their own. */
const CORE = new Set(["if", "then", "else", "end", "and", "or", "true", "false", "null"]);

/** The keywords the forms above stand for. */
const FORM_KEYWORDS = new Set(["def", "as", "elif", "reduce", "foreach", "try", "catch"]);

/** Every other keyword jq has: a program that used one would need a form. */
const OTHER_KEYWORDS = new Set(["label", "break", "import", "include", "__loc__"]);

/** Each function a program may call, and a call of it jq must resolve. */
const FUNCTIONS: Readonly<Record<string, string>> = {
  add: "add",
  empty: "empty",
  endswith: 'endswith("probe")',
  error: 'error("probe")',
  explode: "explode",
  floor: "floor",
  fromjson: "fromjson",
  getpath: "getpath([])",
  has: 'has("probe")',
  keys_unsorted: "keys_unsorted",
  last: "last",
  length: "length",
  map: "map(.)",
  not: "not",
  range: "range(0; 1)",
  select: "select(true)",
  split: 'split("probe")',
  startswith: 'startswith("probe")',
  to_entries: "to_entries",
  tojson: "tojson",
  tostring: "tostring",
  type: "type",
};

/** Every jq command in `text` — the options on its command line, across
 * continued lines — and the program its quoted heredoc holds. */
function programs(text: string): { options: string[]; program: string }[] {
  const lines = text.split("\n");
  const found: { options: string[]; program: string }[] = [];
  for (let at = 0; at < lines.length; at += 1) {
    if (!/^\s*jq\s/.test(lines[at]!)) continue;
    let command = lines[at]!;
    while (command.trimEnd().endsWith("\\") && at + 1 < lines.length) {
      at += 1;
      command += ` ${lines[at]!}`;
    }
    if (!command.includes(`<<'${SHELL_FILE.heredoc}'`)) continue;
    const body: string[] = [];
    for (at += 1; at < lines.length && lines[at] !== SHELL_FILE.heredoc; at += 1) {
      body.push(lines[at]!);
    }
    found.push({ options: command.match(/--[a-z][a-z-]*/g) ?? [], program: body.join("\n") });
  }
  return found;
}

/** What `text`'s jq programs ask of jq: options, keyword forms, functions.
 * Throws for one the tables do not list. */
export function jqNeedsOf(text: string): JqNeeds {
  const options = new Set<string>();
  const forms = new Set<string>();
  const functions = new Set<string>();
  for (const { options: passed, program } of programs(text)) {
    for (const option of passed) {
      if (ALWAYS.includes(option)) continue;
      if (!(option in OPTIONS)) throw new Error(`no probe passes the jq option ${option}`);
      options.add(option);
    }
    const code = program
      .split("\n")
      .filter((line) => !line.trim().startsWith("#"))
      .join("\n")
      .replace(/"(?:[^"\\]|\\.)*"/g, '""');
    for (const [name, form] of Object.entries(FORMS)) {
      if (form.seen.test(code)) forms.add(name);
    }
    const defined = new Set([...code.matchAll(/\bdef\s+([A-Za-z_]\w*)/g)].map((match) => match[1]!));
    for (const [word] of code.matchAll(/(?<![$.\w])[A-Za-z_]\w*/g)) {
      if (CORE.has(word) || FORM_KEYWORDS.has(word) || defined.has(word)) continue;
      if (OTHER_KEYWORDS.has(word)) throw new Error(`no probe uses the jq keyword ${word}`);
      if (!(word in FUNCTIONS)) throw new Error(`no probe names the jq function ${word}`);
      functions.add(word);
    }
  }
  const order = (names: Set<string>, table: object) =>
    Object.keys(table).filter((name) => names.has(name));
  return {
    options: order(options, OPTIONS),
    forms: order(forms, FORMS),
    functions: order(functions, FUNCTIONS),
  };
}

/** The probe, its command at `indent`, setting `status` to jq's status if
 * it fails. The program is indented one level in either file. It is one
 * array of the uses above and calls no function of its own, so it asks for
 * nothing the file's programs do not. */
export function jqProbe(indent: string, status: string, needs: JqNeeds): string[] {
  const passed = needs.options.map((option) => OPTIONS[option]!.pass);
  const used = [
    ...needs.options.flatMap((option) => OPTIONS[option]!.read ?? []),
    ...needs.forms.map((form) => FORMS[form]!.use),
    ...(needs.functions.length > 0
      ? [`(if false then [${needs.functions.map((name) => FUNCTIONS[name]).join(", ")}] else 1 end)`]
      : []),
  ];
  return [
    `${indent}jq ${[...["--null-input"], ...passed].join(" ")} \\`,
    `${indent}${INDENT}--from-file /dev/stdin >/dev/null 2>&1 <<'${SHELL_FILE.heredoc}' || ${status}=$?`,
    ...SHELL_COMMENTS.preflightProgram.map((line) => `${INDENT}# ${line}`),
    ...needs.forms.flatMap((form) => FORMS[form]!.define ?? []).map((line) => `${INDENT}${line}`),
    `${INDENT}[`,
    ...used.map((use, index) => `${INDENT}${INDENT}${use}${index < used.length - 1 ? "," : ""}`),
    `${INDENT}]`,
    SHELL_FILE.heredoc,
  ];
}
