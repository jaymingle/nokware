import { PublishForm } from "@/components/department/publish-form";
import { RolePage } from "@/components/portal/role-page";

export default function DepartmentPublishPage() {
  return (
    <RolePage
      title="Publish a document"
      lead="Published documents become answerable in Ask within minutes, carrying this department's name."
    >
      <PublishForm />
    </RolePage>
  );
}
