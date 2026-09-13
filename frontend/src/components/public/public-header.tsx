"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { Brand } from "@/components/portal/brand";
import { cn } from "@/lib/utils";

function NavLink({ href, testId, children }: { href: string; testId: string; children: ReactNode }) {
  const active = usePathname() === href;
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "rounded-lg px-3 py-2 text-[13.5px] whitespace-nowrap transition-colors",
        active ? "font-medium text-ink" : "text-ink-soft hover:text-ink",
      )}
      data-testid={testId}
    >
      {children}
    </Link>
  );
}

/** The public site's header: home, Ask, and the way in for Assembly staff and contributors. */
export function PublicHeader() {
  return (
    <header className="border-b bg-paper-raised">
      <div className="mx-auto flex w-full max-w-[1360px] items-center justify-between gap-3 px-5 py-3.5 sm:px-7">
        <Link href="/" aria-label="Nokware home" className="min-w-0" data-testid="public-home">
          <Brand />
        </Link>
        <nav aria-label="Main" className="flex shrink-0 items-center">
          <NavLink href="/ask" testId="public-ask-link">
            Ask
          </NavLink>
          <NavLink href="/login" testId="public-portal-link">
            <span className="sm:hidden">Portal</span>
            <span className="hidden sm:inline">Institution portal</span>
          </NavLink>
        </nav>
      </div>
    </header>
  );
}
