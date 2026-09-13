import { EntryPoints } from "@/components/landing/entry-points";
import { Principles } from "@/components/landing/principles";

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: { absolute: "Nokware · Accra's public record" },
  description:
    "Ask questions of the Accra Metropolitan Assembly's published documents, with every answer cited, and report issues in your area.",
};

export default function HomePage() {
  return (
    <div className="mx-auto flex w-full max-w-[1120px] flex-col gap-12 sm:gap-16">
      <section className="flex max-w-[64ch] flex-col gap-4 pt-2 sm:pt-6">
        <p className="text-[12.5px] text-ink-soft">Accra Metropolitan Assembly</p>
        <h1 className="text-[36px] leading-[1.1] sm:text-[52px]">Accra&apos;s public record, in plain answers</h1>
        <p className="text-[17px] text-ink-soft">
          Nokware holds the documents the Assembly publishes (budgets, fees, bye-laws, plans and reports) and answers
          questions from them, citing the document every time. Residents can also tell the Assembly about problems in
          their area and follow each report to its resolution.
        </p>
      </section>
      <EntryPoints />
      <Principles />
    </div>
  );
}
