import { CaseOversightScreen } from "@/components/cases/case-oversight";
import { RolePage } from "@/components/portal/role-page";

export default function MceCasesPage() {
  return (
    <RolePage
      eyebrow="Oversight · Metropolitan Chief Executive"
      title="Citizen cases"
      lead="Every report residents have filed, across every department and the Police and Fire services. Personal-safety cases appear only in outline: their recipients alone can read them. Every reassignment is written to the audit trail with your name, the time and the departments involved."
    >
      <CaseOversightScreen />
    </RolePage>
  );
}
