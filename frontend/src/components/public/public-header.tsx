"use client";

import { PhoneIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Brand } from "@/components/portal/brand";
import { cn } from "@/lib/utils";

import type { ReactNode } from "react";

function NavLink({ href, testId, children }: { href: string; testId: string; children: ReactNode }) {
  const pathname = usePathname();
  // Home is only itself: every path starts with "/", so the prefix test would mark it current everywhere.
  const active = pathname === href || (href !== "/" && pathname.startsWith(`${href}/`));
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

export function PublicHeader() {
  return (
    <header className="border-b bg-paper-raised">
      <div className="mx-auto flex w-full max-w-[1360px] flex-wrap items-center justify-between gap-x-3 gap-y-2 px-5 py-3.5 sm:px-7 md:flex-nowrap">
        <Link href="/" aria-label="Nokware home" data-touch-target className="inline-flex min-w-0 items-center" data-testid="public-home">
          <Brand />
        </Link>
        <nav aria-label="Main" className="-mx-3 flex w-[calc(100%+1.5rem)] items-center overflow-x-auto md:mx-0 md:w-auto md:shrink-0">
          <NavLink href="/" testId="public-home-link">
            Home
          </NavLink>
          <NavLink href="/accountability" testId="public-accountability-link">
            Accountability
          </NavLink>
          <NavLink href="/dashboard" testId="public-dashboard-link">
            Dashboard
          </NavLink>
          <NavLink href="/report" testId="public-report-link">
            <span className="lg:hidden">Report</span>
            <span className="hidden lg:inline">Report an issue</span>
          </NavLink>
          <NavLink href="/ask" testId="public-ask-link">
            Ask
          </NavLink>
          <NavLink href="/petitions" testId="public-petitions-link">
            Petitions
          </NavLink>
          {/* Contacts is the emergency route: the number to call when nothing on this site is fast enough. It is
              marked out because in that moment nobody scans a row of equal-weight words. */}
          <Link href="/contacts" data-touch-target data-testid="public-contacts-link"
            className="ms-1 inline-flex items-center gap-1.5 rounded-lg border border-brick/35 bg-brick-tint px-3 py-2 text-[13.5px] font-medium whitespace-nowrap text-brick transition-colors hover:border-brick">
            <PhoneIcon aria-hidden className="size-4" />
            Contacts
          </Link>
          <NavLink href="/login" testId="public-portal-link">
            <span className="lg:hidden">Portal</span>
            <span className="hidden lg:inline">Institution portal</span>
          </NavLink>
        </nav>
      </div>
    </header>
  );
}
