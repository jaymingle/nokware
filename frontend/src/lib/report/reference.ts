// Mirrors the API's reference format ("K7QM-4TXP"): no 0/O, 1/I/L, so it reads out clearly.
// Copied on purpose, for a check before any request: mirrors REFERENCE_ALPHABET in backend/app/services/report_rules.py.
const ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ";
const LENGTH = 8;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** A reference as typed ("k7qm 4txp") in canonical form, a case ID as given, or null if it can be neither. */
export function normaliseReference(typed: string): string | null {
  const trimmed = typed.trim();
  if (UUID.test(trimmed)) return trimmed.toLowerCase();
  const code = trimmed.replace(/[\s-]/g, "").toUpperCase();
  if (code.length !== LENGTH || [...code].some((char) => !ALPHABET.includes(char))) return null;
  return `${code.slice(0, 4)}-${code.slice(4)}`;
}
