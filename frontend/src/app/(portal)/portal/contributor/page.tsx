import { Submissions } from "@/components/contributor/submissions";
import { RolePage } from "@/components/portal/role-page";

export default function ContributorSubmissionsPage() {
  return (
    <RolePage title="My submissions" lead="Where each document you've submitted stands, and what you can do next.">
      <Submissions />
    </RolePage>
  );
}
