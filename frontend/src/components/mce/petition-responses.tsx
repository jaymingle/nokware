"use client";

import Link from "next/link";

import { RespondDialog } from "@/components/mce/respond-dialog";
import { Card } from "@/components/ui/card";
import { useNow } from "@/hooks/use-now";
import { useAwaitingResponses } from "@/lib/api/queries";
import { daysLeft, NO_RESPONSE, placeLine, signaturesLine, spacedCode } from "@/lib/petitions";
import { joinNames } from "@/lib/text";
import { formatDate } from "@/lib/time";

import type { AwaitingResponse } from "@/lib/api/types";

function ResponseCard({ petition, now }: { petition: AwaitingResponse; now: number }) {
  const left = daysLeft(petition.response_due, now);
  return (
    <Card className="gap-0 py-0" data-testid={`petition-response-${petition.code}`}>
      <div className="border-l-[3px] border-gold bg-gold-tint px-5 py-3 text-[14px]" data-testid={`petition-response-${petition.code}-due`}>
        {left > 0 ? (
          <>Respond publicly by <strong className="font-medium">{formatDate(petition.response_due)}</strong>: {left} {left === 1 ? "day" : "days"} left.
            If there&apos;s no response by then, the petition&apos;s page will say: &ldquo;{NO_RESPONSE}&rdquo;</>
        ) : (
          <>The 30 days ran out on {formatDate(petition.response_due)}. The petition&apos;s page says: &ldquo;{NO_RESPONSE}&rdquo;</>
        )}
      </div>
      <div className="flex flex-col gap-1.5 p-5">
        <p className="text-[12.5px] text-ink-soft">
          No. {spacedCode(petition.code)} · {petition.topic} · {placeLine(petition)} · concerns {joinNames(petition.departments)}
        </p>
        <Link href={`/petitions/${petition.code}`} className="text-[18px] leading-snug underline underline-offset-2" data-testid={`petition-response-${petition.code}-link`}>
          {petition.title}
        </Link>
        <p className="text-[13px] text-ink-soft">{signaturesLine(petition.signatures, petition.threshold)} · reached on {formatDate(petition.threshold_reached_at)}</p>
        <div className="pt-2"><RespondDialog petition={petition} late={left === 0} /></div>
      </div>
    </Card>
  );
}

export function PetitionResponses() {
  const now = useNow();
  const { data } = useAwaitingResponses();
  if (!data || data.length === 0) return null;
  return (
    <section aria-labelledby="responses-title" className="mt-8 flex flex-col gap-4" data-testid="petition-responses">
      <div className="flex flex-col gap-1">
        <h2 id="responses-title" className="text-[21px]">Waiting for your public response</h2>
        <p className="max-w-[70ch] text-[13.5px] text-ink-soft">
          These reached their signatures. Each petition&apos;s page counts down your 30 days to respond publicly: the
          Assembly will act, it&apos;s referred to a department, or it can&apos;t act, and why.
        </p>
      </div>
      {data.map((petition) => <ResponseCard key={petition.code} petition={petition} now={now} />)}
    </section>
  );
}
