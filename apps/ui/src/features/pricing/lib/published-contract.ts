/**
 * What the committed contract publishes for one of this feature's requests —
 * read off `src/api/schema.json`, the snapshot every console type is generated
 * from (#545, #546; W5 ruling 16).
 *
 * The pricing forms' payload pins compare what a form SENDS against this,
 * rather than against a list written beside them: a selector the server gains
 * is one the published contract gains, so a form that does not send it fails
 * the pin instead of silently leaving it out. Read by tests only.
 */

function contract(): unknown {
  const [document] = Object.values(
    import.meta.glob("/src/api/schema.json", { eager: true, import: "default" }),
  );
  return document;
}

function at(node: unknown, ...keys: string[]): unknown {
  return keys.reduce<unknown>(
    (current, key) =>
      typeof current === "object" && current !== null ? Reflect.get(current, key) : undefined,
    node,
  );
}

/** The query parameters one GET operation publishes, by the path's ending. */
export function publishedQueryParameters(pathEnding: string): string[] {
  const paths = at(contract(), "paths");
  const path = Object.keys(typeof paths === "object" && paths !== null ? paths : {}).find(
    (key) => key.endsWith(pathEnding),
  );
  const parameters = path === undefined ? [] : at(paths, path, "get", "parameters");
  return (Array.isArray(parameters) ? parameters : [])
    .filter((parameter) => at(parameter, "in") === "query")
    .map((parameter) => String(at(parameter, "name")));
}

/** The properties one published schema declares. */
export function publishedProperties(schema: string): string[] {
  const properties = at(contract(), "components", "schemas", schema, "properties");
  return Object.keys(typeof properties === "object" && properties !== null ? properties : {});
}
