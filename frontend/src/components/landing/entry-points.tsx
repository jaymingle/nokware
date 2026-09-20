import { ArrowRightIcon, KeyRoundIcon, MegaphoneIcon, MessageCircleQuestionIcon, ShieldIcon, TicketIcon } from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/utils";

import type { LucideIcon } from "lucide-react";

type Entry = {
  icon: LucideIcon;
  title: string;
  body: string;
  action: string;
  href: string;
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
    body: "Tell the Assembly about a blocked drain, uncollected refuse or a broken streetlight. It goes to the department responsible, and you follow it with your reference. Reports about someone's safety are handled privately.",
    action: "Report an issue",
    href: "/report",
    testId: "landing-report",
  },
  {
    icon: ShieldIcon,
    title: "Report abuse or a safety matter",
    body: "If someone is being hurt, threatened or is in danger, it goes privately to the Ghana Police Service and Social Welfare. It is never counted on the dashboard and never shown to anyone else.",
    action: "Report privately",
    href: "/report",
    testId: "landing-safety",
  },
  {
    icon: TicketIcon,
    title: "Check a case",
    body: "Enter the reference you were given when you reported. It shows how far along the case is and, once it is resolved, what was done.",
    action: "Check with a reference",
    href: "/report/status",
    testId: "landing-status",
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

function EntryCard({ entry, lead = false }: { entry: Entry; lead?: boolean }) {
  const Icon = entry.icon;
  return (
    <Link
      href={entry.href}
      className={cn(
        "group flex h-full flex-col items-start gap-4 rounded-xl border bg-card p-6 transition-colors hover:border-teal",
        lead && "border-teal/40 bg-teal-tint/40 sm:p-8",
      )}
      data-testid={entry.testId}
    >
      <span aria-hidden className={cn("grid place-items-center rounded-lg bg-teal-tint text-teal", lead ? "size-12" : "size-10")}>
        <Icon className={lead ? "size-6" : "size-5"} />
      </span>
      <div className="flex flex-1 flex-col gap-2">
        <h2 className={cn("leading-snug", lead ? "text-[28px] sm:text-[32px]" : "text-[22px]")}>{entry.title}</h2>
        <p className={cn("text-ink-soft", lead ? "max-w-[46ch] text-[16px]" : "text-[14.5px]")}>{entry.body}</p>
      </div>
      <span className={cn("inline-flex items-center gap-1.5 font-medium text-teal", lead ? "text-[15.5px]" : "text-[14px]")}>
        {entry.action}
        <ArrowRightIcon aria-hidden className="size-4 transition-transform group-hover:translate-x-0.5" />
      </span>
    </Link>
  );
}

// Weighted by who they are for: almost everyone comes for Ask, while the portal serves about twenty staff. Equal
// prominence told a first-time reader the wrong thing about what this is. Ask leads two columns of the first row;
// the other four fill the third column and the row beneath, so no card is left stranded on a line of its own.
export function EntryPoints() {
  const [ask, ...rest] = ENTRIES;
  return (
    <ul className="grid gap-4 sm:grid-cols-2 md:grid-cols-3">
      <li className="sm:col-span-2">
        <EntryCard entry={ask} lead />
      </li>
      {rest.map((entry) => (
        <li key={entry.testId}>
          <EntryCard entry={entry} />
        </li>
      ))}
    </ul>
  );
}
