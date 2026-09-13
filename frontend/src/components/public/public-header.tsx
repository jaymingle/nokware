import Link from "next/link";

import { Brand } from "@/components/portal/brand";

/** The public site's header: the brand, and the way in for Assembly staff and contributors. */
export function PublicHeader() {
  return (
    <header className="border-b bg-paper-raised">
      <div className="mx-auto flex w-full max-w-[1360px] items-center justify-between gap-4 px-5 py-3.5 sm:px-7">
        <Link href="/ask" aria-label="Nokware Ask" className="min-w-0" data-testid="public-home">
          <Brand />
        </Link>
        <Link
          href="/login"
          className="shrink-0 rounded-lg px-3 py-2 text-[13.5px] whitespace-nowrap text-ink-soft transition-colors hover:text-ink"
          data-testid="public-portal-link"
        >
          <span className="sm:hidden">Portal</span>
          <span className="hidden sm:inline">Institution portal</span>
        </Link>
      </div>
    </header>
  );
}
