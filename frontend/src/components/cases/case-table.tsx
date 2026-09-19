"use client";

import { StatusTag } from "@/components/status-tag";
import { useNow } from "@/hooks/use-now";
import { caseAge } from "@/lib/cases";
import { caseStatus } from "@/lib/status";
import { cn } from "@/lib/utils";
import { voicesTally } from "@/lib/voices";

import type { CaseSummary } from "@/lib/api/types";

const TH = "border-b px-3 py-2.5 text-left text-[12.5px] font-medium text-ink-soft sm:px-4";
const TD = "border-b px-3 py-3.5 align-top sm:px-4";
const WIDE_ONLY = "hidden md:table-cell";

type CaseTableProps = {
  cases: CaseSummary[];
  selected: string | null;
  onSelect: (caseId: string) => void;
  showRecipients?: boolean;
};

function Row({ summary, selected, onSelect, showRecipients, now }: { summary: CaseSummary; selected: boolean; onSelect: (id: string) => void; showRecipients: boolean; now: number }) {
  const tag = caseStatus(summary);
  return (
    <tr className={cn("transition-colors", selected ? "bg-teal-tint/60" : "hover:bg-paper-subtle")} aria-selected={selected}>
      <td className={`${TD} ${WIDE_ONLY} text-[12.5px] text-ink-soft tabular-nums`}>{summary.reference}</td>
      <td className={TD}>
        <button type="button" onClick={() => onSelect(summary.case_id)} className="w-full cursor-pointer text-left" data-testid={`case-row-${summary.case_id}`}>
          <span className="block text-[14.5px]">{summary.topic}</span>
          <span className="line-clamp-2 block text-[12.5px] text-ink-soft">
            {summary.excerpt ?? (summary.view === "oversight" ? "Private: only its recipients can read it." : "")}
          </span>
          <span className="block text-[12px] text-ink-soft">
            {[
              summary.place,
              `Severity ${summary.severity}`,
              showRecipients ? summary.recipients.join(" and ") : null,
              summary.voices ? voicesTally(summary.voices) : null,
            ].filter(Boolean).join(" · ")}
            <span className="md:hidden"> · {summary.reference}</span>
          </span>
        </button>
      </td>
      <td className={`${TD} text-[13px] tabular-nums`}>{caseAge(summary.submitted_at, now)}</td>
      <td className={TD}>
        <StatusTag tone={tag.tone} testId={`case-status-${summary.case_id}`}>{tag.label}</StatusTag>
      </td>
    </tr>
  );
}

export function CaseTable({ cases, selected, onSelect, showRecipients = false }: CaseTableProps) {
  const now = useNow();
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse" data-testid="case-table">
        <thead>
          <tr>
            <th className={`${TH} ${WIDE_ONLY} w-28`}>Case</th>
            <th className={TH}>Report</th>
            <th className={`${TH} w-16`}>Age</th>
            <th className={`${TH} w-32`}>Status</th>
          </tr>
        </thead>
        <tbody>
          {cases.map((summary) => (
            <Row key={summary.case_id} summary={summary} selected={selected === summary.case_id} onSelect={onSelect} showRecipients={showRecipients} now={now} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
