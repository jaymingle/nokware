import type { ReportStatus } from "@/lib/api/types";
import type { Tone } from "@/lib/documents";

type Stage = "received" | "in_progress" | "completed";

export const STAGES: Stage[] = ["received", "in_progress", "completed"];

// The three steps a citizen sees. A personal-safety case shows only these.
const STAGE_OF: Record<string, Stage> = {
  submitted: "received",
  assigned: "received",
  in_progress: "in_progress",
  escalated: "in_progress",
  resolved: "completed",
};

export function stageOf(status: Pick<ReportStatus, "private" | "stage" | "status">): Stage {
  const raw = status.private ? status.stage : status.status;
  return STAGE_OF[raw ?? ""] ?? (raw === "completed" ? "completed" : "received");
}

export function stageLabels(isPrivate: boolean): Record<Stage, string> {
  return { received: "Received", in_progress: "In progress", completed: isPrivate ? "Completed" : "Resolved" };
}

const STAGE_TONES: Record<Stage, Tone> = { received: "gold", in_progress: "teal", completed: "neutral" };

/** The headline tag for a case's status, in the citizen's words. */
export function statusTag(status: ReportStatus): { tone: Tone; label: string } {
  if (!status.private && status.status === "escalated") return { tone: "brick", label: "With the MCE's office" };
  const stage = stageOf(status);
  const label = stageLabels(status.private)[stage];
  return { tone: STAGE_TONES[stage], label: stage === "completed" && status.escalated && !status.private ? `${label} after review` : label };
}
