/**
 * The call-site blocks: the lines that go into code a tenant maintains.
 *
 * NO GENERATED VALUE APPEARS IN ONE (#184 §6), and that is held by what a
 * block is built from. `Block` has room for the name of a function the module
 * exports and for the names of parameters, and for nothing else: there is no
 * field a literal, a declared key or a path could arrive through. Every value
 * the Blueprint resolved lives in the module, so replacing the module is the
 * whole of regenerating and these lines never go stale.
 *
 * A parameter is passed from a variable of its own name. Where the value is
 * one the SDK's handle holds — the id of the work a start returned — the
 * block reads it off the handle.
 */
import { COMMENTS, PYTHON } from "../catalogue.ts";
import { hash } from "../comments.ts";
import type { Plan } from "./plan.ts";

const INDENT = "    ";

/** What a block may be made of: names, and never a value. */
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

/** Parameters whose value is read off the handle rather than held by name. */
const FROM_THE_HANDLE: Readonly<Record<string, string>> = {
  task_id: `${TASK}.task_id`,
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
      ...hash(block.comments),
      ...(block.imports.length === 0
        ? []
        : [`from ${PYTHON.moduleName} import ${block.imports.join(", ")}`, ""]),
      ...block.body,
    ].join("\n")}\n`,
  }));
}
