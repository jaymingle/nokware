import Link from "next/link";

import { StatusTag } from "@/components/status-tag";
import { closingLine, placeLine, progressPercent, responseLine, signaturesLine, spacedCode } from "@/lib/petitions";
import { petitionStatus } from "@/lib/status";
import { cn } from "@/lib/utils";

import type { PetitionCard as Card } from "@/lib/api/types";

export function Progress({ signatures, threshold, large = false }: { signatures: number; threshold: number | null; large?: boolean }) {
  const percent = progressPercent(signatures, threshold);
  return (
    <div className="flex flex-col gap-1.5">
      <div className={cn("overflow-hidden rounded-full bg-paper-subtle", large ? "h-2.5" : "h-1.5")} role="progressbar"
        aria-valuemin={0} aria-valuemax={threshold ?? 0} aria-valuenow={signatures} aria-label={signaturesLine(signatures, threshold)}>
        <div className="h-full rounded-full bg-teal" style={{ width: `${percent}%` }} />
      </div>
      <p className={cn("tabular-nums", large ? "text-[15px]" : "text-[12.5px] text-ink-soft")}>{signaturesLine(signatures, threshold)}</p>
    </div>
  );
}

export function PetitionCard({ petition, now }: { petition: Card; now: number }) {
  const tag = petitionStatus(petition.status);
  return (
    <li className="flex flex-col gap-2 border-b py-4 last:border-0" data-testid={`petition-${petition.code}`}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <Link href={`/petitions/${petition.code}`} className="text-[16px] font-medium underline underline-offset-2"
          data-testid={`petition-${petition.code}-link`}>
          {petition.title}
        </Link>
        <StatusTag tone={tag.tone} testId={`petition-${petition.code}-status`}>{tag.label}</StatusTag>
      </div>
      <p className="text-[12.5px] text-ink-soft">
        No. {spacedCode(petition.code)} · {petition.topic} · {placeLine(petition)}
      </p>
      <div className="max-w-sm"><Progress signatures={petition.signatures} threshold={petition.threshold} /></div>
      <p className="text-[12.5px] text-ink-soft">{responseLine(petition, now, "on its page") ?? closingLine(petition, now)}</p>
    </li>
  );
}
