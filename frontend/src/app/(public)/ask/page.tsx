import { AskPage } from "@/components/ask/ask-page";
import { PAGE_PADDING } from "@/components/page-shell";
import { cn } from "@/lib/utils";

import type { Metadata, Viewport } from "next";

export const metadata: Metadata = {
  title: "Ask",
  description: "Ask about the Accra Metropolitan Assembly's budgets, fees, plans and policies. Every answer cites its source.",
};

// Lets the docked question box sit clear of the iPhone home indicator.
export const viewport: Viewport = { viewportFit: "cover" };

// Ask heads itself: the chat's own opening is the h1, and it gives way to the
// thread once a question is asked. So it spends the shell's page padding
// without the shell's heading block.
export default function Page() {
  return (
    <div className={cn("flex flex-1 flex-col", PAGE_PADDING)}>
      <AskPage />
    </div>
  );
}
