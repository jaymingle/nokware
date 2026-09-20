import type { ContactNumber, PublicContact } from "@/lib/api/types";

const GHANA = "233";

/** Short codes like 112 stay as they are. */
export function numberHref(number: ContactNumber): string {
  const digits = number.number.replace(/\D/g, "");
  if (number.kind === "whatsapp") return `https://wa.me/${digits.startsWith("0") ? GHANA + digits.slice(1) : digits}`;
  return `tel:${digits}`;
}

export function tierNote(contact: PublicContact): string {
  if (contact.tier === 1) return "National emergency line";
  if (contact.tier === 2) return "Official source";
  const via = contact.reported_via ? `Reported via ${contact.reported_via}` : "Reported on social media";
  const by = contact.reported_by ? ` by ${contact.reported_by}` : "";
  return `${via}${by}, not independently verified`;
}

export const TIERS: { tier: 1 | 2 | 3; title: string; body: string }[] = [
  { tier: 1, title: "National emergency lines", body: "Free numbers that work across Ghana. No source needed." },
  { tier: 2, title: "Official sources", body: "Listed on a government website, which is linked beside the number with the date we checked it." },
  { tier: 3, title: "Not independently verified", body: "Reported on social media or in the press only. Included because they may help, but use them with care." },
];

/** The services on the emergency page: whoever can help a person in danger, and no one else. */
export const EMERGENCY_SERVICES = ["emergency", "police", "fire", "ambulance", "disaster", "welfare"];
