// src/features/reconciliation/components/day-labels.ts
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function getDayLabels(start: string, end: string): string[] {
  const labels: string[] = [];
  const s = new Date(start);
  const e = new Date(end);
  while (s <= e) {
    labels.push(`${s.getDate()} ${MONTHS[s.getMonth()]}`);
    s.setDate(s.getDate() + 1);
  }
  return labels;
}

export function buildEvenAllocations(start: string, end: string, amount: number): Record<string, number> {
  const labels = getDayLabels(start, end);
  if (labels.length === 0) return {};
  const perDay = Math.round((Math.abs(amount) / labels.length) * 100) / 100;
  const allocs: Record<string, number> = {};
  labels.forEach((l) => { allocs[l] = perDay; });
  return allocs;
}
