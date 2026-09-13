"use client";

import { toast } from "sonner";

import { CaseNoteDialog } from "@/components/cases/case-note-dialog";
import { ReassignDialog } from "@/components/cases/reassign-dialog";
import { ErrorNote } from "@/components/documents/panels";
import { Button } from "@/components/ui/button";
import { useCaseAction } from "@/lib/api/queries";

import type { CaseDetail, Option } from "@/lib/api/types";

function Acknowledge({ caseId }: { caseId: string }) {
  const mutation = useCaseAction();
  async function start() {
    try {
      await mutation.mutateAsync({ id: caseId, action: "acknowledge" });
      toast.success("Marked in progress.");
    } catch {
      // shown below
    }
  }
  return (
    <>
      <Button variant="secondary" disabled={mutation.isPending} onClick={() => void start()} data-testid={`case-acknowledge-${caseId}`}>
        {mutation.isPending ? "Saving…" : "Start work"}
      </Button>
      {mutation.error ? <ErrorNote>{mutation.error.message}</ErrorNote> : null}
    </>
  );
}

function RecipientActions({ detail }: { detail: CaseDetail }) {
  const allowed = new Set(detail.allowed_actions);
  const whoSees = detail.private ? "It stays private: the citizen sees only that the case is completed." : "The citizen sees this note when they follow the case.";
  return (
    <>
      {allowed.has("acknowledge") ? <Acknowledge caseId={detail.case_id} /> : null}
      {allowed.has("resolve") ? (
        <CaseNoteDialog
          caseId={detail.case_id}
          action="resolve"
          triggerLabel="Resolve"
          title="Resolve this case"
          description={`Case ${detail.reference}: ${detail.topic}`}
          noteLabel="What was done?"
          hint={`${whoSees} It is kept in the case record.`}
          confirmLabel="Resolve case"
          success="Resolved. The citizen is told if they asked for messages."
        />
      ) : null}
    </>
  );
}

function MceActions({ detail, recipients }: { detail: CaseDetail; recipients: Option[] }) {
  const allowed = new Set(detail.allowed_actions);
  return (
    <>
      {allowed.has("reassign") ? <ReassignDialog detail={detail} recipients={recipients} /> : null}
      {allowed.has("reopen") ? (
        <CaseNoteDialog
          caseId={detail.case_id}
          action="reopen"
          tone="secondary"
          triggerLabel="Reopen"
          title="Send it back to finish the work"
          description={`${detail.recipients.join(" and ")} will see your note and the case returns to their queue.`}
          noteLabel="What is still to be done?"
          hint="Written to the audit trail with your name."
          confirmLabel="Reopen case"
          success="Reopened. It is back in the recipients' queue."
        />
      ) : null}
      {allowed.has("confirm-resolution") ? (
        <CaseNoteDialog
          caseId={detail.case_id}
          action="confirm-resolution"
          triggerLabel="Confirm resolution"
          title="Confirm the resolution stands"
          description="The case closes. The citizen is told it has been reviewed, and can't escalate it again."
          noteLabel="Why does the resolution stand?"
          hint="Written to the audit trail with your name."
          confirmLabel="Confirm and close"
          success="Confirmed. The case is closed."
        />
      ) : null}
    </>
  );
}

/** Exactly the actions the server allows the caller now. */
export function CaseActions({ detail, recipients }: { detail: CaseDetail; recipients?: Option[] }) {
  if (detail.allowed_actions.length === 0) return null;
  return (
    <div className="flex flex-wrap items-start gap-2" data-testid={`case-actions-${detail.case_id}`}>
      {recipients ? <MceActions detail={detail} recipients={recipients} /> : <RecipientActions detail={detail} />}
    </div>
  );
}
