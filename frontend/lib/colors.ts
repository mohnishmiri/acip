import { categorical, otherColor } from "@/styles/tokens";

/**
 * Colour follows the entity, never its rank: once a key receives a slot it keeps it for the
 * session (per dimension) as long as no other visible key needs that slot. At most eight
 * categorical slots are ever used; "Other" is always neutral gray.
 */
const registry = new Map<string, Map<string, number>>();

export function assignColors(dimension: string, keys: string[]): Record<string, string> {
  let reg = registry.get(dimension);
  if (!reg) {
    reg = new Map();
    registry.set(dimension, reg);
  }
  const out: Record<string, string> = {};
  const used = new Set<number>();
  const pending: string[] = [];
  for (const k of keys) {
    if (k === "__other__") continue;
    const slot = reg.get(k);
    if (slot !== undefined && !used.has(slot)) {
      used.add(slot);
      out[k] = categorical[slot];
    } else pending.push(k);
  }
  for (const k of pending) {
    let slot = 0;
    while (used.has(slot) && slot < categorical.length) slot++;
    if (slot >= categorical.length) {
      out[k] = otherColor;
      continue;
    }
    used.add(slot);
    reg.set(k, slot);
    out[k] = categorical[slot];
  }
  out.__other__ = otherColor;
  return out;
}
