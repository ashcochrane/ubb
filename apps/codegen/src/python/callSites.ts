/**
 * The call-site blocks: the lines that go into code a tenant maintains.
 *
 * NO GENERATED VALUE APPEARS IN ONE (#184 §6). Every block is written from
 * the plan's function names and parameter names and from fixed text; nothing
 * here reads a token's literal, a declared key or a path. A type does not
 * hold that — a block's body is lines of text — so the package's suite does:
 * Python's own parser is asked for every string, number and bytes literal in
 * every block of every branch, and there must be none. (`...` stands where
 * the tenant's code goes and is the one constant a block contains.)
 *
 * What a block DOES hold are names: the functions the module exports, which
 * are named for declared keys, and the parameters the Blueprint named. Those
 * do not change when configuration does, which is what lets these lines be
 * left alone when the module is replaced.
 *
 * A parameter is passed from a variable of its own name, with one exception:
 * a Subtask's parent is the work the block sits inside, so its id is read
 * off that work's handle. Which work an EVENT belongs to is the tenant's to
 * say — the Task or one of its Subtasks — so a record block reads it off
 * nothing and asks for it by name.
 */
import { COMMENTS, PYTHON } from "../catalogue.ts";
import { asComments } from "../comments.ts";
import type { Plan } from "./plan.ts";
import { INDENT } from "./syntax.ts";

/** One block: where it goes, what is said above it, and its lines. */
interface Block {
  readonly file: string;
  readonly comments: readonly string[];
  /** Module exports the block imports, by name. */
  readonly imports: readonly string[];
  readonly body: readonly string[];
}

export interface CallSite {
  readonly path: string;
  readonly contents: string;
}

/** The variable a block holds the work's handle in. */
const TASK = "task";
const SUBTASK = "subtask";

/** The parameter whose value is read off the handle rather than held by name. */
const FROM_THE_HANDLE: Readonly<Record<string, string>> = {
  parent_task_id: `${TASK}.task_id`,
};

function passed(parameters: readonly string[], indent: string): string[] {
  return parameters.map(
    (parameter) => `${indent}${parameter}=${FROM_THE_HANDLE[parameter] ?? parameter},`,
  );
}

function withBlock(name: string, parameters: readonly string[], handle: string): string[] {
  return [`with ${name}(`, ...passed(parameters, INDENT), `) as ${handle}:`, `${INDENT}...`];
}

function call(name: string, parameters: readonly string[], assignTo?: string): string[] {
  const opening = assignTo === undefined ? `${name}(` : `${assignTo} = ${name}(`;
  return [opening, ...passed(parameters, INDENT), ")"];
}

function blocks(plan: Plan): Block[] {
  return [
    {
      file: PYTHON.unitOfWork,
      comments: COMMENTS.callSiteUnitOfWork,
      imports: [PYTHON.unitOfWork],
      body: withBlock(PYTHON.unitOfWork, plan.start.parameters, TASK),
    },
    ...plan.subtasks.map((subtask) => ({
      file: subtask.name,
      comments: COMMENTS.callSiteSubtask,
      imports: [subtask.name],
      body: withBlock(subtask.name, subtask.parameters, SUBTASK),
    })),
    ...plan.records.flatMap((record) => [
      {
        file: record.name,
        comments: COMMENTS.callSiteRecord,
        imports: [record.name],
        body: call(record.name, record.parameters),
      },
      {
        file: record.backfillName,
        comments: COMMENTS.callSiteBackfill,
        imports: [record.backfillName],
        body: call(
          record.backfillName,
          [...record.parameters, record.recordedAt],
          "acknowledgement",
        ),
      },
    ]),
    {
      file: "close",
      comments: COMMENTS.callSiteClose,
      imports: [],
      body: [`${TASK}.complete()`, `${TASK}.fail(outcome_reason)`, `${TASK}.cancel()`],
    },
    {
      file: "stop",
      comments: COMMENTS.callSiteStop,
      imports: [],
      body: [
        "from ubb import UBBStopRequested",
        "",
        "try:",
        `${INDENT}...`,
        "except UBBStopRequested as stop:",
        `${INDENT}raise`,
      ],
    },
  ];
}

export function renderCallSites(plan: Plan): CallSite[] {
  return blocks(plan).map((block) => ({
    path: `${PYTHON.callSiteDirectory}/${block.file}.py`,
    contents: `${[
      ...asComments(block.comments),
      ...(block.imports.length === 0
        ? []
        : [`from ${PYTHON.moduleName} import ${block.imports.join(", ")}`, ""]),
      ...block.body,
    ].join("\n")}\n`,
  }));
}
