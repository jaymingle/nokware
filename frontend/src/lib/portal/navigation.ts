import type { Me, Role } from "@/lib/api/types";

/** A live count shown on a nav item, e.g. documents awaiting review. */
export type NavCountKind = "review" | "responses" | "escalations";

export type NavItem = { href: string; label: string; testId: string; count?: NavCountKind };

export const ROLE_HOME: Record<Role, string> = {
  department: "/portal/department",
  contributor: "/portal/contributor",
  mce: "/portal/mce",
};

export const ROLE_NAV: Record<Role, NavItem[]> = {
  department: [
    { href: "/portal/department", label: "Review", testId: "portal-nav-review", count: "review" },
    { href: "/portal/department/publish", label: "Publish", testId: "portal-nav-publish" },
    { href: "/portal/department/library", label: "Library", testId: "portal-nav-library" },
  ],
  contributor: [
    { href: "/portal/contributor", label: "My submissions", testId: "portal-nav-submissions", count: "responses" },
    { href: "/portal/contributor/submit", label: "Submit a document", testId: "portal-nav-submit" },
  ],
  mce: [{ href: "/portal/mce", label: "Escalations", testId: "portal-nav-escalations", count: "escalations" }],
};

/** Where the user sits in the Assembly, as shown beside their name. */
export function roleLabel(me: Me): string {
  if (me.role === "department") return me.department_name ?? "Department";
  return me.role === "mce" ? "MCE oversight" : "Contributor";
}

export function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  return words
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase() ?? "")
    .join("");
}

/** Only portal paths may be a post-sign-in destination (never an external URL). */
export function safeNext(next: string | null): string {
  return next && next.startsWith("/portal") && !next.startsWith("//") ? next : "/portal";
}
