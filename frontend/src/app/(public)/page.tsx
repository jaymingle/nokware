import { EntryPoints } from "@/components/landing/entry-points";
import { Principles } from "@/components/landing/principles";
import { RecordFigures } from "@/components/landing/record-figures";
import { PageShell } from "@/components/page-shell";

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: { absolute: "Nokware · Accra's public record" },
  description:
    "Ask questions of the Accra Metropolitan Assembly's published documents, with every answer cited, and report issues in your area.",
};

export default function HomePage() {
  return (
    <PageShell
      width="data"
      title="Accra's public record, in plain answers"
      lead={
        <>
          Nokware holds the documents the Assembly publishes (budgets, fees, bye-laws, plans and reports) and answers
          questions from them, citing the document every time. Residents can also tell the Assembly about problems in
          their area and follow each report to its resolution.
        </>
      }
      // The figures stand beside the opening: it makes four claims about the record, and this is the record.
      aside={<RecordFigures />}
    >
      <div className="flex flex-col gap-12 sm:gap-16">
        <EntryPoints />
        <Principles />
      </div>
    </PageShell>
  );
}
