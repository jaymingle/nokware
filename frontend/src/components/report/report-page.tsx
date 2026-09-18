"use client";

import { ArrowRightIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { ErrorPanel, LoadingPanel } from "@/components/documents/panels";
import { PageIntro } from "@/components/portal/page-intro";
import { CivicForm } from "@/components/report/civic-form";
import { QuickExit } from "@/components/report/quick-exit";
import { ReportReceiptView } from "@/components/report/report-receipt";
import { SafetyForm } from "@/components/report/safety-form";
import { SafetyQuestion } from "@/components/report/safety-question";
import { useStepFocus } from "@/hooks/use-step-focus";
import { useReportOptions } from "@/lib/api/public-queries";

import type { ReportOptions, ReportReceipt } from "@/lib/api/types";

// Every step stays on /report: a separate address for the safety form would
// sit in the browser's history for anyone to find.
type Step = { kind: "choose" } | { kind: "form"; safety: boolean } | { kind: "filed"; receipt: ReportReceipt };

function StepView({ step, options, go }: { step: Step; options: ReportOptions; go: (step: Step) => void }) {
  const back = () => go({ kind: "choose" });
  const filed = (receipt: ReportReceipt) => go({ kind: "filed", receipt });
  if (step.kind === "choose") return <SafetyQuestion onChoose={(safety) => go({ kind: "form", safety })} />;
  if (step.kind === "filed") return <ReportReceiptView receipt={step.receipt} safetySteps={options.safety_steps} onAnother={back} />;
  if (step.safety) return <SafetyForm options={options} onFiled={filed} onBack={back} />;
  return <CivicForm options={options} onFiled={filed} onBack={back} />;
}

/** Reached from the receipt once a report is filed, and from here: someone coming back has only their reference. */
function CheckExisting() {
  return (
    <section aria-labelledby="check-existing" className="mt-4 flex flex-col gap-1.5 rounded-xl border bg-paper-subtle p-5">
      <h2 id="check-existing" className="text-[18px] leading-snug">Already reported something?</h2>
      <p className="text-[14px] text-ink-soft">
        Check how far along it is with the reference you were given. Nokware never asks your name, so the reference
        is the only way to follow a report.
      </p>
      <Link href="/report/status" data-touch-target
        className="inline-flex w-fit items-center gap-1.5 text-[14px] font-medium text-teal underline underline-offset-2"
        data-testid="report-check-status">
        Check a case
        <ArrowRightIcon aria-hidden className="size-4" />
      </Link>
    </section>
  );
}

function isPrivate(step: Step): boolean {
  return (step.kind === "form" && step.safety) || (step.kind === "filed" && step.receipt.private);
}

export function ReportPage() {
  const options = useReportOptions();
  const [step, setStep] = useState<Step>({ kind: "choose" });
  const here = useStepFocus<HTMLDivElement>(step.kind === "form" ? `form-${step.safety}` : step.kind);
  const go = (next: Step) => {
    setStep(next);
    window.scrollTo({ top: 0 });
  };
  return (
    <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-2">
      {isPrivate(step) ? <QuickExit /> : null}
      <PageIntro eyebrow="Report an issue" title="Tell the Assembly">
        Report a problem in your area and it goes to the department responsible. Nokware never asks your name: you
        follow the report with the reference you get at the end.
      </PageIntro>
      {options.isPending ? <LoadingPanel label="Loading the form…" /> : null}
      {options.error ? <ErrorPanel message={options.error.message} onRetry={() => options.refetch()} /> : null}
      <div ref={here} tabIndex={-1} className="flex flex-col outline-none" data-testid="report-step">
        {options.data ? <StepView step={step} options={options.data} go={go} /> : null}
      </div>
      {step.kind === "choose" ? <CheckExisting /> : null}
    </div>
  );
}
