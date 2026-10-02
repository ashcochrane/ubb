/**
 * The call-site blocks: the lines that go into a script a tenant maintains.
 *
 * NO GENERATED VALUE APPEARS IN ONE (#184 §6). Every block is written from
 * the plan's function names and parameter names and from fixed text; nothing
 * here reads a token's literal, a declared key or a path. A block holds no
 * quoted text but the expansion of a variable, and no number of its own.
 *
 * What a block DOES hold are names: the functions the runnable file defines,
 * which are named for declared keys, and the parameters the Blueprint named.
 * Those do not change when configuration does, which is what lets these
 * lines be left alone when the file is replaced.
 *
 * A parameter is passed from a variable of its own name, with one exception:
 * a Subtask's parent is the work the block sits inside, so its id is the one
 * that work was handed. Which work an EVENT belongs to is the tenant's to say
 * — the Task or one of its Subtasks — so a record block asks for it by name.
 * `:` stands where the tenant's own code goes.
 *
 * EVERY BLOCK HOLDS UNDER `set -e` AND WITHOUT IT. A call inside the work is
 * followed by `|| return $?`, and the block that acts on a stop takes the
 * status of the work on the right of `&&` and `||`, so no shell option decides
 * whether the line after a call is reached.
 */
import { COMMENTS, SHELL, SHELL_COMMENTS, SHELL_FILE } from "../catalogue.ts";
import { asComments } from "../comments.ts";
import type { CallPlan, Plan } from "./plan.ts";
import { INDENT } from "./syntax.ts";

/** One block: where it goes, what is said above it, and its lines. */
interface Block {
  readonly file: string;
  readonly comments: readonly string[];
  readonly body: readonly string[];
}

export interface CallSite {
  readonly path: string;
  readonly contents: string;
}

/** The function a block defines for the work, and the variables it holds the
 * ids and the status of the work in. */
const WORK = "work";
const TASK_ID = "task_id";
const SUBTASK_ID = "subtask_id";
const WORK_STATUS = "work_status";

/** The arguments of a call, each from a variable of the parameter's own name
 * but the one that names the work a Subtask is part of. */
function passed(call: CallPlan): string[] {
  return call.parameters
    .filter((parameter) => parameter.required)
    .map(
      (parameter) =>
        `${parameter.name}="$${parameter.name === call.parent?.name ? TASK_ID : parameter.name}"`,
    );
}

/** A call on several lines, one argument a line, ending as `ending` says. */
function invoke(first: string, call: CallPlan, ending = ""): string[] {
  const words = [first, ...passed(call).map((argument) => `${INDENT}${argument}`)];
  return words.map((word, index) =>
    index === words.length - 1 ? `${word}${ending}` : `${word} \\`,
  );
}

const OR_RETURN = " || return $?";

function work(): string[] {
  return [`${WORK}() {`, `${INDENT}${TASK_ID}=$1`, `${INDENT}:`, "}"];
}

function blocks(plan: Plan): Block[] {
  const run = `${SHELL_FILE.runTask} ${WORK}`;
  return [
    {
      file: "run_task",
      comments: SHELL_COMMENTS.callSiteRunTask,
      body: [...work(), ...invoke(run, plan.start)],
    },
    ...plan.subtasks.map((subtask) => ({
      file: subtask.name,
      comments: COMMENTS.callSiteSubtask,
      body: [
        ...invoke(subtask.name, subtask, OR_RETURN),
        `${SUBTASK_ID}=$${SHELL_FILE.taskId}`,
      ],
    })),
    ...plan.records.map((record) => ({
      file: record.name,
      comments: SHELL_COMMENTS.callSiteRecord,
      body: invoke(record.name, record, OR_RETURN),
    })),
    {
      file: "close",
      comments: SHELL_COMMENTS.callSiteClose,
      body: invoke(plan.close.name, plan.close, OR_RETURN),
    },
    {
      file: "stop",
      comments: SHELL_COMMENTS.callSiteStop,
      body: [
        // The status of the work, whichever way it ended, taken where no
        // `set -e` can end the script before it is read.
        ...invoke(run, plan.start, ` && ${WORK_STATUS}=$? || ${WORK_STATUS}=$?`),
        `if [ "$${WORK_STATUS}" -eq "$${SHELL.stopExitStatusName}" ]; then`,
        `${INDENT}:`,
        "fi",
      ],
    },
  ];
}

export function renderCallSites(plan: Plan): CallSite[] {
  return blocks(plan).map((block) => ({
    path: `${SHELL_FILE.callSiteDirectory}/${block.file}.sh`,
    contents: `${[...asComments(block.comments), ...block.body].join("\n")}\n`,
  }));
}
