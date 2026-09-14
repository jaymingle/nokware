import Link from "next/link";

import { ContactItem } from "@/components/contacts/contact-item";

import type { PublicContact } from "@/lib/api/types";

// The directory link is left off mid-form, where following it would lose what was typed.
type ContactListProps = {
  title: string; lead?: string; contacts: PublicContact[]; testId: string; directoryLink?: boolean; columns?: boolean;
};

/** The numbers for one report or form, each with its source, and a way to the full directory. */
export function ContactList({ title, lead, contacts, testId, directoryLink = true, columns = false }: ContactListProps) {
  if (contacts.length === 0) return null;
  return (
    <section className="flex flex-col gap-1 rounded-xl border bg-paper-subtle px-4 py-3" data-testid={testId}>
      <h3 className="text-[17px]">{title}</h3>
      {lead ? <p className="text-[13px] text-ink-soft">{lead}</p> : null}
      <ul className={columns ? "grid gap-x-6 sm:grid-cols-2" : "flex flex-col divide-y"}>
        {contacts.map((contact) => (
          <ContactItem key={contact.id} contact={contact} />
        ))}
      </ul>
      {directoryLink ? (
        <Link href="/contacts" className="self-start pt-1 text-[13px] text-teal underline-offset-2 hover:underline" data-testid={`${testId}-directory`}>
          All numbers, by service
        </Link>
      ) : null}
    </section>
  );
}
