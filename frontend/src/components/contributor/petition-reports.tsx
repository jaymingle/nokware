"use client";

import Link from "next/link";

import { DismissReportDialog } from "@/components/contributor/dismiss-report-dialog";
import { RemoveCommentDialog } from "@/components/contributor/remove-comment-dialog";
import { RemovePetitionDialog } from "@/components/contributor/remove-petition-dialog";
import { ReportedImages } from "@/components/contributor/reported-images";
import { EmptyPanel, ErrorPanel, LoadingPanel } from "@/components/documents/panels";
import { Progress } from "@/components/petitions/petition-card";
import { StatusTag } from "@/components/status-tag";
import { Card } from "@/components/ui/card";
import { usePetitionReports } from "@/lib/api/queries";
import { placeLine, spacedCode, startedBy } from "@/lib/petitions";
import { petitionStatus } from "@/lib/status";
import { joinNames, plural, times } from "@/lib/text";
import { formatDateTime } from "@/lib/time";

import type { PetitionGroundOption, PetitionDismissalOption, PetitionReport, ReportedComment } from "@/lib/api/types";

function Reported({ report }: { report: PetitionReport }) {
  const others = report.reports_on_this_petition - 1;
  return (
    <div className="border-l-[3px] border-gold bg-gold-tint px-5 py-3 text-[14px]" data-testid={`report-${report.id}-ground`}>
      <p>
        Reported as: <strong className="font-medium">{report.ground_words}</strong>
        {report.duplicate_of ? <> · of petition {spacedCode(report.duplicate_of)}</> : null}
      </p>
      <p className="text-[12.5px] text-ink-soft">
        {formatDateTime(report.reported_at)}
        {others > 0 ? ` · ${plural(report.reports_on_this_petition, "report", "reports")} on this petition, ${others} still waiting` : " · the only report on this petition"}
      </p>
    </div>
  );
}

function Petition({ report }: { report: PetitionReport }) {
  const petition = report.petition;
  const tag = petitionStatus(petition.status);
  return (
    <>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <Link href={`/petitions/${petition.code}`} className="text-[18px] leading-snug underline underline-offset-2"
          data-testid={`report-${report.id}-link`}>
          {petition.title}
        </Link>
        <StatusTag tone={tag.tone} testId={`report-${report.id}-status`}>{tag.label}</StatusTag>
      </div>
      <p className="text-[12.5px] text-ink-soft">
        No. {spacedCode(petition.code)} · {petition.topic} · {placeLine(petition)} · concerns {joinNames(petition.departments)} · {startedBy(petition.started_by)}
      </p>
      <div className="max-w-sm"><Progress signatures={petition.signatures} threshold={petition.threshold} /></div>
      {petition.removals > 0 ? (
        <p className="text-[13px] text-ink-soft" data-testid={`report-${report.id}-removals`}>
          Taken down {times(petition.removals)} before, then mended and published again.
        </p>
      ) : null}
    </>
  );
}

type CardProps = {
  report: PetitionReport; grounds: PetitionGroundOption[]; imageGrounds: PetitionGroundOption[];
  reasons: PetitionDismissalOption[];
};

function ReportCard({ report, grounds, imageGrounds, reasons }: CardProps) {
  return (
    <Card className="gap-0 py-0" data-testid={`report-${report.id}`}>
      <Reported report={report} />
      <div className="flex flex-col gap-3 p-5">
        <Petition report={report} />
        {report.note ? (
          <p className="rounded-lg bg-paper-subtle px-3 py-2 text-[13.5px]" data-testid={`report-${report.id}-note`}>
            What the reader added: &ldquo;{report.note}&rdquo;
          </p>
        ) : null}
        <ReportedImages code={report.petition.code} images={report.images} grounds={imageGrounds} />
        <div className="flex flex-wrap gap-2 pt-1">
          <RemovePetitionDialog code={report.petition.code} grounds={grounds} />
          <DismissReportDialog id={report.id} reasons={reasons} />
        </div>
      </div>
    </Card>
  );
}

/** `grounds` here are the comment wording: the same stored ids, but a duplicate repeats another comment. */
function CommentCard({ report, grounds, reasons }: {
  report: ReportedComment; grounds: PetitionGroundOption[]; reasons: PetitionDismissalOption[];
}) {
  const others = report.reports_on_this_comment - 1;
  return (
    <Card className="gap-0 py-0" data-testid={`comment-report-${report.id}`}>
      <div className="border-l-[3px] border-gold bg-gold-tint px-5 py-3 text-[14px]">
        <p>Reported as: <strong className="font-medium">{report.ground_words}</strong></p>
        <p className="text-[12.5px] text-ink-soft">
          {formatDateTime(report.reported_at)}
          {others > 0 ? ` · ${plural(report.reports_on_this_comment, "report", "reports")} on this comment` : " · the only report on this comment"}
        </p>
      </div>
      <div className="flex flex-col gap-3 p-5">
        <p className="text-[12.5px] text-ink-soft">
          A comment under petition{" "}
          <Link href={`/petitions/${report.code}`} className="underline underline-offset-2"
            data-testid={`comment-report-${report.id}-link`}>
            {spacedCode(report.code)}
          </Link>
          {" "}· {report.comment.name ?? "Resident"} · {formatDateTime(report.comment.at)}
        </p>
        <p className="rounded-lg bg-paper-subtle px-3 py-2 text-[14px] whitespace-pre-line"
          data-testid={`comment-report-${report.id}-text`}>
          {report.comment.text}
        </p>
        {report.note ? (
          <p className="text-[13.5px]" data-testid={`comment-report-${report.id}-note`}>
            What the reader added: &ldquo;{report.note}&rdquo;
          </p>
        ) : null}
        <div className="flex flex-wrap gap-2 pt-1">
          <RemoveCommentDialog code={report.code} commentId={report.comment.id} grounds={grounds} />
          <DismissReportDialog id={report.id} reasons={reasons} about="comment" />
        </div>
      </div>
    </Card>
  );
}

/** Reported petitions and reported comments, newest first. Nothing here hides either: both stay up until they
 * come down on a ground. */
export function PetitionReports() {
  const { data, error, isPending, refetch } = usePetitionReports();
  if (isPending) return <LoadingPanel label="Loading reported petitions…" />;
  if (error) return <ErrorPanel message={error.message} onRetry={() => void refetch()} />;
  if (data.reports.length === 0 && data.comments.length === 0) {
    return (
      <EmptyPanel title="Nothing has been reported">
        When a reader reports a petition or a comment under one, it appears here with the ground they gave. It stays
        up while you read it.
      </EmptyPanel>
    );
  }
  return (
    <div className="flex flex-col gap-6">
      {data.reports.length > 0 ? (
        <section aria-label="Reported petitions" className="flex flex-col gap-4">
          {data.reports.map((report) => (
            <ReportCard key={report.id} report={report} grounds={data.grounds} imageGrounds={data.image_grounds}
              reasons={data.dismissal_reasons} />
          ))}
        </section>
      ) : null}
      {data.comments.length > 0 ? (
        <section aria-label="Reported comments" className="flex flex-col gap-4">
          <h2 className="text-[17px]">Reported comments</h2>
          {data.comments.map((report) => (
            <CommentCard key={report.id} report={report} grounds={data.comment_grounds} reasons={data.dismissal_reasons} />
          ))}
        </section>
      ) : null}
    </div>
  );
}
