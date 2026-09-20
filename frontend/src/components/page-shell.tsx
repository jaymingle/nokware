import { cn } from "@/lib/utils";

import type { ReactNode } from "react";

/**
 * The two widths a page may take, chosen by the page: reading for prose, forms
 * and single-column lists; data for the dashboard, the accountability tables
 * and the portal's queues. There is no third width and no per-page override.
 */
export type PageWidth = "reading" | "data";

const WIDTH: Record<PageWidth, string> = {
  reading: "max-w-3xl",
  data: "max-w-[1120px]",
};

/**
 * What a page spends above and below itself. Exported because /ask fills the
 * page with its chat instead of heading it, and has to spend the same.
 */
export const PAGE_PADDING = "pt-8 pb-10 sm:pt-10";

type PageShellProps = {
  /** The small label above the title, where the reader is (e.g. "Accountability"). */
  eyebrow?: ReactNode;
  /** The page's only h1. Everything below it is an h2. */
  title: ReactNode;
  /** One paragraph saying what the page is for. */
  lead?: ReactNode;
  /** Links or buttons belonging to the page as a whole, not to a section of it. */
  actions?: ReactNode;
  /** Something that belongs beside the heading rather than under it — the landing page's record figures, which
      answer the claim the title makes. It stacks under the heading on a phone. */
  aside?: ReactNode;
  width?: PageWidth;
  children?: ReactNode;
};

/**
 * The column a page occupies, without a heading: for the moment before a page
 * whose title is its subject's (a petition's) knows what that title is.
 */
export function PageColumn({ width = "reading", children }: { width?: PageWidth; children?: ReactNode }) {
  return <div className={cn("mx-auto flex w-full flex-col gap-7", WIDTH[width], PAGE_PADDING)}>{children}</div>;
}

/**
 * Every page is headed the same way: one h1 in the same place, at one of two
 * widths, with one spacing scale between the parts.
 */
export function PageShell({ eyebrow, title, lead, actions, aside, width = "reading", children }: PageShellProps) {
  return (
    <PageColumn width={width}>
      <div className={cn("flex flex-col gap-7", aside && "md:flex-row md:items-start md:justify-between md:gap-10")}>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            {/* A div, not a p: sign-in's eyebrow is the brand mark, which is not phrasing content. */}
            {eyebrow ? <div className="text-[12.5px] text-ink-soft">{eyebrow}</div> : null}
            <h1 className="text-[32px] leading-tight sm:text-[40px]">{title}</h1>
          </div>
          {lead ? <div className="max-w-[62ch] text-base text-ink-soft">{lead}</div> : null}
          {actions ? <div className="flex flex-wrap items-center gap-3">{actions}</div> : null}
        </div>
        {aside ? <div className="md:w-[19rem] md:shrink-0">{aside}</div> : null}
      </div>
      {children}
    </PageColumn>
  );
}
