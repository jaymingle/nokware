"use client";

import { Children, isValidElement, useMemo, useState, type ReactNode } from "react";
import Markdown, { type Components } from "react-markdown";

import { CitationTag } from "@/components/ask/citation-tag";
import { CITATION_HREF_PREFIX, linkCitations } from "@/lib/ask/sources";

// Only what an answer needs; anything else (images, tables, raw HTML) is dropped
// or unwrapped to its text.
const ALLOWED = ["p", "strong", "em", "ul", "ol", "li", "a", "h1", "h2", "h3", "h4", "br", "blockquote", "code"];

/**
 * A list longer than this is folded, but only where the same rows are already
 * set out in full below, in the figures card and the chart. Forty-two
 * departments written out three times buries the chart under them; the answer
 * itself is untouched, and what is exported, read aloud and checked is the
 * whole of it.
 */
const LONG_LIST = 8;

type AnswerTextProps = {
  markdown: string;
  /** Source titles by label, for the citation tags' accessible names. */
  titles: Record<string, string>;
  onCite: (label: string) => void;
  testIdPrefix: string;
  /** Whether the figures below repeat these rows; only then is a long list folded. */
  repeatedBelow?: boolean;
};

function LongList({ items, testId }: { items: ReactNode[]; testId: string }) {
  const [open, setOpen] = useState(false);
  const hidden = items.length - LONG_LIST;
  return (
    <div className="flex flex-col gap-2">
      <ul className="flex list-disc flex-col gap-1.5 ps-5 marker:text-ink-muted">{open ? items : items.slice(0, LONG_LIST)}</ul>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="w-fit cursor-pointer text-[13.5px] text-teal underline underline-offset-2"
        data-testid={`${testId}-list-toggle`}
      >
        {open ? "Show fewer" : `Show the other ${hidden}`}
      </button>
      {open ? null : (
        <p className="text-[13px] text-ink-soft">
          All {items.length} are in the figures below, with the document they are read from.
        </p>
      )}
    </div>
  );
}

function useComponents({ titles, onCite, testIdPrefix, repeatedBelow }: Omit<AnswerTextProps, "markdown">): Components {
  return useMemo<Components>(() => {
    const heading: Components["h3"] = ({ children }) => <p className="mt-1 font-medium text-ink">{children}</p>;
    return {
      a: ({ href, children }) => {
        if (href?.startsWith(CITATION_HREF_PREFIX)) {
          const label = href.slice(CITATION_HREF_PREFIX.length);
          return <CitationTag label={label} title={titles[label]} onCite={onCite} testId={`${testIdPrefix}-cite-${label}`} />;
        }
        return (
          <a href={href} target="_blank" rel="noopener noreferrer" className="text-teal underline underline-offset-2">
            {children}
          </a>
        );
      },
      h1: heading,
      h2: heading,
      h3: heading,
      h4: heading,
      p: ({ children }) => <p>{children}</p>,
      ul: ({ children }) => {
        const items = Children.toArray(children).filter(isValidElement);
        if (!repeatedBelow || items.length <= LONG_LIST + 1) {
          return <ul className="flex list-disc flex-col gap-1.5 ps-5 marker:text-ink-muted">{children}</ul>;
        }
        return <LongList items={items} testId={testIdPrefix} />;
      },
      ol: ({ children }) => <ol className="flex list-decimal flex-col gap-1.5 ps-5 marker:text-ink-soft">{children}</ol>,
      li: ({ children }) => <li className="ps-1 [&>ul]:mt-1.5 [&>ol]:mt-1.5">{children}</li>,
      blockquote: ({ children }) => <blockquote className="border-s-2 border-hairline ps-3 text-ink-soft">{children}</blockquote>,
      code: ({ children }) => <code className="rounded bg-paper-subtle px-1 text-[0.92em]">{children}</code>,
    };
  }, [titles, onCite, testIdPrefix, repeatedBelow]);
}

/** The answer's markdown, rendered safely, with each [S#] as a tag linked to its source. */
export function AnswerText({ markdown, ...rest }: AnswerTextProps) {
  const components = useComponents(rest);
  return (
    <div className="flex flex-col gap-3 text-[15.5px] leading-[1.65] break-words text-ink" data-testid={`${rest.testIdPrefix}-answer`}>
      <Markdown allowedElements={ALLOWED} unwrapDisallowed skipHtml components={components}>
        {linkCitations(markdown)}
      </Markdown>
    </div>
  );
}
