import type { Metadata, Viewport } from "next";

import { AskPage } from "@/components/ask/ask-page";

export const metadata: Metadata = {
  title: "Ask",
  description: "Ask about the Accra Metropolitan Assembly's budgets, fees, plans and policies. Every answer cites its source.",
};

// Lets the docked question box sit clear of the iPhone home indicator.
export const viewport: Viewport = { viewportFit: "cover" };

export default function Page() {
  return <AskPage />;
}
