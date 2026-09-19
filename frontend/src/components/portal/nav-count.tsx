"use client";

import { useNow } from "@/hooks/use-now";
import { useAwaitingResponses, useCaseOversight, useCaseQueue, useEscalations, usePetitionReports, useReviewQueue, useSubmissions } from "@/lib/api/queries";
import { openForMe } from "@/lib/cases";
import { awaitingResponse, splitByClock, splitHeld } from "@/lib/documents";
import { cn } from "@/lib/utils";

import type { NavCountKind } from "@/lib/portal/navigation";

function Count({ value, active, testId }: { value: number; active: boolean; testId: string }) {
  if (value === 0) return null;
  return (
    <span
      data-testid={testId}
      aria-label={`${value} waiting`}
      className={cn(
        "ml-1.5 inline-grid min-w-5 place-items-center rounded-md px-1 text-[11.5px] font-medium tabular-nums",
        active ? "bg-teal text-paper" : "bg-gold-tint text-ink",
      )}
    >
      {value}
    </span>
  );
}

/** Only documents whose clock is still running: the rest publish on their own. */
function ReviewCount({ active }: { active: boolean }) {
  const now = useNow();
  const { data } = useReviewQueue();
  const open = data ? splitHeld(data, now).open.length : 0;
  return <Count value={open} active={active} testId="nav-count-review" />;
}

function ResponsesCount({ active }: { active: boolean }) {
  const { data } = useSubmissions();
  return <Count value={data ? awaitingResponse(data).length : 0} active={active} testId="nav-count-responses" />;
}

/** Only escalations whose clock is still running: the rest publish on their own. */
function EscalationsCount({ active }: { active: boolean }) {
  const now = useNow();
  const { data } = useEscalations();
  const open = data ? splitByClock(data, now).open.length : 0;
  return <Count value={open} active={active} testId="nav-count-escalations" />;
}

function CasesCount({ active }: { active: boolean }) {
  const { data } = useCaseQueue();
  return <Count value={data ? openForMe(data.cases) : 0} active={active} testId="nav-count-cases" />;
}

function CaseEscalationsCount({ active }: { active: boolean }) {
  const { data } = useCaseOversight();
  return <Count value={data?.stats.escalated ?? 0} active={active} testId="nav-count-case-escalations" />;
}

/** Only what the MCE owes: petitions that reached their signatures and are waiting for a public response. */
function PetitionsCount({ active }: { active: boolean }) {
  const { data } = useAwaitingResponses();
  return <Count value={data?.length ?? 0} active={active} testId="nav-count-petitions" />;
}

function PetitionReportsCount({ active }: { active: boolean }) {
  const { data } = usePetitionReports();
  return <Count value={data?.reports.length ?? 0} active={active} testId="nav-count-petition-reports" />;
}

export function NavCount({ kind, active }: { kind: NavCountKind; active: boolean }) {
  if (kind === "review") return <ReviewCount active={active} />;
  if (kind === "responses") return <ResponsesCount active={active} />;
  if (kind === "escalations") return <EscalationsCount active={active} />;
  if (kind === "cases") return <CasesCount active={active} />;
  if (kind === "case-escalations") return <CaseEscalationsCount active={active} />;
  if (kind === "petitions") return <PetitionsCount active={active} />;
  if (kind === "petition-reports") return <PetitionReportsCount active={active} />;
  return null;
}
