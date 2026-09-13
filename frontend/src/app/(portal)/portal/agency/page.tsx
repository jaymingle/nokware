import { CaseQueue } from "@/components/cases/case-queue";
import { RolePage } from "@/components/portal/role-page";

export default function AgencyCasesPage() {
  return (
    <RolePage
      title="Cases routed to you"
      lead="Reports about safety that residents have filed and the Assembly has routed to your service, most urgent first. Personal-safety reports are private: only your service and any other it was sent to can read them."
    >
      <CaseQueue />
    </RolePage>
  );
}
