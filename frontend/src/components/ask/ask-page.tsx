"use client";

import { AskChat } from "@/components/ask/ask-chat";

/** The public Ask page: no sign-in, every answer carries its sources. */
export function AskPage() {
  return <AskChat mode="page" />;
}
