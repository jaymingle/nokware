import Link from "next/link";
import { ArrowRightIcon, KeyRoundIcon, MegaphoneIcon, MessageCircleQuestionIcon } from "lucide-react";

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

/**
 * The ways in, weighted by who they are for. Ask is what almost everyone comes
 * for; the portal is for about twenty members of staff, and it had the same
 * size and prominence as Ask, which told a first-time reader the wrong thing
 * about what this is.
 */
export function EntryPoints() {
  const [ask, ...rest] = ENTRIES;
  return (
    <ul className="grid gap-4 md:grid-cols-3">
      <li className="md:col-span-2">
        <EntryCard entry={ask} lead />
      </li>
      {rest.map((entry) => (
        <li key={entry.testId} className="md:col-span-1 md:last:col-span-3">
          <EntryCard entry={entry} />
        </li>
      ))}
    </ul>
  );
}
