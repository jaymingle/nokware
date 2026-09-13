import type { HistoryAction, HistoryEntry } from "@/lib/api/types";

/** What each audit-trail entry records, in the portal's words. */
const LABELS: Record<HistoryAction, string> = {
  uploaded: "Published by the department",
  submitted: "Submitted for review",
  accepted: "Accepted and published",
  disputed: "Disputed by the department",
  dispute_accepted: "Dispute accepted; withdrawn",
  resubmitted: "Resubmitted with a revised PDF",
  escalated: "Escalated to the MCE",
  upheld: "Dispute upheld by the MCE; withdrawn",
  overruled: "Dispute overruled by the MCE; published",
  auto_published: "Published automatically: the clock ran out",
};

const ROLES: Record<string, string> = {
  department: "Department",
  contributor: "Contributor",
  mce: "MCE",
};

export function historyLabel(action: HistoryAction): string {
  return LABELS[action];
}

/** Who acted, e.g. "Ama Mensah · Contributor"; automatic steps have no person. */
export function historyActor(entry: HistoryEntry): string | null {
  if (entry.actor_role === "system") return null;
  const role = ROLES[entry.actor_role];
  return role ? `${entry.actor_name} · ${role}` : entry.actor_name;
}
