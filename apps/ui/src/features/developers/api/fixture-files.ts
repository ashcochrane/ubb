// What the two mock modules that read platform-written fixtures share (#579,
// #581): naming a lazily loaded file, and the field-by-field reading that lets
// a JSON document become a typed answer without a cast.
//
// Each module still makes its own `import.meta.glob` call: Vite resolves the
// pattern at build time and needs it written as a literal at the call.

/** A glob's lazy loaders, keyed by each file's name without its extension. */
export function loadersByName<T>(loaders: Record<string, () => Promise<T>>): Map<string, () => Promise<T>> {
  return new Map(
    Object.entries(loaders).map(([path, load]) => [
      path.slice(path.lastIndexOf("/") + 1).replace(/\.json$/, ""),
      load,
    ]),
  );
}

export function isRecord(value: unknown): value is object {
  return typeof value === "object" && value !== null;
}

/** One member of a parsed document, read without asserting its type. */
export const field = (value: object, name: string): unknown => Reflect.get(value, name);

export function isOneOf<T extends string>(values: readonly T[], value: unknown): value is T {
  return values.some((member) => member === value);
}
