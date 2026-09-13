import { LibraryTable } from "@/components/department/library-table";
import { RolePage } from "@/components/portal/role-page";

export default function DepartmentLibraryPage() {
  return (
    <RolePage title="Department library" lead="Everything published under this department's name, and whether Ask can find it yet.">
      <LibraryTable />
    </RolePage>
  );
}
