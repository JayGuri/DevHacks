import { useParams } from "react-router-dom";
import AppLayout from "@/components/layout/AppLayout";

export default function ProjectDetail() {
  const { id } = useParams();
  return (
    <AppLayout
      title="Project Detail"
      breadcrumbs={[
        { label: "Projects", href: "/dashboard/projects" },
        { label: id },
      ]}
    >
      <p className="text-muted-foreground">Project {id} details coming soon.</p>
    </AppLayout>
  );
}
