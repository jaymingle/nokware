"use client";

import { CheckIcon, UsersIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { ErrorNote } from "@/components/documents/panels";
import { VoiceDialog } from "@/components/issues/voice-dialog";
import { StatusTag } from "@/components/status-tag";
import { Button } from "@/components/ui/button";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { useNow } from "@/hooks/use-now";
import { useIssues } from "@/lib/api/public-queries";
import { caseAge } from "@/lib/cases";
import { issueStage } from "@/lib/status";
import { joinNames } from "@/lib/text";
import { voicedIssues, voicesLine } from "@/lib/voices";

import type { Issue, IssuePage, Option } from "@/lib/api/types";

const PAGE = 10;

function IssueCard({ issue, voiced, onVoiced, now }: { issue: Issue; voiced: boolean; onVoiced: (id: string) => void; now: number }) {
  const place = [issue.ward, issue.sub_metro].filter(Boolean).join(", ");
  return (
    <li className="flex flex-wrap items-center gap-4 border-b py-4 last:border-0" data-testid={`issue-${issue.public_id}`}>
      <div className="flex min-w-0 flex-1 basis-64 flex-col gap-1">
        <p className="text-[15.5px]">{issue.topic}{place ? <span className="text-ink-soft"> · {place}</span> : null}</p>
        <p className="flex flex-wrap items-center gap-2 text-[12.5px] text-ink-soft">
          <StatusTag tone={issueStage(issue.stage).tone}>{issueStage(issue.stage).label}</StatusTag>
          with {joinNames(issue.departments)} · reported {caseAge(issue.filed_at, now)} ago
        </p>
        <p className="flex items-center gap-1.5 text-[13px]" data-testid={`issue-${issue.public_id}-voices`}>
          <UsersIcon aria-hidden className="size-3.5 text-teal" />
          {voicesLine(issue.voices)}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {voiced ? (
          <span className="inline-flex items-center gap-1.5 text-[13px] text-teal" data-testid={`issue-${issue.public_id}-voiced`}>
            <CheckIcon aria-hidden className="size-4" /> You added your voice
          </span>
        ) : (
          <VoiceDialog issue={issue} onAdded={() => onVoiced(issue.public_id)} />
        )}
        <Button asChild variant="ghost" size="sm">
          <Link href={`/petitions/new?issue=${issue.public_id}`} data-testid={`issue-${issue.public_id}-petition`}>Start a petition</Link>
        </Button>
      </div>
    </li>
  );
}

function Filter({ label, value, options, onChange, testId, all }: {
  label: string; value: string; options: Option[]; onChange: (v: string) => void; testId: string; all: string;
}) {
  return (
    <NativeSelect value={value} onChange={(e) => onChange(e.target.value)} aria-label={label} size="sm" data-testid={testId}>
      <NativeSelectOption value="">{all}</NativeSelectOption>
      {options.map((o) => <NativeSelectOption key={o.id} value={o.id}>{o.name}</NativeSelectOption>)}
    </NativeSelect>
  );
}

function useVoiced(): [Set<string>, (id: string) => void] {
  // Read once in the browser. Cards render only after the list loads there, so the server's empty set never shows.
  const [voiced, setVoiced] = useState<Set<string>>(() => (typeof window === "undefined" ? new Set() : voicedIssues()));
  return [voiced, (id) => setVoiced((current) => new Set([...current, id]))];
}

function Paging({ page, offset, onOffset }: { page: IssuePage; offset: number; onOffset: (n: number) => void }) {
  if (page.total <= PAGE) return null;
  return (
    <div className="flex items-center gap-3 pt-3 text-[13px] text-ink-soft">
      <Button variant="secondary" size="sm" disabled={offset === 0} onClick={() => onOffset(offset - PAGE)} data-testid="issues-previous">Previous</Button>
      <span>{offset + 1}–{Math.min(offset + PAGE, page.total)} of {page.total}</span>
      <Button variant="secondary" size="sm" disabled={offset + PAGE >= page.total} onClick={() => onOffset(offset + PAGE)} data-testid="issues-next">Next</Button>
    </div>
  );
}

export function IssueList() {
  const [subMetro, setSubMetro] = useState("");
  const [topic, setTopic] = useState("");
  const [offset, setOffset] = useState(0);
  const [voiced, markVoiced] = useVoiced();
  const now = useNow();
  const { data, error } = useIssues({ subMetro, topic, limit: PAGE, offset });
  const filter = (set: (v: string) => void) => (value: string) => { set(value); setOffset(0); };
  return (
    <section aria-labelledby="issues-title" className="flex flex-col gap-3 rounded-xl border bg-card p-5 sm:p-[22px]" data-testid="dashboard-issues">
      <div className="flex flex-wrap items-baseline gap-3">
        <h2 id="issues-title" className="text-[21px]">Issues residents have raised</h2>
        {data ? <span className="text-[12.5px] text-ink-soft">{data.total} open</span> : null}
      </div>
      <p className="max-w-[70ch] text-[13px] text-ink-soft">
        Open everyday problems residents have reported. If one affects you too, say so: the department handling it sees how
        many residents it affects. Only the topic and area are shown, never what the resident wrote.
      </p>
      <div className="flex flex-wrap gap-2">
        <Filter label="Sub-metro" value={subMetro} options={data?.sub_metros ?? []} onChange={filter(setSubMetro)} testId="issues-sub-metro" all="All sub-metros" />
        <Filter label="Topic" value={topic} options={data?.topics ?? []} onChange={filter(setTopic)} testId="issues-topic" all="All topics" />
      </div>
      {error ? <ErrorNote>{error.message}</ErrorNote> : null}
      {data && data.issues.length === 0 ? <p className="py-3 text-[13.5px] text-ink-soft">No open issues match.</p> : null}
      <ul>{data?.issues.map((issue) => <IssueCard key={issue.public_id} issue={issue} voiced={voiced.has(issue.public_id)} onVoiced={markVoiced} now={now} />)}</ul>
      {data ? <Paging page={data} offset={offset} onOffset={setOffset} /> : null}
    </section>
  );
}
