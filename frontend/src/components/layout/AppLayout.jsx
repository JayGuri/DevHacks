import Sidebar from "@/components/layout/Sidebar";
import TopNav from "@/components/layout/TopNav";
import MobileNav from "@/components/layout/MobileNav";

export default function AppLayout({ title, breadcrumbs, children }) {
  return (
    <div className="flex">
      <Sidebar />
      <div className="flex min-h-screen flex-1 flex-col lg:ml-60">
        <TopNav title={title} breadcrumbs={breadcrumbs} />
        <main className="flex-1 p-6 pb-24 pt-20 lg:pb-6">{children}</main>
      </div>
      <MobileNav />
    </div>
  );
}
