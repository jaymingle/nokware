import { EntryPoints } from "@/components/landing/entry-points";
import { Principles } from "@/components/landing/principles";
import { RecordFigures } from "@/components/landing/record-figures";

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: { absolute: "Nokware · Accra's public record" },
  description:
    "Ask questions of the Accra Metropolitan Assembly's published documents, with every answer cited, and report issues in your area.",
};

export default function HomePage() {
  return (
    <div className="mx-auto flex w-full max-w-[1120px] flex-col gap-12 sm:gap-16">
      {/* The figures sit beside the opening: it made four claims about the record and showed none of it. */}
      <section className="grid gap-8 pt-2 sm:pt-6 lg:grid-cols-[minmax(0,1fr)_300px] lg:items-start lg:gap-12">
        <div className="flex max-w-[64ch] flex-col gap-4">
          <h1 className="text-[36px] leading-[1.1] sm:text-[52px]">Accra&apos;s public record, in plain answers</h1>
          <p className="text-[17px] text-ink-soft">
            Nokware holds the documents the Assembly publishes (budgets, fees, bye-laws, plans and reports) and answers
            questions from them, citing the document every time. Residents can also tell the Assembly about problems in
            their area and follow each report to its resolution.
          </p>
        </div>
        <RecordFigures />
      </section>
      <EntryPoints />
      <Principles />
    </div>
  );
}
