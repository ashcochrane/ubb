/**
 * Reading a Blueprint's tokens: which class each one is, and what it is named
 * under.
 *
 * A Blueprint call is a flat list of tokens (ADR-0015 §3). This module turns
 * that list into the structure a target renders from, and it is the only place
 * the token convention is read. Nothing here knows a target.
 *
 * THE FOUR SHAPES A TOKEN HAS. The contract carries a token's class as a word
 * and three optional fields; here it is one of four types, so that code
 * holding a token cannot read a field its class does not fill. A
 * `SecretReference` in particular carries the NAME of a variable and nothing
 * else: whatever a document put in the `value` of a secret token is never
 * copied out of it, so past this module there is no type through which a
 * secret TOKEN's value could reach a file. The document itself is untyped
 * JSON at the boundary and is not made safe by a type: that a Blueprint
 * carries no secret anywhere is the server's test to hold.
 *
 * WHICH TOKENS ARE ARGUMENTS, AND WHICH ARE ONLY STATED. Read off the name,
 * and off the position — never by decoding a key, and never by knowing what a
 * field means:
 *
 * 1. `api_key`, a `secret_reference`, is the credential every call carries.
 *    It is not an argument of the call: it is what the client is built with.
 * 2. A ONE-SEGMENT name is a field the call's request publishes, and it is an
 *    argument, under exactly that name.
 * 3. For the two fields that hold an object of declared keys
 *    (`KEYED_FIELDS`), each one-segment token is one KEY of that object,
 *    carried as its literal. The tokens named under the key follow it
 *    directly and share one `<field>.<segment>` prefix, read off the first of
 *    them. The token named exactly that prefix is the VALUE under the key —
 *    with the key, one entry of the argument. A key with no such token has no
 *    value this document can supply.
 * 4. Every other token — `<field>.<element>`, `<field>.<key>.<element>` — is
 *    a DECLARED FACT about the value it is named under. It is never sent and
 *    never asked for. A target states it beside that value, and may use it to
 *    choose how the value is expressed.
 */
import {
  refuse,
  type BlueprintArgument,
  type BlueprintCall,
  type BlueprintProvenance,
  type IntegrationReadiness,
  type Json,
} from "./blueprint.ts";

/** The fields of a request that hold an object of declared keys. */
export const KEYED_FIELDS: readonly string[] = ["grouping_fields", "measurements"];

declare const secretReferenceBrand: unique symbol;

/** A value UBB resolved: the literal itself. */
export interface Literal {
  readonly kind: "literal";
  readonly value: Json;
}

/** A literal UBB would know, and nothing is configured to supply. */
export interface Unconfigured {
  readonly kind: "unconfigured";
}

/**
 * A literal the tenant HAS configured, which this version of the renderer
 * cannot yet write (#571): a constant quantity's declared value. The
 * Blueprint carries it unconfigured and reports why, and `readLifecycle`
 * reads that diagnostic back onto the value, so no file calls a declared
 * value missing. The ticket that renders a constant (#584) removes it.
 */
export interface NotRenderable {
  readonly kind: "not_renderable";
}

/** A value only the tenant's code holds: the parameter it must pass. */
export interface Parameter {
  readonly kind: "parameter";
  readonly name: string;
}

/** A value UBB withholds: the variable it is read from, and no value. */
export interface SecretReference {
  readonly kind: "secret_reference";
  readonly environmentVariable: string;
  readonly [secretReferenceBrand]: true;
}

export type Binding = Literal | Unconfigured | NotRenderable | Parameter | SecretReference;

export interface Token<B extends Binding = Binding> {
  /** The name as the document gives it. Never rebuilt and never decoded. */
  readonly name: string;
  readonly binding: B;
  readonly provenance: BlueprintProvenance | null;
}

/** A declared fact, and the last segment of its name: which fact it is. */
export interface Fact {
  readonly element: string;
  readonly token: Token<Literal>;
}

/** A field of the request holding one value, and the facts declared of it. */
export interface ScalarField {
  readonly shape: "scalar";
  readonly name: string;
  readonly token: Token<Literal | Unconfigured | Parameter>;
  readonly facts: Fact[];
}

/** One declared key of a keyed field, the value under it, and its facts. */
export interface Entry {
  readonly key: Token<Literal>;
  /** The declared key itself, exactly as declared. */
  readonly keyText: string;
  /** `null` where the document carries no value for this key. Only an
   * entry's value can be one this renderer cannot yet write. */
  readonly value: Token<Literal | Unconfigured | NotRenderable | Parameter> | null;
  readonly facts: Fact[];
}

/** A field of the request holding an object of declared keys. */
export interface KeyedField {
  readonly shape: "keyed";
  readonly name: string;
  readonly entries: Entry[];
}

export type Field = ScalarField | KeyedField;

export interface Call {
  readonly operationId: string;
  readonly readiness: IntegrationReadiness;
  readonly credentials: Token<SecretReference>[];
  /** In the order the document first names each field. */
  readonly fields: Field[];
}

function bindingOf(argument: BlueprintArgument): Binding {
  switch (argument.binding_class) {
    case "secret_reference": {
      const variable = argument.environment_variable;
      if (typeof variable !== "string" || variable === "") {
        return refuse(
          `the secret reference "${argument.name}" names no environment variable`,
        );
      }
      // The one place a `SecretReference` is made. `argument.value` is not
      // read: a secret token has no value this package will carry.
      return { kind: "secret_reference", environmentVariable: variable } as SecretReference;
    }
    case "runtime_bound": {
      const parameter = argument.parameter_name;
      if (typeof parameter !== "string" || parameter === "") {
        return refuse(`the runtime value "${argument.name}" names no parameter`);
      }
      return { kind: "parameter", name: parameter };
    }
    case "platform_known":
      if (!argument.configured) return { kind: "unconfigured" };
      return { kind: "literal", value: (argument.value ?? null) as Json };
    default:
      return refuse(
        `"${argument.name}" has a binding class this renderer does not know: ` +
          `${String(argument.binding_class)}`,
      );
  }
}

function tokenOf(argument: BlueprintArgument): Token {
  const segments = argument.name.split(".");
  if (segments.length > 3 || segments.some((segment) => segment === "")) {
    refuse(`"${argument.name}" is not a token name of one to three segments`);
  }
  return {
    name: argument.name,
    binding: bindingOf(argument),
    provenance: argument.provenance ?? null,
  };
}

function isLiteral(token: Token): token is Token<Literal> {
  return token.binding.kind === "literal";
}

function isSecret(token: Token): token is Token<SecretReference> {
  return token.binding.kind === "secret_reference";
}

function notSecret(token: Token): Token<Literal | Unconfigured | Parameter> {
  if (isSecret(token)) {
    return refuse(
      `"${token.name}" is a secret reference where a call's value is named; ` +
        `only a credential is one`,
    );
  }
  return token as Token<Literal | Unconfigured | Parameter>;
}

function factOf(token: Token): Fact | null {
  const element = token.name.slice(token.name.lastIndexOf(".") + 1);
  if (isLiteral(token)) return { element, token };
  if (token.binding.kind === "unconfigured") return null;
  return refuse(
    `"${token.name}" is named as a declared fact and is not a platform-known value`,
  );
}

/** One call of a Blueprint, with its tokens placed by the convention above. */
export function readCall(call: BlueprintCall): Call {
  const tokens = call.arguments.map(tokenOf);
  const credentials: Token<SecretReference>[] = [];
  const fields: Field[] = [];
  const scalars = new Map<string, ScalarField>();
  const keyed = new Map<string, KeyedField>();
  const strayFacts: Token[] = [];

  let index = 0;
  while (index < tokens.length) {
    const token = tokens[index]!;
    index += 1;
    const segments = token.name.split(".");

    if (segments.length > 1) {
      strayFacts.push(token);
      continue;
    }
    if (isSecret(token)) {
      credentials.push(token);
      continue;
    }
    if (KEYED_FIELDS.includes(token.name)) {
      if (!isLiteral(token) || typeof token.binding.value !== "string") {
        refuse(`a key of "${token.name}" is not a declared key carried as a literal`);
      }
      const entry: Entry = {
        key: token as Token<Literal>,
        keyText: (token.binding as Literal).value as string,
        value: null,
        facts: [],
      };
      // Everything named under this key follows it directly, sharing one
      // prefix. The prefix is read off the name the document gives — the key
      // inside it is never rebuilt here.
      const next = tokens[index];
      const nextSegments = next?.name.split(".") ?? [];
      let value: Entry["value"] = null;
      if (nextSegments.length > 1 && nextSegments[0] === token.name) {
        const prefix = `${nextSegments[0]}.${nextSegments[1]}`;
        while (index < tokens.length) {
          const under = tokens[index]!;
          if (under.name === prefix) {
            if (value !== null) refuse(`"${prefix}" is named twice under one key`);
            value = notSecret(under);
          } else if (under.name.startsWith(`${prefix}.`)) {
            const fact = factOf(under);
            if (fact !== null) entry.facts.push(fact);
          } else {
            break;
          }
          index += 1;
        }
      }
      let field = keyed.get(token.name);
      if (field === undefined) {
        field = { shape: "keyed", name: token.name, entries: [] };
        keyed.set(token.name, field);
        fields.push(field);
      }
      field.entries.push({ ...entry, value });
      continue;
    }
    if (scalars.has(token.name)) {
      refuse(`"${token.name}" is named twice on one call`);
    }
    const field: ScalarField = {
      shape: "scalar",
      name: token.name,
      token: notSecret(token),
      facts: [],
    };
    scalars.set(token.name, field);
    fields.push(field);
  }

  // One credential a call, and it is what the client is built with. A second
  // secret would be a value the call needs and this reader has no place for;
  // taking it for the credential would drop it from the call without a word.
  if (credentials.length > 1) {
    refuse(
      `the call ${call.operation_id} carries ${credentials.length} secret references, ` +
        `and a call has one credential`,
    );
  }

  // A fact about a scalar field may be named anywhere on the call — after
  // the entries of another field, say — so they are placed once every field
  // is known.
  for (const token of strayFacts) {
    const owner = token.name.slice(0, token.name.indexOf("."));
    const field = scalars.get(owner);
    if (field === undefined) {
      refuse(`"${token.name}" is named under a field this call does not carry`);
    }
    const fact = factOf(token);
    if (fact !== null) field.facts.push(fact);
  }

  return {
    operationId: call.operation_id,
    readiness: call.readiness,
    credentials,
    fields,
  };
}

/** A value a call cannot be sent without, and why it has none here. */
export interface NotWritten {
  readonly name: string;
  readonly why: (Unconfigured | NotRenderable)["kind"];
}

/** Every token of a call this file cannot write a value for, by name and in
 * the order the call names them: one nothing configures, or one this
 * renderer cannot yet write. */
export function notWritten(call: Call): NotWritten[] {
  const found: NotWritten[] = [];
  for (const field of call.fields) {
    if (field.shape === "scalar") {
      if (field.token.binding.kind === "unconfigured") {
        found.push({ name: field.name, why: "unconfigured" });
      }
      continue;
    }
    for (const entry of field.entries) {
      const kind = entry.value?.binding.kind;
      if (kind === "unconfigured" || kind === "not_renderable") {
        found.push({ name: entry.value!.name, why: kind });
      }
    }
  }
  return found;
}

/** The parameters a call asks for, each once, in the order first named. */
export function parameters(call: Call): string[] {
  const names: string[] = [];
  const add = (token: Token | null) => {
    if (token?.binding.kind === "parameter" && !names.includes(token.binding.name)) {
      names.push(token.binding.name);
    }
  };
  for (const field of call.fields) {
    if (field.shape === "scalar") add(field.token);
    else field.entries.forEach((entry) => add(entry.value));
  }
  return names;
}

/** One declared fact out of several, by which fact it is. */
export function factNamed(facts: readonly Fact[], element: string): Json | undefined {
  return facts.find((fact) => fact.element === element)?.token.binding.value;
}

/** The literal a scalar field carries, or `undefined` for none. */
export function literalOf(call: Call, field: string): Json | undefined {
  const found = call.fields.find(
    (candidate): candidate is ScalarField =>
      candidate.shape === "scalar" && candidate.name === field,
  );
  return found?.token.binding.kind === "literal" ? found.token.binding.value : undefined;
}

/** A declared fact of a scalar field, or `undefined` where none is stated. */
export function factOfField(call: Call, field: string, element: string): Json | undefined {
  const found = call.fields.find(
    (candidate): candidate is ScalarField =>
      candidate.shape === "scalar" && candidate.name === field,
  );
  return found === undefined ? undefined : factNamed(found.facts, element);
}
