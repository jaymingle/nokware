"use client";

import { MessageCircleIcon, XIcon } from "lucide-react";
import { usePathname } from "next/navigation";
import { Dialog as DialogPrimitive } from "radix-ui";
import { useState } from "react";

import { AskChat } from "@/components/ask/ask-chat";
import { useThread } from "@/components/ask/ask-thread-provider";
import { Button } from "@/components/ui/button";
import { DialogOverlay } from "@/components/ui/dialog";

const ASK_PAGE = "/ask"; // the page is the conversation; no button to open a second one

function PanelHeader({ answers }: { answers: number }) {
  return (
    <header className="flex items-start justify-between gap-3 border-b bg-paper-raised px-4 py-3">
      <div className="flex items-center gap-2.5">
        <span aria-hidden className="grid size-8 place-items-center rounded-lg bg-ink font-heading text-[16px] leading-none text-paper">N</span>
        <div>
          <DialogPrimitive.Title className="font-heading text-[15px] font-medium">Ask Nokware</DialogPrimitive.Title>
          <DialogPrimitive.Description className="text-[12px] text-ink-soft">
            {answers ? "Every answer names its sources" : "Answers from the Assembly's own documents"}
          </DialogPrimitive.Description>
        </div>
      </div>
      <DialogPrimitive.Close asChild>
        <Button variant="ghost" size="icon-sm" aria-label="Close Ask" data-testid="ask-widget-close">
          <XIcon />
        </Button>
      </DialogPrimitive.Close>
    </header>
  );
}

export function AskWidget() {
  const [open, setOpen] = useState(false);
  const { turns } = useThread();
  const pathname = usePathname();
  if (pathname === ASK_PAGE) return null;
  return (
    <DialogPrimitive.Root open={open} onOpenChange={setOpen}>
      <DialogPrimitive.Trigger asChild>
        <button
          type="button"
          aria-label="Ask Nokware a question"
          data-testid="ask-widget-open"
          className="fixed end-4 bottom-4 z-40 flex h-12 cursor-pointer items-center gap-2 rounded-full border border-ink bg-ink ps-4 pe-5 text-[14.5px] font-medium text-paper transition-colors hover:bg-teal hover:border-teal focus-visible:ring-3 focus-visible:ring-teal/50 focus-visible:outline-none"
        >
          <MessageCircleIcon aria-hidden className="size-4.5" />
          Ask
        </button>
      </DialogPrimitive.Trigger>
      <DialogPrimitive.Portal>
        <DialogOverlay />
        <DialogPrimitive.Content
          data-testid="ask-widget-panel"
          className="fixed inset-x-0 bottom-0 z-50 flex h-[min(88dvh,640px)] flex-col overflow-hidden rounded-t-2xl border bg-paper outline-none data-open:animate-in data-open:slide-in-from-bottom-4 data-closed:animate-out data-closed:fade-out-0 sm:inset-x-auto sm:end-4 sm:bottom-4 sm:w-[26rem] sm:rounded-2xl"
        >
          <PanelHeader answers={turns.length} />
          <div className="min-h-0 flex-1">
            <AskChat mode="panel" />
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
