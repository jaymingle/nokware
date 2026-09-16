"use client";

import { AreasMap } from "@/components/dashboard/areas-map";
import { AskPrompt, Panel, RecentDocuments, SubMetroTable, TopicShares } from "@/components/dashboard/dashboard-panels";
import { TrendChart } from "@/components/dashboard/trend-chart";
import { ErrorPanel, LoadingPanel } from "@/components/documents/panels";
import { IssueList } from "@/components/issues/issue-list";
import { useDashboard } from "@/lib/api/public-queries";
import { formatCount, formatDays, percent, periodLabel } from "@/lib/report/dashboard";
import { formatDateTime } from "@/lib/time";

import type { Dashboard } from "@/lib/api/types";

type Stat = { value: string; label: string; note: string; testId: string };

function stats(figures: Dashboard): Stat[] {
  const median = figures.median_days;
  return [
    { value: formatCount(figures.received), label: "reports received", note: periodLabel(figures.months), testId: "dashboard-received" },
    {
      value: formatCount(figures.resolved),
      label: "resolved",
      note: percent(figures.resolved, figures.received) ? `${percent(figures.resolved, figures.received)} of all reports` : "a share isn't given for fewer than 5",
      testId: "dashboard-resolved",
    },
    {
      value: median === null ? "–" : formatDays(median),
      label: "median days to resolve",
      note: median === null ? "shown once five reports are resolved" : "metro-wide",
      testId: "dashboard-median",
    },
    {
      value: figures.documents_published.toLocaleString(),
      label: "documents published",
      note: `across ${figures.departments_publishing} departments`,
      testId: "dashboard-documents-published",
    },
  ];
}

function StatCards({ figures }: { figures: Dashboard }) {
  return (
    <ul className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
      {stats(figures).map((stat) => (
        <li key={stat.label} className="rounded-xl border bg-card p-4 sm:p-[22px]" data-testid={stat.testId}>
          <div className="font-heading text-[38px] leading-none tabular-nums sm:text-[48px]" aria-label={stat.value === "<5" ? "fewer than 5" : undefined}>
            {stat.value}
          </div>
          <div className="mt-3 text-[13.5px]">{stat.label}</div>
          <div className="mt-0.5 text-[12px] text-ink-soft">{stat.note}</div>
        </li>
      ))}
    </ul>
  );
}

function Figures({ figures }: { figures: Dashboard }) {
  return (
    <div className="flex flex-col gap-5">
      <StatCards figures={figures} />
      <div className="flex flex-wrap items-start gap-5">
        <Panel title="Reports received and resolved" lead={`Monthly, ${periodLabel(figures.months)}. Bars: received. Line: resolved in the month. Dashed: fewer than 5.`} className="flex-[1_1_520px]">
          <TrendChart months={figures.months} />
        </Panel>
        <Panel title="By topic" lead="Share of all reports in the period." className="flex-[1_1_300px]">
          <TopicShares topics={figures.topics} total={figures.received} />
        </Panel>
      </div>
      <Panel
        title="Where reports come from"
        lead="The last twelve months, by sub-metro and by electoral area. Personal-safety reports are not counted here, and a count from 1 to 4 reads “fewer than 5”."
        testId="dashboard-areas"
      >
        <AreasMap subMetros={figures.sub_metros} areas={figures.electoral_areas} />
      </Panel>
      <div className="flex flex-wrap items-start gap-5">
        <Panel title="By sub-metro" lead="A median is shown once five of a sub-metro's reports are resolved." className="flex-[1_1_460px] px-0 sm:px-0 [&>h2]:px-5 [&>p]:px-5" testId="dashboard-sub-metro-panel">
          <SubMetroTable rows={figures.sub_metros} />
        </Panel>
        <div className="flex min-w-0 flex-[1_1_320px] flex-col gap-4">
          <Panel title="What the record holds">
            <RecentDocuments documents={figures.recent_documents} />
          </Panel>
          <AskPrompt />
        </div>
      </div>
    </div>
  );
}

/** The public dashboard: counts and trends only. Personal-safety reports are in none of them. */
export function DashboardPage() {
  const dashboard = useDashboard();
  return (
    <div className="mx-auto flex w-full max-w-[1120px] flex-col gap-8">
      <div className="flex max-w-[62ch] flex-col gap-3">
        <p className="text-[12.5px] text-ink-soft">
          Public record{dashboard.data ? ` · updated ${formatDateTime(dashboard.data.generated_at)}` : ""}
        </p>
        <h1 className="text-[34px] leading-tight sm:text-[46px]">The city, in the aggregate</h1>
        <p className="text-base text-ink-soft">
          What Accra&apos;s residents reported over the last twelve months, and what the Assembly resolved. Counts and
          trends only: no individual case, address or reporter appears here, and a count from 1 to 4 reads
          &ldquo;fewer than 5&rdquo;. Reports about a person&apos;s safety are handled privately and are not counted here at all.
        </p>
      </div>
      {dashboard.isPending ? <LoadingPanel label="Loading the figures…" /> : null}
      {dashboard.error ? <ErrorPanel message={dashboard.error.message} onRetry={() => dashboard.refetch()} /> : null}
      {dashboard.data ? <Figures figures={dashboard.data} /> : null}
      <IssueList />
    </div>
  );
}
