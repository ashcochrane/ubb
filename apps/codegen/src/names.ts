/**
 * Naming a generated function for the declared key it is about.
 *
 * Target-neutral: every target names its functions the same way, so the same
 * selection gives the same names whichever file a tenant is handed. This is
 * the renderer's naming and never a second spelling of the key, which is only
 * ever written as a literal.
 *
 * TWO KEYS THAT WOULD SHARE A NAME BOTH TAKE A SUFFIX that is a function of
 * the key. Neither keeps the plain name — so adding an Event Type can make an
 * existing function's name disappear, which a call site notices, and can never
 * hand that name to another Event Type, which it would not. A generated
 * function is never silently reattributed to another declared object, and the
 * rule is deliberately no more elaborate than that (ADR-0016 §2).
 */

/**
 * A declared key as the tail of a function name: its ASCII letters and
 * digits, and an underscore for everything else. Naming, not translation —
 * the key itself is only ever written as a literal.
 */
export function nameTail(key: string): string {
  return key.replace(/[^A-Za-z0-9]/g, "_");
}

/** Eight hexadecimal digits that are a function of `text` and nothing else. */
export function shortHash(text: string): string {
  let hash = 0x811c9dc5;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash.toString(16).padStart(8, "0");
}

/** A function to be named: the prefixes it is spelled under, and its key. */
export interface Wanted {
  readonly prefixes: readonly string[];
  /** `null` where no declared key names it. */
  readonly key: string | null;
}

/**
 * The tail of each wanted function's name — the part after its prefix — so
 * that no two functions share a name, and none takes a name in `fixed`.
 */
export function nameTails(
  wanted: readonly Wanted[],
  fixed: readonly string[],
  unkeyed: string,
): string[] {
  const plain = wanted.map((entry) => (entry.key === null ? null : nameTail(entry.key)));
  const names = (index: number, tail: string) =>
    wanted[index]!.prefixes.map((prefix) => `${prefix}_${tail}`);

  const count = new Map<string, number>();
  for (const name of fixed) count.set(name, 1);
  plain.forEach((tail, index) => {
    if (tail === null) return;
    for (const name of names(index, tail)) count.set(name, (count.get(name) ?? 0) + 1);
  });

  const taken = new Set<string>(fixed);
  const settled = plain.map((tail, index) => {
    if (tail === null) return null;
    const shared = names(index, tail).some((name) => (count.get(name) ?? 0) > 1);
    const own = shared ? `${tail}_${shortHash(wanted[index]!.key!)}` : tail;
    names(index, own).forEach((name) => taken.add(name));
    return own;
  });

  // A call with no declared key to be named for is named for its place. It
  // cannot run — it has no key because nothing is selected or declared — so
  // its name is not one a working call site depends on.
  return settled.map((tail, index) => {
    if (tail !== null) return tail;
    let own: string = unkeyed;
    for (let suffix = 2; names(index, own).some((name) => taken.has(name)); suffix += 1) {
      own = `${unkeyed}_${suffix}`;
    }
    names(index, own).forEach((name) => taken.add(name));
    return own;
  });
}
