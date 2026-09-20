import { LedgerPdfLink } from "@/components/ask/ledger-pdf-link";
import { ProvenanceLine } from "@/components/ask/provenance-line";
import { RTI_CONTACT, RTI_MANUAL } from "@/lib/ask/rti";

function Contact() {
  return (
    <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1.5 text-[14px]">
      <dt className="text-ink-soft">Office</dt>
      <dd>{RTI_CONTACT.unit}</dd>
      <dt className="text-ink-soft">Information Officer</dt>
      <dd>{RTI_CONTACT.officer}</dd>
      <dt className="text-ink-soft">Phone</dt>
      <dd>
        <a href={RTI_CONTACT.phoneHref} className="text-teal underline underline-offset-2" data-testid="rti-phone">
          {RTI_CONTACT.phone}
        </a>
      </dd>
      <dt className="text-ink-soft">Post</dt>
      <dd>{RTI_CONTACT.postal}</dd>
    </dl>
  );
}

export function RtiPanel({ testId, heading: Heading = "h3" }: { testId: string; heading?: "h2" | "h3" }) {
  return (
    <div className="flex flex-col gap-3" data-testid={testId}>
      <div className="flex flex-col gap-1">
        {/* The panel's own level: the whole page on /rti, a section of an answer inside Ask. */}
        <Heading className="text-[16px]">Request it from the Assembly</Heading>
        <p className="text-[14px] text-ink-soft">
          If the Assembly holds this information but hasn&apos;t published it, you have the right to request it under the
          Right to Information Act, 2019 (Act 989). The manual below includes the standard request form (Appendix A).
        </p>
      </div>
      <Contact />
      <div className="flex flex-col gap-1.5 rounded-lg bg-paper-subtle px-3.5 py-3">
        <p className="text-[12.5px] text-ink-soft">
          Source: {RTI_MANUAL.title} ({RTI_MANUAL.year})
        </p>
        <ProvenanceLine provenance="ama_website" departmentName={RTI_MANUAL.departmentName} sourceUrl={RTI_MANUAL.sourceUrl} testId={`${testId}-provenance`} />
        <p className="text-[12px] text-ink-muted">
          These details come from AMA&apos;s {RTI_MANUAL.year} manual and may have changed since.
        </p>
        <div className="mt-1">
          <LedgerPdfLink documentId={RTI_MANUAL.documentId} testId={`${testId}-pdf`} />
        </div>
      </div>
    </div>
  );
}
