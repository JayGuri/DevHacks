import { useState, useEffect } from "react";
import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";

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
import JoinRequests from "@/pages/admin/JoinRequests";
import ProtectedRoute from "@/components/auth/ProtectedRoute";
import CommandPalette from "@/components/layout/CommandPalette";

function AnimatedPage({ children }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.18 }}
    >
      {children}
    </motion.div>
  );
}

export default function App() {
  const location = useLocation();
  const [paletteOpen, setPaletteOpen] = useState(false);

  // Global Ctrl+K / Cmd+K shortcut
  useEffect(() => {
    function handleKeyDown(e) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setPaletteOpen((prev) => !prev);
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    // Also listen for the custom event fired by the TopNav hint button
    function handleCustomEvent() {
      setPaletteOpen(true);
    }
    document.addEventListener("open-command-palette", handleCustomEvent);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("open-command-palette", handleCustomEvent);
    };
  }, []);

  return (
    <>
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />

      <AnimatePresence mode="wait">
        <Routes location={location} key={location.pathname}>
          {/* Public */}
          <Route path="/" element={<Navigate to="/login" replace />} />
          <Route path="/login" element={<AnimatedPage><Login /></AnimatedPage>} />
          <Route path="/signup" element={<AnimatedPage><Signup /></AnimatedPage>} />

          {/* Dashboard — any authenticated user */}
          <Route
            path="/dashboard/overview"
            element={
              <ProtectedRoute>
                <AnimatedPage><Overview /></AnimatedPage>
              </ProtectedRoute>
            }
          />
          <Route
            path="/dashboard/projects"
            element={
              <ProtectedRoute>
                <AnimatedPage><Projects /></AnimatedPage>
              </ProtectedRoute>
            }
          />
          <Route
            path="/dashboard/projects/:id"
            element={
              <ProtectedRoute>
                <AnimatedPage><ProjectDetail /></AnimatedPage>
              </ProtectedRoute>
            }
          />
          <Route
            path="/dashboard/profile"
            element={
              <ProtectedRoute>
                <AnimatedPage><Profile /></AnimatedPage>
              </ProtectedRoute>
            }
          />

          {/* Admin — TEAM_LEAD only */}
          <Route
            path="/admin/overview"
            element={
              <ProtectedRoute requiredRole="TEAM_LEAD">
                <AnimatedPage><AdminOverview /></AnimatedPage>
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/projects"
            element={
              <ProtectedRoute requiredRole="TEAM_LEAD">
                <AnimatedPage><AdminProjects /></AnimatedPage>
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/projects/:id"
            element={
              <ProtectedRoute requiredRole="TEAM_LEAD">
                <AnimatedPage><AdminProjectDetail /></AnimatedPage>
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/users"
            element={
              <ProtectedRoute requiredRole="TEAM_LEAD">
                <AnimatedPage><AdminUsers /></AnimatedPage>
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/requests"
            element={
              <ProtectedRoute requiredRole="TEAM_LEAD">
                <AnimatedPage><JoinRequests /></AnimatedPage>
              </ProtectedRoute>
            }
          />

          {/* Catch-all */}
          <Route path="*" element={<AnimatedPage><NotFound /></AnimatedPage>} />
        </Routes>
      </AnimatePresence>
    </>
  );
}
