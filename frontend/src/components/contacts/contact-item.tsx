import { ExternalLinkIcon, MailIcon, MessageCircleIcon, PhoneIcon } from "lucide-react";

import { Tag } from "@/components/documents/tag";
import { numberHref, tierNote } from "@/lib/contacts";
import { formatDate } from "@/lib/time";

import type { ContactNumber, PublicContact } from "@/lib/api/types";

function NumberLink({ number, testId }: { number: ContactNumber; testId: string }) {
  const whatsapp = number.kind === "whatsapp";
  const Icon = whatsapp ? MessageCircleIcon : PhoneIcon;
  return (
    <a
      href={numberHref(number)}
      target={whatsapp ? "_blank" : undefined}
      rel={whatsapp ? "noopener" : undefined}
      className="inline-flex items-center gap-1.5 rounded-lg border bg-card px-2.5 py-1.5 text-[14px] font-medium tabular-nums hover:border-teal"
      data-testid={testId}
    >
      <Icon aria-hidden className="size-3.5 text-teal" />
      {number.number}
      {whatsapp ? <span className="text-[12px] font-normal text-ink-soft">WhatsApp</span> : null}
    </a>
  );
}

/** Where the number comes from, beside it: the emergency-line label, the cited page, or an unverified warning. */
export function SourceLine({ contact }: { contact: PublicContact }) {
  if (contact.tier === 2 && contact.source) {
    return (
      <p className="text-[12px] text-ink-soft">
        Source:{" "}
        <a href={contact.source.url} target="_blank" rel="noopener" className="text-teal underline-offset-2 hover:underline" data-testid={`contact-${contact.id}-source`}>
          {contact.source.label}
        </a>
        , checked {formatDate(contact.source.checked)}
      </p>
    );
  }
  if (contact.tier === 1) return <p className="text-[12px] text-ink-soft">{tierNote(contact)}</p>;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Tag tone="gold">{tierNote(contact)}</Tag>
      {contact.press_url ? (
        <a href={contact.press_url} target="_blank" rel="noopener" className="inline-flex items-center gap-1 text-[12px] text-teal hover:underline" data-testid={`contact-${contact.id}-press`}>
          Press report <ExternalLinkIcon aria-hidden className="size-3" />
        </a>
      ) : null}
    </div>
  );
}

/** One office or line: its name, what it's for, its numbers, and where they come from. */
export function ContactItem({ contact }: { contact: PublicContact }) {
  return (
    <li className="flex flex-col gap-2 py-3" data-testid={`contact-${contact.id}`}>
      <div>
        <div className="text-[14.5px] font-medium">{contact.name}</div>
        {contact.detail ? <p className="text-[13px] text-ink-soft">{contact.detail}</p> : null}
      </div>
      <div className="flex flex-wrap gap-2">
        {contact.numbers.map((number, i) => (
          <NumberLink key={number.number} number={number} testId={`contact-${contact.id}-number-${i}`} />
        ))}
        {contact.email ? (
          <a href={`mailto:${contact.email}`} className="inline-flex items-center gap-1.5 rounded-lg border bg-card px-2.5 py-1.5 text-[14px] hover:border-teal" data-testid={`contact-${contact.id}-email`}>
            <MailIcon aria-hidden className="size-3.5 text-teal" />
            {contact.email}
          </a>
        ) : null}
      </div>
      <SourceLine contact={contact} />
    </li>
  );
}
