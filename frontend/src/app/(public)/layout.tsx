import type { ReactNode } from "react";

import { AskThreadProvider } from "@/components/ask/ask-thread-provider";
import { AskWidget } from "@/components/ask/ask-widget";
import { PublicHeader } from "@/components/public/public-header";

// Public pages: no sign-in and no auth state.
export default function PublicGroupLayout({ children }: { children: ReactNode }) {
  return (
    <AskThreadProvider>
      <div className="flex flex-1 flex-col">
        <PublicHeader />
        <main className="flex w-full flex-1 flex-col px-5 pt-8 pb-10 sm:px-7 sm:pt-10">{children}</main>
        <AskWidget />
      </div>
    </AskThreadProvider>
  );
}
