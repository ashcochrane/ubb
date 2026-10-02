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
 * the contract marks are also exhaustive by type.
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

export const CATALOGUE_VERSION = 1;

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
 * What a shell file calls the stop, declared here so both targets take it
 * from one place. Nothing in the Python target emits them.
 */
export const SHELL = {
  /** The name of the stop's metadata. */
  stopMetadata: "stop_requested",
  /** The one symbolic constant the reserved exit status is emitted through. */
  stopExitStatusName: "UBB_EXIT_STOP_REQUESTED",
  stopExitStatus: 20,
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
  reported_cost_provider_response_unsupported: [
    "The supplier's cost is declared to be read off the response, and no",
    "generated call can carry a cost read that way. Declare it as supplied",
    "by the caller with the request below.",
  ],
  constant_value_not_declared: [
    "A constant quantity has no declared value, and none is made up for it.",
    "Declare the quantity another way with the request below.",
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
    "A literal with no configured value is a state of a literal, not a",
    "fourth kind: it is written as a call that raises, naming what is",
    "missing.",
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
    "What a call raises until the declarations it needs are made. The",
    "header of this file lists them.",
  ],
  notReadyCall: [
    "This call is not ready to run. See the header of this file.",
  ],
  reportedCost: [
    "A cost a supplier reports is converted to whole micros once, here,",
    "through Decimal. A binary float is refused. An amount finer than a",
    "micro is refused, never rounded. A currency other than the declared",
    "one fails, never converts.",
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

/** What generated code says when it raises or reports. */
export const MESSAGES = {
  notReady: "is not ready to run. The generated file's header lists what to declare.",
  notConfigured: "has no configured value",
  environmentNotSet: "is not set. Set it in the environment this code runs in.",
  stop: "UBB requested a stop. The event sent as %r was recorded and must not be sent again: %r",
  float: "is a binary float, and a reported cost is money: pass its decimal text or an integer",
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
  verifyEventTypes: "Event Types with a quantity read off a response:",
  verifyNothing: "No selected Event Type reads a quantity off a response. There is nothing to check.",
  verifyResolves: "resolves in the captured response",
  verifyNumber: "is a number",
  verifyNotZero: "is not zero (a constant zero is what a path to the wrong field reads)",
  verifyDistinct: "is read from a path no other quantity is read from",
  verifyPassed: "Every check passed.",
  verifyFailed: "check(s) failed.",
  verifyOk: "ok  ",
  verifyFail: "FAIL",
} as const;
