import { RtiPanel } from "@/components/ask/rti-panel";
import { SuggestedQuestions } from "@/components/ask/suggested-questions";
import { cn } from "@/lib/utils";

function RtiFootnote({ testId }: { testId: string }) {
  return (
    <details className="group rounded-xl border bg-card px-4 py-3.5">
      <summary className="cursor-pointer list-none text-[13.5px] text-ink-soft [&::-webkit-details-marker]:hidden" data-testid="ask-rti-toggle">
        Looking for something the Assembly hasn&apos;t published?{" "}
        <span className="text-teal underline underline-offset-2">You can request it under the RTI Act.</span>
      </summary>
      <div className="mt-4">
        <RtiPanel testId={testId} heading="h2" />
      </div>
    </details>
  );
}

/** The start of a conversation: what Ask does, questions it is known to answer, and where to go for what isn't published. */
export function AskWelcome({ compact, onAsk, disabled }: { compact: boolean; onAsk: (question: string) => void; disabled: boolean }) {
  return (
    <div className="flex flex-col gap-6" data-testid="ask-welcome">
      <div className="flex flex-col gap-2.5">
        <p className="text-[12.5px] text-ink-soft">Ask Nokware</p>
        <h1 className={cn("leading-tight", compact ? "text-[24px]" : "text-[32px] sm:text-[40px]")}>Answers that carry their source</h1>
        <p className={cn("max-w-[62ch] text-ink-soft", compact ? "text-[14px]" : "text-base")}>
          Ask about a budget, a fee, a plan or a policy, by typing or speaking. Every answer names the documents it came
          from, who published them and when. Where the record is silent, Nokware says so.
        </p>
      </div>
      <SuggestedQuestions onAsk={onAsk} disabled={disabled} compact={compact} />
      <RtiFootnote testId="ask-rti-footnote" />
    </div>
  );
}
