"use client";

import { useMemo } from "react";
import Markdown, { type Components } from "react-markdown";

import { CitationTag } from "@/components/ask/citation-tag";
import { CITATION_HREF_PREFIX, linkCitations } from "@/lib/ask/sources";

// Only what an answer needs; anything else (images, tables, raw HTML) is dropped
// or unwrapped to its text.
const ALLOWED = ["p", "strong", "em", "ul", "ol", "li", "a", "h1", "h2", "h3", "h4", "br", "blockquote", "code"];

type AnswerTextProps = {
  markdown: string;
  /** Source titles by label, for the citation tags' accessible names. */
  titles: Record<string, string>;
  onCite: (label: string) => void;
  testIdPrefix: string;
};

function useComponents({ titles, onCite, testIdPrefix }: Omit<AnswerTextProps, "markdown">): Components {
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
      ul: ({ children }) => <ul className="flex list-disc flex-col gap-1.5 pl-5 marker:text-ink-muted">{children}</ul>,
      ol: ({ children }) => <ol className="flex list-decimal flex-col gap-1.5 pl-5 marker:text-ink-soft">{children}</ol>,
      li: ({ children }) => <li className="pl-1 [&>ul]:mt-1.5 [&>ol]:mt-1.5">{children}</li>,
      blockquote: ({ children }) => <blockquote className="border-l-2 border-hairline pl-3 text-ink-soft">{children}</blockquote>,
      code: ({ children }) => <code className="rounded bg-paper-subtle px-1 text-[0.92em]">{children}</code>,
    };
  }, [titles, onCite, testIdPrefix]);
}

/** The answer's markdown, rendered safely, with each [S#] as a tag linked to its source. */
export function AnswerText({ markdown, ...rest }: AnswerTextProps) {
  const components = useComponents(rest);
  return (
    <div className="flex flex-col gap-3 text-[15.5px] leading-[1.65] text-ink" data-testid={`${rest.testIdPrefix}-answer`}>
      <Markdown allowedElements={ALLOWED} unwrapDisallowed skipHtml components={components}>
        {linkCitations(markdown)}
      </Markdown>
    </div>
  );
}
