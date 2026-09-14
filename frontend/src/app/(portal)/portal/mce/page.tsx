import { Escalations } from "@/components/mce/escalations";
import { RolePage } from "@/components/portal/role-page";

export default function MceEscalationsPage() {
  return (
    <RolePage
      eyebrow="Oversight · Metropolitan Chief Executive"
      title="Every department"
      lead="Disputes contributors have escalated to you, from any department. Each publishes automatically when its clock runs out, unless you uphold the dispute. Every ruling is written to the audit trail with your name and the time."
    >
      <Escalations />
    </RolePage>
  );
}
