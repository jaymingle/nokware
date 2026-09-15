"use client";

import { useState } from "react";

import { ErrorPanel, LoadingPanel } from "@/components/documents/panels";
import { PageIntro } from "@/components/portal/page-intro";
import { CivicForm } from "@/components/report/civic-form";
import { QuickExit } from "@/components/report/quick-exit";
import { ReportReceiptView } from "@/components/report/report-receipt";
import { SafetyForm } from "@/components/report/safety-form";
import { SafetyQuestion } from "@/components/report/safety-question";
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

function isPrivate(step: Step): boolean {
  return (step.kind === "form" && step.safety) || (step.kind === "filed" && step.receipt.private);
}

/** The public report page: one question, then the everyday or the safety form, then the reference. */
export function ReportPage() {
  const options = useReportOptions();
  const [step, setStep] = useState<Step>({ kind: "choose" });
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
      {options.data ? <StepView step={step} options={options.data} go={go} /> : null}
    </div>
  );
}
