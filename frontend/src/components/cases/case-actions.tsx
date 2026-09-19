"use client";

import { CaseNoteDialog } from "@/components/cases/case-note-dialog";
import { ReassignDialog } from "@/components/cases/reassign-dialog";

import type { CaseDetail, Option } from "@/lib/api/types";

function RecipientActions({ detail }: { detail: CaseDetail }) {
  const allowed = new Set(detail.allowed_actions);
  return (
    <>
      {allowed.has("acknowledge") ? (
        <CaseNoteDialog
          detail={detail}
          action="acknowledge"
          tone="secondary"
          triggerLabel="Start work"
          title="Start work on this case"
          description={`Case ${detail.reference}: ${detail.topic}`}
          noteRequired={false}
          confirmLabel="Start work"
          success="Marked in progress."
        />
      ) : null}
      {allowed.has("resolve") ? (
        <CaseNoteDialog
          detail={detail}
          action="resolve"
          triggerLabel="Resolve"
          title="Resolve this case"
          description={`Case ${detail.reference}: ${detail.topic}`}
          noteRequired
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
          detail={detail}
          action="reopen"
          tone="secondary"
          triggerLabel="Reopen"
          title="Send it back to finish the work"
          description={`${detail.recipients.join(" and ")} will see your note and the case returns to their queue.`}
          noteRequired={false}
          confirmLabel="Reopen case"
          success="Reopened. It is back in the recipients' queue."
        />
      ) : null}
      {allowed.has("confirm-resolution") ? (
        <CaseNoteDialog
          detail={detail}
          action="confirm-resolution"
          triggerLabel="Confirm resolution"
          title="Confirm the resolution stands"
          description="The case closes. The citizen is told it has been reviewed, and can't escalate it again."
          noteRequired={false}
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
