import Link from "next/link";
import { ArrowRightIcon, KeyRoundIcon, MegaphoneIcon, MessageCircleQuestionIcon } from "lucide-react";

import { Tag } from "@/components/documents/tag";

import type { LucideIcon } from "lucide-react";

// Citizen reporting opens when the report form ships (Citizen Reports, R4).
const REPORTING_OPEN = false;

type Entry = {
  icon: LucideIcon;
  title: string;
  body: string;
  action: string;
  href: string | null;
  testId: string;
};

const ENTRIES: Entry[] = [
  {
    icon: MessageCircleQuestionIcon,
    title: "Ask a question",
    body: "Ask about a budget, a fee, a bye-law or a plan. Every answer names the documents it came from, and says so when the record is silent.",
    action: "Ask Nokware",
    href: "/ask",
    testId: "landing-ask",
  },
  {
    icon: MegaphoneIcon,
    title: "Report an issue",
    body: "Tell the Assembly about a blocked drain, uncollected refuse or a broken streetlight. It goes to the department responsible, and you can follow it with your case number.",
    action: "Report an issue",
    href: REPORTING_OPEN ? "/report" : null,
    testId: "landing-report",
  },
  {
    icon: KeyRoundIcon,
    title: "Institution portal",
    body: "For Assembly departments, verified contributors and the MCE: publish documents, review submissions and respond to disputes.",
    action: "Staff sign in",
    href: "/login",
    testId: "landing-portal",
  },
];

function EntryCard({ entry }: { entry: Entry }) {
  const Icon = entry.icon;
  const content = (
    <>
      <span aria-hidden className="grid size-10 place-items-center rounded-lg bg-teal-tint text-teal">
        <Icon className="size-5" />
      </span>
      <div className="flex flex-1 flex-col gap-2">
        <h2 className="text-[22px] leading-snug">{entry.title}</h2>
        <p className="text-[14.5px] text-ink-soft">{entry.body}</p>
      </div>
      {entry.href ? (
        <span className="inline-flex items-center gap-1.5 text-[14px] font-medium text-teal">
          {entry.action}
          <ArrowRightIcon aria-hidden className="size-4 transition-transform group-hover:translate-x-0.5" />
        </span>
      ) : (
        <Tag tone="neutral">Opening soon</Tag>
      )}
    </>
  );
  const frame = "flex h-full flex-col items-start gap-4 rounded-xl border bg-card p-6";
  if (!entry.href) {
    return (
      <div className={frame} data-testid={entry.testId} aria-disabled>
        {content}
      </div>
    );
  }
  return (
    <Link href={entry.href} className={`group ${frame} transition-colors hover:border-teal`} data-testid={entry.testId}>
      {content}
    </Link>
  );
}

/** The three ways in: Ask, report an issue, and the portal for staff. */
export function EntryPoints() {
  return (
    <ul className="grid gap-4 md:grid-cols-3">
      {ENTRIES.map((entry) => (
        <li key={entry.testId}>
          <EntryCard entry={entry} />
        </li>
      ))}
    </ul>
  );
}
