import { useState, useEffect } from "react";
import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";

import Login from "@/pages/auth/Login";
import Signup from "@/pages/auth/Signup";
import NotFound from "@/pages/NotFound";
import Overview from "@/pages/dashboard/Overview";
import Projects from "@/pages/dashboard/Projects";
import ProjectDetail from "@/pages/dashboard/ProjectDetail";
import AdminOverview from "@/pages/admin/AdminOverview";
import AdminProjects from "@/pages/admin/AdminProjects";
import AdminProjectDetail from "@/pages/admin/AdminProjectDetail";
import AdminUsers from "@/pages/admin/AdminUsers";
import JoinRequests from "@/pages/admin/JoinRequests";
import Subscription from "@/pages/admin/Subscription";
import ProtectedRoute from "@/components/auth/ProtectedRoute";
import CommandPalette from "@/components/layout/CommandPalette";
import ErrorBoundary from "@/components/ui/ErrorBoundary";

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

  useEffect(() => {
    function handleKeyDown(e) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setPaletteOpen((prev) => !prev);
      }
    }
    document.addEventListener("keydown", handleKeyDown);
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

      <ErrorBoundary>
        <AnimatePresence mode="wait">
          <Routes location={location} key={location.pathname}>
            {/* Public */}
            <Route path="/" element={<Navigate to="/login" replace />} />
            <Route
              path="/login"
              element={
                <AnimatedPage>
                  <Login />
                </AnimatedPage>
              }
            />
            <Route
              path="/signup"
              element={
                <AnimatedPage>
                  <Signup />
                </AnimatedPage>
              }
            />

            {/* Dashboard */}
            <Route
              path="/dashboard/overview"
              element={
                <ProtectedRoute>
                  <AnimatedPage>
                    <Overview />
                  </AnimatedPage>
                </ProtectedRoute>
              }
            />
            <Route
              path="/dashboard/projects"
              element={
                <ProtectedRoute>
                  <AnimatedPage>
                    <Projects />
                  </AnimatedPage>
                </ProtectedRoute>
              }
            />
            <Route
              path="/dashboard/projects/:id"
              element={
                <ProtectedRoute>
                  <AnimatedPage>
                    <ProjectDetail />
                  </AnimatedPage>
                </ProtectedRoute>
              }
            />
            {/* /dashboard/profile is retired — redirect to overview */}
            <Route
              path="/dashboard/profile"
              element={<Navigate to="/dashboard/overview" replace />}
            />

            {/* Admin */}
            <Route
              path="/admin/overview"
              element={
                <ProtectedRoute requiredRole="TEAM_LEAD">
                  <AnimatedPage>
                    <AdminOverview />
                  </AnimatedPage>
                </ProtectedRoute>
              }
            />
            <Route
              path="/admin/projects"
              element={
                <ProtectedRoute requiredRole="TEAM_LEAD">
                  <AnimatedPage>
                    <AdminProjects />
                  </AnimatedPage>
                </ProtectedRoute>
              }
            />
            <Route
              path="/admin/projects/:id"
              element={
                <ProtectedRoute requiredRole="TEAM_LEAD">
                  <AnimatedPage>
                    <AdminProjectDetail />
                  </AnimatedPage>
                </ProtectedRoute>
              }
            />
            <Route
              path="/admin/users"
              element={
                <ProtectedRoute requiredRole="TEAM_LEAD">
                  <AnimatedPage>
                    <AdminUsers />
                  </AnimatedPage>
                </ProtectedRoute>
              }
            />
            <Route
              path="/admin/requests"
              element={
                <ProtectedRoute requiredRole="TEAM_LEAD">
                  <AnimatedPage>
                    <JoinRequests />
                  </AnimatedPage>
                </ProtectedRoute>
              }
            />
            <Route
              path="/admin/billing"
              element={
                <ProtectedRoute requiredRole="TEAM_LEAD">
                  <AnimatedPage>
                    <Subscription />
                  </AnimatedPage>
                </ProtectedRoute>
              }
            />

            {/* Catch-all */}
            <Route
              path="*"
              element={
                <AnimatedPage>
                  <NotFound />
                </AnimatedPage>
              }
            />
          </Routes>
        </AnimatePresence>
      </ErrorBoundary>
    </>
  );
}
