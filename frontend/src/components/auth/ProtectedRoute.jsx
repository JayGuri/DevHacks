import { Navigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { ENFORCE_TIER_RESTRICTIONS } from "@/lib/config";

/**
 * ProtectedRoute — guards routes based on authentication, RBAC role, and subscription tier.
 *
 * Props:
 *   requiredRole  — "TEAM_LEAD" | "CONTRIBUTOR" (always enforced)
 *   requiredTier  — "PRO" (enforced only when ENFORCE_TIER_RESTRICTIONS=true)
 *
 * Redirect behaviour:
 *   Not authenticated       → /login
 *   Wrong role              → /dashboard/overview
 *   Wrong tier (Free→Pro)   → /admin/billing  (upgrade prompt)
 */
export default function ProtectedRoute({ children, requiredRole, requiredTier }) {
  const { currentUser, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    );
  }

  if (!currentUser) {
    return <Navigate to="/login" replace />;
  }

  // Layer 1: RBAC — always enforced regardless of bypass flag
  if (requiredRole && currentUser.role !== requiredRole) {
    return <Navigate to="/dashboard/overview" replace />;
  }

  // Layer 2: Subscription tier — bypassed when ENFORCE_TIER_RESTRICTIONS=false
  if (
    requiredTier === "PRO" &&
    ENFORCE_TIER_RESTRICTIONS &&
    currentUser.subscriptionTier !== "PRO"
  ) {
    return <Navigate to="/admin/billing" replace />;
  }

  return children;
}
