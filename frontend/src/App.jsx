import { Routes, Route, Navigate } from "react-router-dom";

import Login from "@/pages/auth/Login";
import Signup from "@/pages/auth/Signup";
import Overview from "@/pages/dashboard/Overview";
import Projects from "@/pages/dashboard/Projects";
import ProjectDetail from "@/pages/dashboard/ProjectDetail";
import Profile from "@/pages/dashboard/Profile";
import AdminOverview from "@/pages/admin/AdminOverview";
import AdminProjects from "@/pages/admin/AdminProjects";
import AdminProjectDetail from "@/pages/admin/AdminProjectDetail";
import AdminUsers from "@/pages/admin/AdminUsers";

export default function App() {
  return (
    <Routes>
      {/* Public routes */}
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />

      {/* Dashboard routes (contributor) */}
      <Route path="/dashboard/overview" element={<Overview />} />
      <Route path="/dashboard/projects" element={<Projects />} />
      <Route path="/dashboard/projects/:id" element={<ProjectDetail />} />
      <Route path="/dashboard/profile" element={<Profile />} />

      {/* Admin routes (team lead) */}
      <Route path="/admin/overview" element={<AdminOverview />} />
      <Route path="/admin/projects" element={<AdminProjects />} />
      <Route path="/admin/projects/:id" element={<AdminProjectDetail />} />
      <Route path="/admin/users" element={<AdminUsers />} />

      {/* Fallback */}
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}
