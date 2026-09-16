"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { Brand } from "@/components/portal/brand";
import { cn } from "@/lib/utils";

function NavLink({ href, testId, children }: { href: string; testId: string; children: ReactNode }) {
  const pathname = usePathname();
  const active = pathname === href || pathname.startsWith(`${href}/`);
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      data-touch-target
      className={cn(
        "inline-flex items-center rounded-lg px-3 py-2 text-[13.5px] whitespace-nowrap transition-colors",
        active ? "font-medium text-ink" : "text-ink-soft hover:text-ink",
      )}
      data-testid={testId}
    >
      {children}
    </Link>
  );
}

/** The public site's header: Ask, reporting, the dashboard, petitions, accountability, and the way in for staff. On a phone or tablet the links take a second row. */
export function PublicHeader() {
  return (
    <header className="border-b bg-paper-raised">
      <div className="mx-auto flex w-full max-w-[1360px] flex-wrap items-center justify-between gap-x-3 gap-y-2 px-5 py-3.5 sm:px-7 md:flex-nowrap">
        <Link href="/" aria-label="Nokware home" data-touch-target className="inline-flex min-w-0 items-center" data-testid="public-home">
          <Brand />
        </Link>
        <nav aria-label="Main" className="-mx-3 flex w-[calc(100%+1.5rem)] items-center overflow-x-auto md:mx-0 md:w-auto md:shrink-0">
          <NavLink href="/ask" testId="public-ask-link">
            Ask
          </NavLink>
          <NavLink href="/report" testId="public-report-link">
            <span className="lg:hidden">Report</span>
            <span className="hidden lg:inline">Report an issue</span>
          </NavLink>
          <NavLink href="/dashboard" testId="public-dashboard-link">
            Dashboard
          </NavLink>
          <NavLink href="/petitions" testId="public-petitions-link">
            Petitions
          </NavLink>
          <NavLink href="/accountability" testId="public-accountability-link">
            Accountability
          </NavLink>
          <NavLink href="/contacts" testId="public-contacts-link">
            Contacts
          </NavLink>
          <NavLink href="/login" testId="public-portal-link">
            <span className="lg:hidden">Portal</span>
            <span className="hidden lg:inline">Institution portal</span>
          </NavLink>
        </nav>
      </div>
    </header>
  );
}
