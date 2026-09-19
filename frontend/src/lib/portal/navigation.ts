import type { Me, Role } from "@/lib/api/types";

export type NavCountKind =
  | "review" | "responses" | "escalations" | "cases" | "case-escalations" | "petitions" | "petition-reports";

type NavItem = { href: string; label: string; testId: string; count?: NavCountKind };

export const ROLE_HOME: Record<Role, string> = {
  department: "/portal/department",
  agency: "/portal/agency",
  contributor: "/portal/contributor",
  mce: "/portal/mce",
};

export const ROLE_NAV: Record<Role, NavItem[]> = {
  department: [
    { href: "/portal/department", label: "Review", testId: "portal-nav-review", count: "review" },
    { href: "/portal/department/publish", label: "Publish", testId: "portal-nav-publish" },
    { href: "/portal/department/library", label: "Library", testId: "portal-nav-library" },
    { href: "/portal/department/cases", label: "Cases", testId: "portal-nav-cases", count: "cases" },
  ],
  agency: [{ href: "/portal/agency", label: "Cases", testId: "portal-nav-cases", count: "cases" }],
  contributor: [
    { href: "/portal/contributor", label: "My submissions", testId: "portal-nav-submissions", count: "responses" },
    { href: "/portal/contributor/submit", label: "Submit a document", testId: "portal-nav-submit" },
    { href: "/portal/contributor/petitions", label: "Reported petitions", testId: "portal-nav-petition-reports", count: "petition-reports" },
  ],
  mce: [
    { href: "/portal/mce", label: "Document disputes", testId: "portal-nav-escalations", count: "escalations" },
    { href: "/portal/mce/cases", label: "Cases", testId: "portal-nav-cases", count: "case-escalations" },
    { href: "/portal/mce/petitions", label: "Petitions", testId: "portal-nav-petitions", count: "petitions" },
  ],
};

export function roleLabel(me: Me): string {
  if (me.role === "department") return me.department_name ?? "Department";
  if (me.role === "agency") return me.agency_name ?? "Agency";
  return me.role === "mce" ? "MCE oversight" : "Contributor";
}

export function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  return words
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase() ?? "")
    .join("");
}

/** Never an external URL after sign-in. */
export function safeNext(next: string | null): string {
  return next && next.startsWith("/portal") && !next.startsWith("//") ? next : "/portal";
}
