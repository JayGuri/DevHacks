// src/hooks/useFeatureGate.js — Central access control hook
/**
 * useFeatureGate returns named booleans describing what the current user
 * may access. It is the single source of truth for both RBAC and tier checks.
 *
 * Layer 1 — RBAC (always enforced, never bypassed):
 *   canViewGlobalTopology, canViewAllNodes, canViewBackendTelemetry,
 *   canManageNodes, canManageUsers, canAccessAdminPanel
 *
 * Layer 2 — Subscription Tier (bypassed when ENFORCE_TIER_RESTRICTIONS=false):
 *   canUseAdvancedAggregation, canUseUnlimitedNodes,
 *   canView3DTopology, canExportMetrics, canViewDeepTelemetry
 *
 * Developer bypass:
 *   Set VITE_ENFORCE_TIER_RESTRICTIONS=false in .env to make hasPro=true
 *   for every user regardless of their stored subscriptionTier.
 */

import { useAuth } from "@/contexts/AuthContext";
import { ENFORCE_TIER_RESTRICTIONS, FREE_TIER_MAX_NODES } from "@/lib/config";

export function useFeatureGate() {
  const { currentUser } = useAuth();

  const isTeamLead = currentUser?.role === "TEAM_LEAD";

  // hasPro: true when bypass is active OR user genuinely has PRO tier
  const hasPro =
    !ENFORCE_TIER_RESTRICTIONS ||
    currentUser?.subscriptionTier === "PRO";

  return {
    // Raw flags — useful for conditional rendering logic
    isTeamLead,
    hasPro,

    // ── RBAC gates (never bypassed) ────────────────────────────────────────
    // These map to the Team Leader vs Client distinction in the requirements.
    canAccessAdminPanel: isTeamLead,
    canViewGlobalTopology: isTeamLead,   // Full cross-node convergence view
    canViewAllNodes: isTeamLead,          // Per-node stats across the federation
    canViewBackendTelemetry: isTeamLead, // Server-side training metrics
    canManageNodes: isTeamLead,           // Block / unblock nodes
    canManageUsers: isTeamLead,           // User role management

    // ── Tier gates (bypassed when ENFORCE_TIER_RESTRICTIONS=false) ─────────
    canUseAdvancedAggregation: isTeamLead && hasPro, // Multi-Krum / Trimmed Mean / Coord Median
    canUseUnlimitedNodes: isTeamLead && hasPro,       // > FREE_TIER_MAX_NODES connected nodes
    canView3DTopology: isTeamLead && hasPro,          // 3D network topology visualisation
    canExportMetrics: isTeamLead && hasPro,           // JSON metrics download (deep telemetry)
    canViewDeepTelemetry: isTeamLead && hasPro,       // SABD analytics, Byzantine detection table

    // ── Computed limits ────────────────────────────────────────────────────
    maxNodes: hasPro ? Infinity : FREE_TIER_MAX_NODES,
  };
}
