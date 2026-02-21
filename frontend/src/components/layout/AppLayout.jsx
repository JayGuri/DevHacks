import { useParams, useLocation } from "react-router-dom";
import { useStore } from "@/lib/store";
import { getAllProjects } from "@/lib/projectUtils";
import { getBreadcrumbs } from "@/lib/breadcrumbs";
import Sidebar from "@/components/layout/Sidebar";
import TopNav from "@/components/layout/TopNav";
import MobileNav from "@/components/layout/MobileNav";
import PageHeader from "@/components/layout/PageHeader";

/**
 * AppLayout wraps every authenticated page.
 *
 * Props:
 *   children   – page content
 *   pageHeader – optional { title, subtitle, icon, badge, actions }
 *                Renders a rich PageHeader below the TopNav.
 *
 * Breadcrumbs are derived automatically from the current route.
 * Any page that previously passed `title` or `breadcrumbs` props
 * can now leave them out — they'll be resolved here.
 */
export default function AppLayout({ children, pageHeader }) {
  const params = useParams();
  const location = useLocation();
  const store = useStore();
  const projects = getAllProjects(store);

  const breadcrumbs = getBreadcrumbs(location.pathname, params, projects);

  return (
    <div className="flex">
      <Sidebar />
      <div className="flex min-h-screen flex-1 flex-col lg:ml-60">
        <TopNav breadcrumbs={breadcrumbs} />
        {pageHeader && (
          <div className="pt-14">
            <PageHeader {...pageHeader} />
          </div>
        )}
        <main className={`flex-1 p-6 pb-24 lg:pb-6 ${pageHeader ? "pt-4" : "pt-20"}`}>
          {children}
        </main>
      </div>
      <MobileNav />
    </div>
  );
}
