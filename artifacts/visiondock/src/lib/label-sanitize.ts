/**
 * Class names come from the VLM. The UI only trims and de-duplicates them —
 * it never decides whether a name is a "real" label.
 */
export function sanitizeLabels(names: string[]): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const raw of names) {
    const cleaned = String(raw ?? "").trim();
    if (!cleaned) continue;
    const key = cleaned.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(cleaned);
  }
  return out;
}

/** Strip a leading $ so a DollarSign icon does not double-prefix cost strings. */
export function stripLeadingDollar(cost: string | null | undefined): string {
  if (!cost) return "";
  return cost.replace(/^\$\s*/, "").trim();
}
