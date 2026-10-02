/**
 * Reading a rendered shell file as text.
 *
 * Worked out here against the shell's own grammar and not against the
 * renderer: where a heredoc starts and ends, what is inside a command
 * substitution, which lines are a function's. A mistake in the renderer is
 * then contradicted by these readings rather than reproduced by them.
 */

export interface Heredoc {
  delimiter: string;
  /** Whether the delimiter was quoted, so that the shell expands nothing. */
  quoted: boolean;
  /** The line the heredoc is opened on. */
  opener: string;
  body: string[];
}

const OPENS = /<<(-?)(?:'([A-Za-z_]+)'|"([A-Za-z_]+)"|([A-Za-z_]+))/;

/** Every heredoc of a file, in order. */
export function heredocs(text: string): Heredoc[] {
  const found: Heredoc[] = [];
  const lines = text.split("\n");
  for (let index = 0; index < lines.length; index += 1) {
    const opened = OPENS.exec(lines[index]!);
    if (opened === null || lines[index]!.trimStart().startsWith("#")) continue;
    const delimiter = opened[2] ?? opened[3] ?? opened[4]!;
    const heredoc: Heredoc = {
      delimiter,
      quoted: opened[4] === undefined,
      opener: lines[index]!,
      body: [],
    };
    for (index += 1; index < lines.length && lines[index] !== delimiter; index += 1) {
      heredoc.body.push(lines[index]!);
    }
    if (index === lines.length) throw new Error(`the heredoc ${delimiter} is never closed`);
    found.push(heredoc);
  }
  return found;
}

/** The file with every heredoc's body and every comment taken out: the lines
 * the shell itself reads as code. */
export function shellCode(text: string): string[] {
  const code: string[] = [];
  const lines = text.split("\n");
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index]!;
    if (line.trimStart().startsWith("#")) continue;
    code.push(line);
    const opened = OPENS.exec(line);
    if (opened === null) continue;
    const delimiter = opened[2] ?? opened[3] ?? opened[4]!;
    for (index += 1; index < lines.length && lines[index] !== delimiter; index += 1);
  }
  return code;
}

/**
 * What is run inside each command substitution of a file: the text between
 * `$(` and its `)`, with heredoc bodies left out and single-quoted text
 * blanked. Arithmetic — `$((` — is not a substitution and is not returned.
 */
export function substitutions(text: string): string[] {
  const code = shellCode(text).join("\n");
  const found: string[] = [];
  const open: number[] = [];
  let quoted = false;
  let arithmetic = 0;
  for (let index = 0; index < code.length; index += 1) {
    const character = code[index]!;
    if (quoted) {
      if (character === "'") quoted = false;
      continue;
    }
    if (character === "\\") {
      index += 1;
    } else if (character === "'" && !insideDoubleQuotes(code, index)) {
      quoted = true;
    } else if (code.startsWith("$((", index)) {
      arithmetic += 1;
      index += 2;
    } else if (code.startsWith("$(", index)) {
      open.push(index + 2);
      index += 1;
    } else if (character === ")" && arithmetic > 0 && code[index + 1] === ")") {
      arithmetic -= 1;
      index += 1;
    } else if (character === ")" && open.length > 0) {
      // Outside a substitution a `)` closes a `case` pattern and nothing is
      // open; inside one, a generated file holds no `case`.
      found.push(code.slice(open.pop()!, index));
    }
  }
  if (open.length > 0) throw new Error("a command substitution is never closed");
  return found;
}

function insideDoubleQuotes(code: string, at: number): boolean {
  // Counted on the line: no double-quoted text in a generated file spans one.
  const line = code.slice(code.lastIndexOf("\n", at) + 1, at);
  return (line.match(/(?<!\\)"/g) ?? []).length % 2 === 1;
}

export interface ShellFunction {
  name: string;
  /** Every line from the one that opens it to the one that closes it. */
  lines: string[];
}

/** Every function a file defines at its top level. */
export function functionsOf(text: string): ShellFunction[] {
  const found: ShellFunction[] = [];
  const lines = text.split("\n");
  for (let index = 0; index < lines.length; index += 1) {
    const opened = /^([A-Za-z_][A-Za-z0-9_]*)\(\) \{$/.exec(lines[index]!);
    if (opened === null) continue;
    const start = index;
    while (index < lines.length && lines[index] !== "}") index += 1;
    found.push({ name: opened[1]!, lines: lines.slice(start, index + 1) });
  }
  return found;
}

/** The `name=value` parameters a function reads its arguments into. */
export function parametersOf(shellFunction: ShellFunction): string[] {
  return shellFunction.lines.flatMap((line) => {
    const arm = /^\s+([A-Za-z_][A-Za-z0-9_]*)=\*\) /.exec(line);
    return arm === null ? [] : [arm[1]!];
  });
}

/** A jq program without its comments and its string literals. */
export function jqCode(program: readonly string[]): string {
  return program
    .filter((line) => !line.trimStart().startsWith("#"))
    .join("\n")
    .replace(/"(?:[^"\\]|\\.)*"/g, '""');
}
