import { AskThreadProvider } from "@/components/ask/ask-thread-provider";
import { AskWidget } from "@/components/ask/ask-widget";
import { PublicHeader } from "@/components/public/public-header";
import { SkipLink } from "@/components/skip-link";

import type { ReactNode } from "react";

// Public pages: no sign-in and no auth state.
export default function PublicGroupLayout({ children }: { children: ReactNode }) {
  return (
    <AskThreadProvider>
      <div className="relative flex flex-1 flex-col">
        <SkipLink />
        <PublicHeader />
        {/* Vertical rhythm belongs to the page shell; the gutter belongs here, with the header's. */}
        <main id="main" className="flex w-full flex-1 flex-col px-5 sm:px-7">{children}</main>
        <AskWidget />
      </div>
    </AskThreadProvider>
  );
}
