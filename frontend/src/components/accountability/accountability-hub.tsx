import Link from "next/link";

import { PageIntro } from "@/components/portal/page-intro";

const PAGES = [
  {
    href: "/accountability/documents",
    title: "What the Assembly publishes",
    body: "The documents it is required to publish, against what The Ledger holds, year by year: the gaps as well as the contents.",
    testId: "accountability-documents-link",
  },
  {
    href: "/accountability/departments",
    title: "How departments respond",
    body: "How quickly each department starts and resolves what residents report, and how it handles contributors' documents.",
    testId: "accountability-departments-link",
  },
];

export function AccountabilityHub() {
  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-7">
      <PageIntro eyebrow="Accountability" title="Holding the Assembly to its own record">
        What the Accra Metropolitan Assembly has published and what it hasn&apos;t, and how its departments respond to residents.
      </PageIntro>
      <ul className="grid gap-4 md:grid-cols-2">
        {PAGES.map((page) => (
          <li key={page.href}>
            <Link href={page.href} className="flex h-full flex-col gap-2 rounded-xl border bg-card p-5 transition-colors hover:border-teal" data-testid={page.testId}>
              <span className="text-[19px]">{page.title}</span>
              <span className="text-[14px] text-ink-soft">{page.body}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
