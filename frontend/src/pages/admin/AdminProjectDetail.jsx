import { useParams } from "react-router-dom";
import AppLayout from "@/components/layout/AppLayout";

export default function AdminProjectDetail() {
  const { id } = useParams();
  return (
    <AppLayout
      title="Project Detail"
      breadcrumbs={[
        { label: "All Projects", href: "/admin/projects" },
        { label: id },
      ]}
    >
      <p className="text-muted-foreground">Admin project {id} details coming soon.</p>
    </AppLayout>
  );
}
