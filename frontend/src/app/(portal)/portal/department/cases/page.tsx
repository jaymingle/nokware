import { CaseQueue } from "@/components/cases/case-queue";
import { RolePage } from "@/components/portal/role-page";

export default function DepartmentCasesPage() {
  return (
    <RolePage
      title="Citizen cases"
      lead="Reports residents have filed about your department's work, most urgent first. Start work so the case shows as in hand, and resolve it with a note the citizen will see."
    >
      <CaseQueue />
    </RolePage>
  );
}
