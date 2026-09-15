/** A list of names as a sentence would give them: "Works", "Police and Social Welfare", "A, B and C". */
export function joinNames(names: string[]): string {
  if (names.length <= 1) return names[0] ?? "";
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

/** A label inside a sentence: its first letter lower-cased, every other letter (a proper noun's) left alone. */
export function lowerFirst(text: string): string {
  return text ? text[0].toLowerCase() + text.slice(1) : text;
}
