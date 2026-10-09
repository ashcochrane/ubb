/**
 * The renderer catalogue: every fixed thing a generated file says.
 *
 * A generated file carries two classes of comment and no third (#184 §6).
 * PROVENANCE is generated from the Blueprint in one grammatical form
 * (`comments.ts`). CONTRACT is fixed prose, and every line of it is here —
 * with the messages generated code raises and prints, and the names a
 * tenant's own code can see — so what a file may ASSERT is one reviewable
 * list. The shape of the code around those lines is each target's own.
 *
 * It is CLOSED and VERSIONED. `CATALOGUE_VERSION` is meant to move whenever a
 * member is added, removed or reworded. What the package's tests hold is
 * weaker and is said plainly: the whole catalogue is pinned in a file named
 * for its version, so a change under an unchanged number is a diff of that
 * file a reviewer reads — nothing refuses it by itself.
 *
 * WHERE IT RESTATES A REGISTRY VALUE. The verdicts, the diagnostic codes, the
 * pricing modes, the amount representations and the response
 * representations are registry concepts, and their values are spelled here
 * as keys. The registry generates no artifact for this package, so each set
 * is held equal to the registry's by `tests/catalogue.test.ts`, and the three
 * the contract marks are also exhaustive by type. Two more are restated for
 * the targets' own use and held the same way: the two stop behaviours the
 * Python target passes, and the outcomes the comment above a shell close
 * names.
 *
 * The symbols are the renderer's own and are deliberately not registry
 * concepts (owner ruling of 2026-09-25, item 9): the domain registry names
 * values a tenant sends and reads, and these name things inside a generated
 * file.
 */
import type {
  DiagnosticCode,
  IntegrationReadiness,
} from "./blueprint.ts";

export const CATALOGUE_VERSION = 7;

/**
 * The environment a generated file reads, and the instructions each needs.
 *
 * ⚠ THERE IS NO DEFAULT HOST HERE, AND THAT IS A RULING (owner review of
 * PR #597, 2026-10-02). Where the API is belongs to the platform's contract,
 * and no operational hostname is ratified by it: the renderer must not turn a
 * hostname a dated document quoted into a public contract by writing it into
 * tenants' files. So `UBB_BASE_URL` is REQUIRED, and a generated file refuses
 * to build a client without it. The SDK's own default is a developer's
 * localhost and is not inherited either. The day a canonical host is
 * formally established, the target that has an SDK inherits the SDK's
 * default, and no target holds a copy of its own.
 */
export const ENVIRONMENT = {
  /** The tenant's credential. Withheld by the server; read here by name. */
  apiKey: "UBB_API_KEY",
  /** Where the API is. Not a secret, and required. */
  baseUrl: "UBB_BASE_URL",
} as const;

/**
 * What a shell file calls the stop: the three symbols ruled for it (#184 §10,
 * §15). The status is public contract — a supervisor tests for it — and it is
 * written into a generated file once, as the value of the named constant.
 */
export const SHELL = {
  /** The name of the stop's metadata. */
  stopMetadata: "stop_requested",
  /** The one symbolic constant the reserved exit status is emitted through. */
  stopExitStatusName: "UBB_EXIT_STOP_REQUESTED",
  stopExitStatus: 20,
} as const;

/**
 * The statuses a shell file returns for everything that is NOT a stop, each
 * through a named constant of its own. They are the `sysexits.h` values for
 * what each one is, used for nothing else: 20 was chosen to stand clear of
 * that block, and no status here may come to mean a stop.
 */
export const SHELL_EXIT = {
  /** A parameter left out, passed empty, or not one the call has; or work
   * that ended without saying how. */
  usage: { name: "UBB_EXIT_USAGE", status: 64 },
  /** A value that was passed and cannot be used: a supplier's cost that
   * cannot be held or its currency, a quantity that is not a whole number, a
   * response that does not hold what a declared path reads. */
  valueRefused: { name: "UBB_EXIT_VALUE_REFUSED", status: 65 },
  /** jq or curl is missing, or cannot do what the file asks of it. */
  toolUnavailable: { name: "UBB_EXIT_TOOL_UNAVAILABLE", status: 69 },
  /** A response that is not the acknowledgement the contract publishes. */
  responseUnreadable: { name: "UBB_EXIT_RESPONSE_UNREADABLE", status: 76 },
  /** A call that is not ready, or a variable the environment must hold. */
  notConfigured: { name: "UBB_EXIT_NOT_CONFIGURED", status: 78 },
} as const;

/** The names a shell artifact is made of. */
export const SHELL_FILE = {
  moduleFile: "ubb_integration.sh",
  verifyFile: "verify_integration.sh",
  environmentFile: ".env.example",
  callSiteDirectory: "call_sites",
  previewDirectory: "request_previews",
  startTask: "ubb_start_task",
  /** The outer runner of a Task. Named for the Task, the domain's own noun. */
  runTask: "ubb_run_task",
  closeTask: "ubb_close_task",
  startSubtaskPrefix: "ubb_start_subtask",
  recordPrefix: "ubb_record",
  /** What an unkeyed call is named after, where no declared key names it. */
  unkeyed: "usage",
  /** Where a start leaves the id of the work it started. */
  taskId: "UBB_TASK_ID",
  /** Where every call leaves the response it was answered with. */
  response: "UBB_RESPONSE",
  /** Where a record leaves the stop's metadata, as one line of JSON. */
  stopRequested: "UBB_STOP_REQUESTED",
  /** The delimiter of every heredoc that holds a jq program. */
  heredoc: "UBB_JQ",
  /** The largest whole number of micros a cost may be: 2**63 - 1. */
  microsLimit: "9223372036854775807",
  /** How far a reported cost's exponent may run, either way. */
  exponentLimit: 40,
  /** The most digits a whole number is carried through jq with. */
  exactDigits: 15,
  /** The two fields a close may carry beside the outcome. */
  outcomeReason: "outcome_reason",
  reasonDetail: "reason_detail",
} as const;

/** The names a Python artifact is made of. */
export const PYTHON = {
  moduleName: "ubb_integration",
  moduleFile: "ubb_integration.py",
  verifyFile: "verify_integration.py",
  environmentFile: ".env.example",
  callSiteDirectory: "call_sites",
  /** The SDK major this target is written against. */
  sdkMajorVersion: 3,
  startTask: "start_task",
  unitOfWork: "unit_of_work",
  startSubtaskPrefix: "start_subtask",
  recordPrefix: "record",
  backfillPrefix: "backfill",
  /** What an unkeyed call is named after, where no declared key names it. */
  unkeyed: "usage",
  notReadyError: "UBBIntegrationNotReady",
  environmentError: "UBBEnvironmentNotSet",
  amountRefused: "ReportedCostNotRepresentable",
  currencyRefused: "ReportedCostCurrencyRefused",
  logger: "ubb_integration",
  /** The parameter a backfill adds: when the work actually happened. */
  recordedAt: "recorded_at",
  /** The two values of the SDK's `stop_behavior`, as the SDK spells them. */
  stopBehaviorRaise: "raise",
  stopBehaviorReturn: "return",
} as const;

/**
 * Micros in one minor unit of each currency UBB holds. Held equal to the
 * platform's own table by the package's tests, through a file the platform
 * writes.
 */
export const MICROS_PER_MINOR_UNIT: Readonly<Record<string, number>> = {
  aud: 10000, brl: 10000, cad: 10000, chf: 10000, czk: 10000, dkk: 10000,
  eur: 10000, gbp: 10000, hkd: 10000, inr: 10000, mxn: 10000, nok: 10000,
  nzd: 10000, pln: 10000, sek: 10000, sgd: 10000, usd: 10000, zar: 10000,
};

/** How a cost a supplier reports is declared to be represented. */
export const AMOUNT_REPRESENTATION = {
  micros: "micros",
  minorUnits: "minor_units",
  majorUnitsDecimal: "major_units_decimal",
} as const;

/** The two things a response a path is read off can be. */
export const RESPONSE_REPRESENTATION = {
  json: "json",
  pythonObject: "python_object",
} as const;

/** How a kind of work is sold, where this target says something about it. */
export const PRICING_MODE_COMMENTS: Readonly<Record<string, readonly string[]>> = {
  event_priced: [
    "This kind of work is priced event by event, as each one is recorded.",
  ],
  fixed: [
    "This kind of work is sold whole, at one agreed price. Declaring it",
    "delivered is what creates the charge, once. A retried start with a new",
    "idempotency_key is a second piece of work, and a second charge.",
  ],
};

/** What each verdict means, in the words the header states it in. */
export const READINESS_COMMENTS: Readonly<Record<IntegrationReadiness, readonly string[]>> = {
  scaffold: [
    "SCAFFOLD, NOT READY TO RUN. A kind of work or an Event Type is not",
    "selected or not declared. This file shows the shape of the lifecycle;",
    "the calls that are not ready raise UBBIntegrationNotReady.",
  ],
  blocked: [
    "BLOCKED, NOT READY TO RUN. The structure is known, and at least one",
    "call lacks something it cannot run without. Those calls raise",
    "UBBIntegrationNotReady; the others run.",
  ],
  complete: [
    "COMPLETE. Every call has what it needs to run.",
  ],
};

/** The same verdicts, in the words a shell file's header states them in. */
export const SHELL_READINESS_COMMENTS: Readonly<
  Record<IntegrationReadiness, readonly string[]>
> = {
  scaffold: [
    "SCAFFOLD, NOT READY TO RUN. A kind of work or an Event Type is not",
    "selected or not declared. This file shows the shape of the lifecycle;",
    "the calls that are not ready return UBB_EXIT_NOT_CONFIGURED.",
  ],
  blocked: [
    "BLOCKED, NOT READY TO RUN. The structure is known, and at least one",
    "call lacks something it cannot run without. Those calls return",
    "UBB_EXIT_NOT_CONFIGURED; the others run.",
  ],
  complete: [
    "COMPLETE. Every call has what it needs to run.",
  ],
};

/** What to do about each diagnostic. One entry per code, and no others. */
export const REMEDIATION: Readonly<Record<DiagnosticCode, readonly string[]>> = {
  task_type_not_selected: [
    "No kind of work is selected. Select one in the Code Builder.",
  ],
  task_type_not_declared: [
    "The selected kind of work is not declared. Declare it, or select one",
    "that is.",
  ],
  task_type_retired: [
    "The selected kind of work is retired, so nothing can start under it.",
    "Select a kind of work that is live.",
  ],
  required_grouping_field_not_declared: [
    "This kind of work requires a Grouping Field that is not declared.",
    "Declare the field with the request below.",
  ],
  required_grouping_field_retired: [
    "This kind of work requires a Grouping Field that is retired. Change",
    "which fields the kind of work requires.",
  ],
  required_grouping_field_wrong_scope: [
    "This kind of work requires a Grouping Field declared at another scope,",
    "so a start cannot supply it. Change which fields the kind of work",
    "requires.",
  ],
  event_type_not_selected: [
    "No Event Type is selected. Select at least one in the Code Builder.",
  ],
  event_type_not_declared: [
    "The selected Event Type is not declared. Declare it with the request",
    "below, then publish it.",
  ],
  event_type_not_published: [
    "The Event Type has no publication to resolve from. Publish it with the",
    "request below.",
  ],
  event_type_revised_since_publication: [
    "The Event Type has been edited since it was published. This file is",
    "resolved from the publication, not from the edits. Publish with the",
    "request below when the edits are meant to take effect.",
  ],
  reported_cost_mapping_missing: [
    "The Event Type is costed from a figure its supplier reports, and",
    "declares nowhere to read that figure from. Declare the mapping with the",
    "request below.",
  ],
  constant_measurement_not_renderable: [
    "The constant quantity is valid platform configuration, with its value",
    "declared. This Code Builder version cannot yet generate code that uses",
    "it, so the call is blocked until a version that can. Nothing in the",
    "declaration needs to change.",
  ],
  derived_measurement_unsupported: [
    "A derived quantity cannot be computed by generated code. Declare the",
    "quantity another way with the request below.",
  ],
  response_shape_not_declared: [
    "A value is read off the supplier's response, and the Event Type",
    "declares no response shape. Declare one with the request below.",
  ],
  response_shape_not_readable_by_target: [
    "The declared response shape is one this target cannot read. Declare a",
    "shape it can with the request below, or generate for another target.",
  ],
  source_path_convention_mismatch: [
    "A declared path is spelled against the naming of its response shape.",
    "It is emitted exactly as declared. Check it against the client you",
    "call, or correct it with the request below.",
  ],
};

/** Every other fixed comment, by where it is said. */
export const COMMENTS = {
  generated: [
    `UBB integration, generated by ubb-codegen (renderer catalogue version ${CATALOGUE_VERSION}).`,
    "Do not edit this file. When your UBB configuration changes, generate it",
    "again and replace it whole. Your own code lives at the call sites.",
  ],
  draftPreview: [
    "DRAFT PREVIEW. Resolved from draft declarations, not from published",
    "ones. It is stored nowhere, has no configuration_fingerprint, and cannot",
    "be verified.",
  ],
  fingerprint: [
    "The fingerprint identifies exactly what this file was resolved from. A",
    "different one in the Code Builder means this file is stale.",
  ],
  resolvedFrom: ["Resolved from these declarations:"],
  noDiagnostics: ["Nothing is reported against this integration."],
  diagnostics: ["Reported against this integration:"],
  remediationRequest: [
    "The request that fixes it. UBB never sends it for you:",
  ],
  legend: [
    "Three kinds of value appear below, and each has its own shape.",
    "  A literal is a value UBB resolved from what you declared.",
    "  A parameter is a value only your code holds. Every one is required:",
    "  leave one out and Python raises TypeError at the call.",
    "  os.environ[...] is a credential. UBB withholds it from this file.",
    "A literal with no configured value, or one this Code Builder version",
    "cannot yet generate, is a state of a literal, not a fourth kind: it is",
    "written as a call that raises, saying which.",
  ],
  client: [
    "The client is built on first use, so importing this file needs no",
    "credentials.",
  ],
  apiKey: [
    "A credential. Set it in the environment this code runs in, and never",
    "write its value into a file.",
  ],
  baseUrl: [
    "Not a secret, and required: the base URL of the UBB API this code",
    "calls. This file holds no address of its own.",
  ],
  environmentNotSet: [
    "What building the client raises when a variable it needs is not set.",
  ],
  notReady: [
    "What a call raises while it is not ready to run. The header of this",
    "file says why.",
  ],
  notReadyCall: [
    "This call is not ready to run. See the header of this file.",
  ],
  /** Every converted cost, whichever way it arrives. */
  reportedCost: [
    "A cost a supplier reports is converted to whole micros once, here,",
    "through Decimal. A binary float is refused. An amount finer than a",
    "micro is refused, never rounded.",
  ],
  /** A cost the caller passes, in a file that has one (#577). */
  callerCost: [
    "A currency other than the declared one fails, never converts.",
  ],
  /** A cost read off the response, in a file that reads one (#583). */
  responseCost: [
    "A cost read off your supplier's response is read as it is there: an",
    "integer, a decimal string, or a Decimal where you parse JSON with",
    "parse_float=Decimal. A binary float is refused: read the response's",
    "integer or decimal string instead.",
  ],
  /** A currency read off the response beside it (#583 D1). */
  responseCurrency: [
    "A currency read off the response that UBB does not hold is refused",
    "here. One it holds that is not your UBB currency is refused by UBB",
    "when the event is recorded, and that refusal reaches you as the SDK's",
    "error.",
  ],
  start: [
    "idempotency_key is your own identifier for this piece of work, and the",
    "same on every retry. A new value on each attempt starts the work twice.",
  ],
  unitOfWork: [
    "The whole piece of work, as one block. Declare how it ended inside the",
    "block, with complete(), fail(outcome_reason) or cancel().",
    "This is the one place a stop is caught. The event that carried it was",
    "recorded and charged: never send it again. The stop is logged and",
    "raised again, so whatever runs this work can honour its scope.",
    "What is logged is the key the event was sent under and each field of",
    "the stop by its own name, as UBB stated it: what does not apply is",
    "None, and nothing is worked out.",
  ],
  subtask: [
    "A Subtask is started only where you say so. UBB never infers one.",
  ],
  record: [
    "A stop is raised as UBBStopRequested, which is not an Exception, so",
    "your own `except Exception` cannot swallow it. Nothing here catches it.",
  ],
  response: [
    "This file never calls your supplier. Pass the response you already",
    "have.",
  ],
  backfill: [
    "For work that has already happened. A stop is returned on the",
    "acknowledgement and not raised, so the rest of a backlog is still",
    "recorded. Read `stop` on what this returns.",
  ],
  environmentFile: [
    "Copy this file to .env and fill it in. Never commit the copy.",
  ],
  verify: [
    "Checks the paths you declared against a response your supplier really",
    "returned. UBB never sees that response, so only you can run this.",
    "It calls nothing: no supplier and no UBB. Save one real response as",
    "JSON and pass it:",
    "  python verify_integration.py EVENT_TYPE captured-response.json",
  ],
  verifyPaths: [
    "Every quantity read off a response, by Event Type, and where.",
  ],
  verifyCosts: [
    "Every supplier cost read off a response, by Event Type: where, what it",
    "represents, and its currency or where that is read. A cost of zero is",
    "a cost: what is checked is that each value is there, is what a cost",
    "may be, and converts.",
  ],
  callSiteUnitOfWork: [
    "Where the piece of work begins. Everything it does goes inside.",
  ],
  callSiteClose: [
    "Inside the block, before it ends: exactly one of these. A block that",
    "ends cleanly having declared nothing raises TaskOutcomeRequired and",
    "leaves the work open.",
  ],
  callSiteSubtask: [
    "Only where your code creates this Subtask, inside the work it is part",
    "of. Pass its task_id when recording to attribute an event to it.",
  ],
  callSiteRecord: [
    "After each call to your supplier. idempotency_key identifies this one",
    "call, and is the same if you retry it. task_id is the task_id of the",
    "handle the event belongs to: the work's own, or a Subtask's.",
  ],
  callSiteBackfill: [
    "When recording work that has already happened, one event at a time.",
    "task_id is the task_id of the handle the event belongs to.",
  ],
  callSiteStop: [
    "Around whatever runs the work, where you can act on a stop's scope.",
    "This is not error handling: the event was recorded and charged.",
  ],
} as const satisfies Record<string, readonly string[]>;

/**
 * Every fixed comment only a shell file carries, by where it is said. A shell
 * file also carries the members of `COMMENTS` that are true of any target:
 * what generated it, the fingerprint, the diagnostics, the two variables, and
 * what a start, a Subtask and a path are.
 */
export const SHELL_COMMENTS = {
  legend: [
    "Three kinds of value appear below, and each has its own shape.",
    "  A literal is a value UBB resolved from what you declared.",
    "  A parameter is a value only your code holds, passed as name=value.",
    "  Leave out one a call requires, or pass it empty, and the call returns",
    "  UBB_EXIT_USAGE before anything is sent, naming it.",
    "  $UBB_API_KEY is a credential. UBB withholds it from this file.",
    "A literal with no configured value, or one this Code Builder version",
    "cannot yet generate, is a state of a literal, not a fourth kind: it is",
    "written as a call that raises, saying which.",
  ],
  usage: [
    "Source this file from the script that does the work:",
    "  . ./ubb_integration.sh",
    "It requires curl and jq, and checks both before the first request. It",
    "sets no shell option and never exits the shell that sourced it: every",
    "function returns a status, and you check it. set -e is not relied on.",
  ],
  statuses: [
    "The statuses a function returns. A stop has a status of its own, and no",
    "other failure is ever returned as it. A request that fails returns the",
    "status curl gave it; every other failure returns one of these.",
  ],
  outputs: [
    "What a call leaves behind for the code that called it. They are shell",
    "variables this file sets, not settings you supply, and it exports none.",
    "UBB_TASK_ID is the id of the work the last start created.",
    "UBB_RESPONSE is the response to the most recent call. The next call",
    "overwrites it.",
    "UBB_STOP_REQUESTED is the stop the most recent record met, or the Task",
    "ubb_run_task ran, as one line of JSON. It is empty where none was met:",
    "each clears it before it does anything else, so a stop is never an",
    "earlier call's.",
    "They are set in your shell, so never call a function of this file",
    "inside $( ) or a pipeline: both run it in a subshell, and what it set is",
    "lost.",
  ],
  preflight: [
    "Checks, once, that jq and curl can do what this file asks of them. It",
    "contacts nothing and creates nothing.",
  ],
  preflightProgram: [
    "A program of this file's own form: read from standard input, holding",
    "comments, passing each option and using each form its programs use, and",
    "naming each function they call in a branch that is never taken.",
  ],
  environment: [
    "Both variables are required, and are read each time a request is made.",
  ],
  request: [
    "Sends one request. The credential goes to curl on standard input, so it",
    "is never an argument another process can list. The response is left in",
    "UBB_RESPONSE. A response that is not a success is printed, and the",
    "status curl gave it is returned.",
  ],
  startedTask: [
    "The id of the work a start created is read off the response and left in",
    "UBB_TASK_ID.",
  ],
  acknowledgement: [
    "A stop arrives on a successful response, so it is read off the",
    "acknowledgement and never off the HTTP status. The event that carried",
    "it was recorded and charged: never send it again. Its metadata is left",
    "in UBB_STOP_REQUESTED and the reserved status is returned.",
    "The metadata carries the stop's fields as the acknowledgement holds",
    "them, and works nothing out: what does not apply stays null, and the",
    "bound and the amount measured against it keep the digits and the sign",
    "UBB wrote, never the number jq would make of them.",
  ],
  notReady: [
    "What a call prints, before returning UBB_EXIT_NOT_CONFIGURED, while it",
    "is not ready to run. The header of this file says why.",
  ],
  parameters: [
    "What a call prints, before returning UBB_EXIT_USAGE, for a parameter it",
    "was not given, was given empty, or does not have.",
  ],
  wholeNumber: [
    "A quantity is a whole number, carried exactly or refused as",
    "UBB_EXIT_VALUE_REFUSED.",
  ],
  urlValue: [
    "A value written into a URL is one that needs no encoding there, or it",
    "is refused as UBB_EXIT_VALUE_REFUSED.",
  ],
  /** Every converted cost, whichever way it arrives. */
  reportedCost: [
    "A cost a supplier reports is converted to whole micros once, here, on",
    "its digits as text: no arithmetic is done on the amount, so nothing can",
    "round it. An amount finer than a micro is refused, never rounded, as",
    "UBB_EXIT_VALUE_REFUSED.",
  ],
  /** A cost the caller passes, in a file that has one (#578). */
  callerCost: [
    "A currency other than the declared one fails, never converts, as",
    "UBB_EXIT_VALUE_REFUSED. Pass the amount as the text your supplier",
    "wrote. A number another tool has parsed, jq included, may already have",
    "been rounded.",
  ],
  /** A cost read off the response, in a file that reads one (#583). */
  responseCost: [
    "A cost read off your supplier's response is read as it is written",
    "there, never as the number jq would make of it: a JSON string as its",
    "text, an integer as its digits. A number written with a fraction or an",
    "exponent is a binary float, and is refused as UBB_EXIT_VALUE_REFUSED:",
    "read the response's integer or decimal string instead. So is a",
    "response holding a number Python's json does not read, such as 01, .5",
    "or nan, wherever it sits.",
  ],
  /** A currency read off the response beside it (#583 D1). */
  responseCurrency: [
    "A currency read off the response that UBB does not hold is refused as",
    "UBB_EXIT_VALUE_REFUSED. One it holds that is not your UBB currency is",
    "refused by UBB when the event is recorded, and the call returns what",
    "curl gave that refusal.",
  ],
  writtenProgram: [
    "Reads one value off the response as the response wrote it, and prints",
    "what kind of value it is: for a string or an integer, with its text. A",
    "response holding a number Python's json does not read is not read, and",
    "no number is read for what it is worth, because that loses how it was",
    "written.",
  ],
  runTask: [
    "The whole of a Task, as one command you name. It is run with the Task's",
    "task_id as its one argument. Declare how the work ended inside it, with",
    "ubb_close_task: nothing here declares an outcome for you.",
    "This is the one place a stop is acted on, and it is acted on whatever",
    "the work then returned. The event that carried it was recorded and",
    "charged: never send it again. The stop is logged and the reserved",
    "status returned, so whatever runs this work can honour its scope.",
    "Work that returns a failure is not declared failed: a status is not",
    "evidence of how the work went. Its status is returned as it is, and a",
    "Task with no outcome declared is left open and said to be. Work that",
    "returns success having declared none is left open too, and that is",
    "returned as UBB_EXIT_USAGE.",
  ],
  record: [
    "A stop is returned as UBB_EXIT_STOP_REQUESTED, with the event recorded.",
    "Return it from your own code unchanged, up to whatever runs the work.",
  ],
  response: [
    "This file never calls your supplier. Pass the path of a file holding",
    "the response it returned, as JSON. One that does not hold what a",
    "declared path reads is refused as UBB_EXIT_VALUE_REFUSED: nothing is",
    "sent, and a missing quantity is never recorded as none.",
  ],
  close: [
    "outcome is delivered, failed or cancelled, and UBB never guesses it. A",
    "failure also says why: pass outcome_reason, and reason_detail if you",
    "have a sentence to go with it.",
  ],
  environmentFile: [
    "Load the copy before sourcing ubb_integration.sh:",
    "  set -a; . ./.env; set +a",
  ],
  verify: [
    "Checks the paths you declared against a response your supplier really",
    "returned. UBB never sees that response, so only you can run this.",
    "It calls nothing: no supplier and no UBB. Save one real response as",
    "JSON and pass it:",
    "  sh verify_integration.sh EVENT_TYPE captured-response.json",
  ],
  verifyPreflight: [
    "Checks that jq can do what this script asks of it. It contacts nothing",
    "and creates nothing.",
  ],
  verifyCosts: [
    "What checks a supplier's cost read off a response: the runnable file's",
    "own programs and functions, which read, pin and convert it here exactly",
    "as they do there, and one check of each Event Type that reads a cost.",
  ],
  callSiteRunTask: [
    "Where the piece of work begins. Everything it does goes inside the",
    "function, which is handed the work's task_id. Check the status of each",
    "call yourself: set -e does not apply inside a function run this way.",
  ],
  callSiteClose: [
    "Inside the work, before it ends: exactly once. A Task whose work ends",
    "having declared nothing is left open, and that is reported.",
  ],
  callSiteRecord: [
    "After each call to your supplier. idempotency_key identifies this one",
    "call, and is the same if you retry it. task_id is the task_id of the",
    "work the event belongs to: the work's own, or a Subtask's.",
  ],
  callSiteStop: [
    "Where the work is run, if you act on a stop's scope yourself. This is",
    "not error handling: the event was recorded and charged.",
    "UBB_STOP_REQUESTED holds the stop as JSON: its scope and reason, what",
    "applied it, and the bound and the amount measured against it, each null",
    "where it does not apply. Pass the status on to whatever runs this code.",
  ],
  preview: [
    "A preview of one request, for reading: the method, the URL, the headers",
    "and the body. It is not the runnable file and carries no verdict: the",
    "header of the runnable file says whether the integration is ready.",
  ],
} as const satisfies Record<string, readonly string[]>;

/** What generated code says when it raises or reports. */
export const MESSAGES = {
  notReady: "is not ready to run. The generated file's header says why.",
  notConfigured: "has no configured value",
  /** A value the tenant declared that this renderer cannot yet write (#571).
   * Never "missing": the declaration is complete. */
  notRenderable:
    "is valid platform configuration that this Code Builder version cannot yet generate: " +
    "see the blocking diagnostic in this file's header",
  environmentNotSet: "is not set. Set it in the environment this code runs in.",
  /** The stop, as the Python boundary logs it: the key, then each field the
   * stop is explained by, by its own name and in the acknowledgement's order
   * (`STOP_FIELDS`), as the SDK holds it (#585). */
  stop:
    "UBB requested a stop. The event sent as %r was recorded and must not be sent again. " +
    "stop_scope=%r, stop_reason=%r, trigger_source=%r, stop_bound_micros=%r, stop_measured_micros=%r",
  float: "is a binary float, and a reported cost is money: pass its decimal text or an integer",
  /** The same refusal of a cost read off a response, which says what to read
   * rather than what to pass (#583). */
  floatRead:
    "is a binary float, and a reported cost is money: read the response's integer or its decimal string instead",
  currencyNotText: "is not a currency code: a currency read off a response is text",
  flag: "is a flag, not a reported cost",
  missing: "no cost was reported, and a missing cost is not a zero",
  notANumber: "is not a number",
  notFinite: "is not a finite amount",
  exponent: "is not an amount of money that can be held: its exponent is out of range",
  fractional: "is not a whole number of micros, and a reported cost is never rounded",
  tooLarge: "is more micros than can be held",
  representation: "is not an amount representation",
  currencyUnknown: "is not a currency UBB holds",
  currencyNone: "this cost is denominated in no currency",
  currencyDisagrees: "the supplier reported this cost in another currency than the declared one",
  verifyUsage: "usage: python verify_integration.py EVENT_TYPE captured-response.json",
  verifyEventTypes: "Event Types with a quantity or a cost read off a response:",
  verifyNothing:
    "No selected Event Type reads a quantity or a cost off a response. There is nothing to check.",
  verifyResolves: "resolves in the captured response",
  verifyNumber: "is a number",
  verifyNotZero: "is not zero (a constant zero is what a path to the wrong field reads)",
  verifyDistinct: "is read from a path no other quantity is read from",
  verifyAmount: "is an integer or a decimal string, as a reported cost must be",
  verifyConverts: "converts to whole micros exactly",
  verifyCurrency: "is a currency UBB holds",
  verifyPassed: "Every check passed.",
  verifyFailed: "check(s) failed.",
  verifyOk: "ok  ",
  verifyFail: "FAIL",
} as const;

/**
 * What only a shell file says. It also says the members of `MESSAGES` that
 * are true of any target: the conversion's refusals and the verify script's
 * verdicts.
 */
export const SHELL_MESSAGES = {
  jqMissing: "This file requires jq, and none is installed.",
  jqUnusable: "The installed jq cannot run the programs this file hands it. jq 1.5 or later can.",
  curlMissing: "This file requires curl, and none is installed.",
  curlUnusable: "The installed curl has no --fail-with-body. curl 7.76 or later has it.",
  missing: "is required, and was left out or passed empty.",
  unknown: "is not a parameter of this call. Pass each one as name=value.",
  wholeNumber: "is not a whole number of at most 15 digits, which is what is carried exactly.",
  urlValue: "cannot be written into a URL as it stands.",
  work: "the first argument is the command that does the work.",
  outcomeRequired:
    "the work ended without declaring an outcome, and is left open. Declare one with ubb_close_task.",
  leftOpen:
    "the work returned a failure and declared no outcome. None was declared for it: the Task is left open.",
  stop: "UBB requested a stop. The event that carried it was recorded and must not be sent again.",
  responseUnreadable: "the response is not the acknowledgement this call expects.",
  noTaskId: "the response carries no task_id",
  noEventId: "the acknowledgement carries no event_id",
  /** Why a stop's acknowledgement was refused rather than carried, said
   * before the field's name (#585): what is not there is never filled in,
   * and a figure is never rounded. */
  stopFigure: "the acknowledgement holds no whole number or null at",
  stopText: "the acknowledgement holds no text or null at",
  noValue: "the response holds no value at",
  notWhole: "the response holds a value that is not a whole number at",
  /** Why a value read off the response as written was refused, said after
   * `<call>: <field> read at <path>` (#583). */
  readMissing: "is not in the response",
  readUnreadable: "cannot be read: the response is not JSON",
  readNull: "is null: no cost was reported, and a missing cost is not a zero",
  inexact: "the response holds a number too large to be carried exactly at",
  verifyUsage: "usage: sh verify_integration.sh EVENT_TYPE captured-response.json",
} as const;
