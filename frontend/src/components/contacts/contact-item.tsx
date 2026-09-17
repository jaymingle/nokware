import { ExternalLinkIcon, MailIcon, MessageCircleIcon, PhoneIcon } from "lucide-react";

import { Tag } from "@/components/documents/tag";
import { numberHref, tierNote } from "@/lib/contacts";
import { formatDate } from "@/lib/time";
import { cn } from "@/lib/utils";

import type { ContactNumber, PublicContact } from "@/lib/api/types";

function NumberLink({ number, testId, marked = false }: { number: ContactNumber; testId: string; marked?: boolean }) {
  const whatsapp = number.kind === "whatsapp";
  const Icon = whatsapp ? MessageCircleIcon : PhoneIcon;
  return (
    <a
      href={numberHref(number)}
      target={whatsapp ? "_blank" : undefined}
      rel={whatsapp ? "noopener" : undefined}
      data-touch-target
      className={cn(
        "inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[14px] tabular-nums hover:border-teal",
        number.current ? "bg-card font-medium" : "bg-transparent text-ink-soft",
      )}
      data-testid={testId}
    >
      <Icon aria-hidden className={cn("size-3.5", number.current ? "text-teal" : "text-ink-soft")} />
      {number.number}
      {whatsapp ? <span className="text-[12px] font-normal text-ink-soft">WhatsApp</span> : null}
      {marked ? <span className="rounded bg-teal-tint px-1.5 text-[11.5px] font-normal text-teal">Current</span> : null}
    </a>
  );
}

/** Numbers given to Nokware that differ from the cited page. */
function EarlierNumbers({ contactId, numbers }: { contactId: string; numbers: ContactNumber[] }) {
  return (
    <ul className="flex flex-col gap-1.5">
      {numbers.map((number, i) => (
        <li key={number.number} className="flex flex-wrap items-center gap-2">
          <NumberLink number={number} testId={`contact-${contactId}-earlier-${i}`} />
          <span className="text-[12px] text-ink-soft">{number.note}</span>
        </li>
      ))}
    </ul>
  );
}

function SourceLine({ contact }: { contact: PublicContact }) {
  if (contact.tier === 2 && contact.source) {
    return (
      <p className="text-[12px] text-ink-soft">
        Source:{" "}
        <a href={contact.source.url} target="_blank" rel="noopener" className="text-teal underline underline-offset-2" data-testid={`contact-${contact.id}-source`}>
          {contact.source.label}
        </a>
        , checked {formatDate(contact.source.checked)}
      </p>
    );
  }
  if (contact.tier === 1) return <p className="text-[12px] text-ink-soft">{tierNote(contact)}</p>;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Tag tone="gold" wrap testId={`contact-${contact.id}-unverified`}>{tierNote(contact)}</Tag>
      {contact.press_url ? (
        <a href={contact.press_url} target="_blank" rel="noopener" data-touch-target className="inline-flex items-center gap-1 text-[12px] text-teal underline underline-offset-2" data-testid={`contact-${contact.id}-press`}>
          Press report <ExternalLinkIcon aria-hidden className="size-3" />
        </a>
      ) : null}
    </div>
  );
}

export function ContactItem({ contact }: { contact: PublicContact }) {
  const current = contact.numbers.filter((n) => n.current);
  const earlier = contact.numbers.filter((n) => !n.current);
  return (
    <li className="flex flex-col gap-2 py-3" data-testid={`contact-${contact.id}`}>
      <div>
        <div className="text-[14.5px] font-medium">{contact.name}</div>
        {contact.detail ? <p className="text-[13px] text-ink-soft">{contact.detail}</p> : null}
      </div>
      <div className="flex flex-wrap gap-2">
        {current.map((number, i) => (
          <NumberLink key={number.number} number={number} testId={`contact-${contact.id}-number-${i}`} marked={earlier.length > 0} />
        ))}
        {contact.email ? (
          <a href={`mailto:${contact.email}`} data-touch-target className="inline-flex items-center gap-1.5 rounded-lg border bg-card px-2.5 py-1.5 text-[14px] hover:border-teal" data-testid={`contact-${contact.id}-email`}>
            <MailIcon aria-hidden className="size-3.5 text-teal" />
            {contact.email}
          </a>
        ) : null}
      </div>
      {earlier.length ? <EarlierNumbers contactId={contact.id} numbers={earlier} /> : null}
      <SourceLine contact={contact} />
    </li>
  );
}
