"use client";

import Link from "next/link";

import { useDashboard, usePublishingRecord } from "@/lib/api/public-queries";

/**
 * What the record actually holds, on the page that makes claims about it.
 *
 * The landing page asserted four things about Nokware and showed no evidence
 * for any of them. These are the live figures, the same ones the dashboard and
 * the publishing record show, so the claims can be checked in one glance — the
 * gap included, which is the figure the Assembly would rather not lead with.
 *
 * Every figure is a link to where it comes from. If either call fails the panel
 * simply isn't there: a landing page must not break because a count didn't load.
 */
type Figure = { value: string; label: string; href: string; testId: string };

function figures(documents?: number, departments?: number, missing?: number, due?: number): Figure[] {
  const found: Figure[] = [];
  if (documents !== undefined) {
    found.push({
      value: documents.toLocaleString(),
      label: departments ? `documents held, from ${departments} departments` : "documents held",
      href: "/accountability/documents",
      testId: "landing-figure-documents",
    });
  }
  if (missing !== undefined && due !== undefined) {
    found.push({
      value: missing.toLocaleString(),
      // "we would expect", as the record itself says it: the list of required documents is Nokware's own.
      label: `of the ${due} documents we would expect are not there`,
      href: "/accountability/documents",
      testId: "landing-figure-missing",
    });
  }
  return found;
}

export function RecordFigures() {
  const dashboard = useDashboard();
  const record = usePublishingRecord();
  const shown = figures(
    dashboard.data?.documents_published,
    dashboard.data?.departments_publishing,
    record.data?.summary.missing,
    record.data?.summary.due,
  );
  if (!shown.length) return null;
  return (
    <aside aria-label="What the record holds" className="flex flex-col gap-3 rounded-xl border bg-card p-5" data-testid="landing-figures">
      <p className="text-[12px] font-medium tracking-wide text-ink-soft uppercase">What the record holds</p>
      <ul className="flex flex-col gap-4">
        {shown.map((figure) => (
          <li key={figure.testId}>
            <Link href={figure.href} className="group flex flex-col gap-0.5" data-testid={figure.testId}>
              <span className="font-heading text-[34px] leading-none tabular-nums group-hover:text-teal">{figure.value}</span>
              <span className="text-[13.5px] text-ink-soft">{figure.label}</span>
            </Link>
          </li>
        ))}
      </ul>
      <p className="border-t pt-3 text-[12.5px] text-ink-soft">
        Counted from the Ledger against what the Assembly is required to publish.{" "}
        <Link href="/accountability/documents" className="text-teal underline underline-offset-2" data-testid="landing-figures-record">
          See the record
        </Link>
      </p>
    </aside>
  );
}
