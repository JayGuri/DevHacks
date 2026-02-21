import { Routes, Route, Navigate } from "react-router-dom";

import Login from "@/pages/auth/Login";
import Signup from "@/pages/auth/Signup";
import NotFound from "@/pages/NotFound";
import Overview from "@/pages/dashboard/Overview";
import Projects from "@/pages/dashboard/Projects";
import ProjectDetail from "@/pages/dashboard/ProjectDetail";
import Profile from "@/pages/dashboard/Profile";
import AdminOverview from "@/pages/admin/AdminOverview";
import AdminProjects from "@/pages/admin/AdminProjects";
import AdminProjectDetail from "@/pages/admin/AdminProjectDetail";
import AdminUsers from "@/pages/admin/AdminUsers";
import ProtectedRoute from "@/components/auth/ProtectedRoute";

export default function App() {
  return (
    <Routes>
      {/* Public */}
      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />

      {/* Dashboard — any authenticated user */}
      <Route
        path="/dashboard/overview"
        element={
          <ProtectedRoute>
            <Overview />
          </ProtectedRoute>
        }
      />
      <Route
        path="/dashboard/projects"
        element={
          <ProtectedRoute>
            <Projects />
          </ProtectedRoute>
        }
      />
      <Route
        path="/dashboard/projects/:id"
        element={
          <ProtectedRoute>
            <ProjectDetail />
          </ProtectedRoute>
        }
      />
      <Route
        path="/dashboard/profile"
        element={
          <ProtectedRoute>
            <Profile />
          </ProtectedRoute>
        }
      />

      {/* Admin — TEAM_LEAD only */}
      <Route
        path="/admin/overview"
        element={
          <ProtectedRoute requiredRole="TEAM_LEAD">
            <AdminOverview />
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin/projects"
        element={
          <ProtectedRoute requiredRole="TEAM_LEAD">
            <AdminProjects />
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin/projects/:id"
        element={
          <ProtectedRoute requiredRole="TEAM_LEAD">
            <AdminProjectDetail />
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin/users"
        element={
          <ProtectedRoute requiredRole="TEAM_LEAD">
            <AdminUsers />
          </ProtectedRoute>
        }
      />

      {/* Catch-all */}
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
