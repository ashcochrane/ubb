export function slugify(input: string): string {
  return input
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_|_$/g, "")
    .slice(0, 40);
}

export function slugifyWithSuffix(input: string): string {
  const base = slugify(input).slice(0, 36);
  const suffix = Math.floor(100 + Math.random() * 900);
  return `${base}_${suffix}`;
}
