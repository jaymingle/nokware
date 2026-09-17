/** A page's searchParams, as Next.js passes them. */
export type SearchParams = Promise<{ [key: string]: string | string[] | undefined }>;

/** The first value of a search param given once, several times or not at all. */
export function firstParam(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}
