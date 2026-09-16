import Link from "next/link";
import type { ReactNode } from "react";

import { CountValue } from "@/components/dashboard/count";
import { Button } from "@/components/ui/button";
import { ledgerFileUrl } from "@/lib/api/public";
import { formatDays, percent, type Count } from "@/lib/report/dashboard";
import { formatDate } from "@/lib/time";
import { cn } from "@/lib/utils";

import type { RecentDocument, SubMetroFigures, TopicFigures } from "@/lib/api/types";

export function Panel({ title, lead, children, className, testId }: {
  title: string; lead?: string; children: ReactNode; className?: string; testId?: string;
}) {
  return (
    <section className={cn("min-w-0 rounded-xl border bg-card p-5 sm:p-[22px]", className)} data-testid={testId}>
      <h2 className="text-[19px]">{title}</h2>
      {lead ? <p className="mt-1.5 text-[12.5px] text-ink-soft">{lead}</p> : null}
      <div className="mt-4">{children}</div>
    </section>
  );
}

/** Each topic's share of the period's reports, most reported first. */
export function TopicShares({ topics, total }: { topics: TopicFigures[]; total: Count }) {
  if (topics.length === 0) return <p className="text-[13.5px] text-ink-soft">No reports in this period yet.</p>;
  const top = Math.max(1, ...topics.map((t) => t.count ?? 0));
  return (
    <ul className="flex flex-col" data-testid="dashboard-topics">
      {topics.map((topic) => (
        <li key={topic.label} className="py-2.5">
          <div className="flex justify-between gap-3 text-[13.5px]">
            <span>{topic.label}</span>
            <span className="whitespace-nowrap text-ink-soft tabular-nums">
              <CountValue value={topic.count} />
              {percent(topic.count, total) ? ` · ${percent(topic.count, total)}` : null}
            </span>
          </div>
          <div className="mt-2 h-1 overflow-hidden rounded-sm bg-paper">
            {topic.count === null ? null : <div className="h-1 rounded-sm bg-teal" style={{ width: `${(topic.count / top) * 100}%` }} />}
          </div>
        </li>
      ))}
    </ul>
  );
}

/** Reports, resolutions and the median time to resolve, by sub-metro: no finer. */
export function SubMetroTable({ rows }: { rows: SubMetroFigures[] }) {
  const cell = "px-5 py-3 text-[13.5px] tabular-nums";
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left" data-testid="dashboard-sub-metros">
        <thead className="text-[12.5px] text-ink-soft">
          <tr className="border-b">
            <th scope="col" className="px-5 py-2.5 font-normal">Sub-metro</th>
            <th scope="col" className="px-5 py-2.5 font-normal">Reports</th>
            <th scope="col" className="px-5 py-2.5 font-normal">Resolved</th>
            <th scope="col" className="px-5 py-2.5 font-normal">Median days</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.name} className="border-b last:border-0">
              <th scope="row" className="px-5 py-3 text-[13.5px] font-normal">{row.name}</th>
              <td className={cn(cell, "text-ink-soft")}><CountValue value={row.reports} /></td>
              <td className={cn(cell, "text-ink-soft")}><CountValue value={row.resolved} /></td>
              <td className={cn(cell, "text-ink-soft")}>{row.median_days === null ? "–" : formatDays(row.median_days)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** The latest documents the Ledger published, each opening its PDF. */
export function RecentDocuments({ documents }: { documents: RecentDocument[] }) {
  return (
    <ul className="flex flex-col" data-testid="dashboard-documents">
      {documents.map((doc) => (
        <li key={doc.id} className="flex flex-wrap items-center gap-3 border-b py-3 last:border-0">
          <div className="min-w-0 flex-1 basis-48">
            <div className="text-[14.5px]">{doc.title}</div>
            <div className="text-[12px] text-ink-soft tabular-nums">
              {[doc.department_name, doc.published_at ? `published ${formatDate(doc.published_at)}` : null].filter(Boolean).join(" · ")}
            </div>
          </div>
          <a href={ledgerFileUrl(doc.id)} target="_blank" rel="noopener" className="text-[13px] whitespace-nowrap text-teal underline-offset-2 hover:underline"
            data-testid={`dashboard-document-${doc.id}`}>
            Read
          </a>
        </li>
      ))}
    </ul>
  );
}

export function AskPrompt() {
  return (
    <section className="rounded-xl border bg-teal-tint p-5 sm:p-[22px]">
      <h2 className="text-[21px]">A question about any of these?</h2>
      <p className="mt-2 mb-4 text-[13.5px] text-ink-soft">Ask Nokware and the answer comes back with the document and the date attached.</p>
      <Button asChild>
        <Link href="/ask" data-testid="dashboard-ask">Ask a question</Link>
      </Button>
    </section>
  );
}
