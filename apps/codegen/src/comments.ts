/**
 * The two classes of comment a generated file carries, and no third.
 *
 * PROVENANCE is generated from the Blueprint, in one grammatical form:
 *
 *     <name> = <value>[ · <qualifier> <value>]...
 *
 * where every `<value>` is one line of JSON. A token's comment is its name,
 * its literal, and the declaration it was read from as `<object kind> <key>`;
 * a header line is the same form over a field of the document. Nothing else
 * about a Blueprint is ever written into a comment, so a comment cannot assert
 * a fact the document does not carry.
 *
 * CONTRACT is a member of the catalogue, written exactly as it stands there.
 *
 * Both are `#` comments in every file this package writes today.
 */
import type { BlueprintProvenance, Json } from "./blueprint.ts";
import { endsALine, oneLineJson } from "./python/syntax.ts";
import type { Literal, Token } from "./tokens.ts";

/** A name written into a comment: itself, unless it could end the line. */
function inline(name: string): string {
  return Array.from(name, (character) =>
    endsALine(character.charCodeAt(0))
      ? `\\u${character.charCodeAt(0).toString(16).padStart(4, "0")}`
      : character,
  ).join("");
}

/** One provenance statement: a name, its value, and what qualifies it. */
export function statement(
  name: string,
  value: Json,
  qualifiers: readonly (readonly [string, Json])[] = [],
): string {
  const tail = qualifiers
    .map(([qualifier, qualified]) => ` · ${qualifier} ${oneLineJson(qualified)}`)
    .join("");
  return `${inline(name)} = ${oneLineJson(value)}${tail}`;
}

/** The qualifiers that say which declaration a value was read from. */
export function declaredBy(
  provenance: BlueprintProvenance | null,
): (readonly [string, Json])[] {
  return provenance === null ? [] : [[provenance.object_kind, provenance.key]];
}

/** The qualifiers that say which publication, where there was one. */
export function publication(
  provenance: BlueprintProvenance,
): (readonly [string, Json])[] {
  const qualifiers: (readonly [string, Json])[] = [];
  if (provenance.published_revision != null) {
    qualifiers.push(["published_revision", provenance.published_revision]);
  }
  if (provenance.published_at != null) {
    qualifiers.push(["published_at", provenance.published_at]);
  }
  return qualifiers;
}

/** The comment beside one literal: what it is, and where it was declared. */
export function tokenStatement(token: Token<Literal>): string {
  return statement(token.name, token.binding.value, declaredBy(token.provenance));
}

/** Lines of comment text as `#` comments, at an indentation. */
export function hash(lines: readonly string[], indent = ""): string[] {
  return lines.map((line) => `${indent}# ${line}`);
}
