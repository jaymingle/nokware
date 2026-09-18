"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { Brand } from "@/components/portal/brand";
import { NavCount } from "@/components/portal/nav-count";
import { Button } from "@/components/ui/button";
import { useAuth, useMe } from "@/lib/auth/auth-context";
import { initials, ROLE_NAV, roleLabel } from "@/lib/portal/navigation";
import { cn } from "@/lib/utils";

function PortalNav() {
  const pathname = usePathname();
  const { role } = useMe();
  return (
    <nav aria-label="Portal" className="flex flex-wrap gap-1">
      {ROLE_NAV[role].map((item) => {
        const active = pathname === item.href;
        return (
          <Link
            key={item.href}
            href={item.href}
            data-testid={item.testId}
            aria-current={active ? "page" : undefined}
            data-touch-target
            className={cn(
              "inline-flex items-center rounded-lg border px-[13px] py-2 text-[13.5px] transition-colors",
              active ? "border-teal bg-teal-tint font-medium text-teal" : "border-transparent text-ink-soft hover:text-ink",
            )}
          >
            {item.label}
            {item.count ? <NavCount kind={item.count} active={active} /> : null}
          </Link>
        );
      })}
    </nav>
  );
}

function UserChip() {
  const me = useMe();
  const { signOut } = useAuth();
  return (
    <div className="flex items-center gap-2 text-[12.5px] text-ink-soft">
      <span aria-hidden className="grid size-6 place-items-center rounded-full bg-teal-tint text-[11px] text-teal">
        {initials(me.name)}
      </span>
      <span data-testid="portal-user">
        {me.name} · {roleLabel(me)}
      </span>
      <Link href="/" data-touch-target className="inline-flex items-center underline underline-offset-2 hover:text-ink" data-testid="portal-public-site">
        Public site
      </Link>
      <Button variant="ghost" size="sm" onClick={() => void signOut()} data-testid="portal-sign-out">
        Sign out
      </Button>
    </div>
  );
}

export function PortalHeader() {
  return (
    <header className="border-b bg-card">
      <div className="mx-auto flex max-w-[1360px] flex-wrap items-center gap-6 px-7 py-4">
        <Link href="/" aria-label="Nokware home" data-touch-target className="mr-auto inline-flex min-w-0 items-center" data-testid="portal-home">
          <Brand />
        </Link>
        <PortalNav />
        <UserChip />
      </div>
    </header>
  );
}
