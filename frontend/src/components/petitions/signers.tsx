"use client";

import { Button } from "@/components/ui/button";
import { useSignerNames } from "@/lib/api/petition-queries";
import { formatDate } from "@/lib/time";

/** Who has signed: the names signers chose to show, and how many signed anonymously. Never a number. */
export function Signers({ code, signatures }: { code: string; signatures: number }) {
  const names = useSignerNames(code);
  const pages = names.data?.pages ?? [];
  const named = pages[0]?.total ?? 0;
  const anonymous = Math.max(0, signatures - named);
  if (signatures === 0) return null;
  return (
    <section className="flex flex-col gap-3 rounded-xl border bg-card p-5" data-testid="petition-signers">
      <h2 className="text-[19px]">Who has signed</h2>
      <p className="text-[13.5px] text-ink-soft" data-testid="petition-signers-summary">
        {named.toLocaleString()} with their name shown · {anonymous.toLocaleString()} anonymously. Each is a confirmed Ghanaian number, once.
      </p>
      {named > 0 ? (
        <ul className="grid gap-x-6 gap-y-1 text-[13.5px] sm:grid-cols-2">
          {pages.flatMap((page) => page.names).map((signer, i) => (
            <li key={`${signer.signed_at}-${i}`} className="flex justify-between gap-3 border-b border-dashed py-1">
              <span>{signer.name}</span>
              <span className="text-[12px] text-ink-muted tabular-nums">{formatDate(signer.signed_at)}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {names.hasNextPage ? (
        <Button variant="secondary" size="sm" className="w-fit" disabled={names.isFetchingNextPage} onClick={() => void names.fetchNextPage()} data-testid="petition-signers-more">
          Show more names
        </Button>
      ) : null}
    </section>
  );
}
