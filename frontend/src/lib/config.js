// Frontend configuration — API base URL and mock toggle
// Set USE_MOCK to false to use real backend API calls.
// Can also be toggled at runtime via localStorage:
//   localStorage.setItem('arfl-use-mock', 'false'); location.reload();

const stored = localStorage.getItem("arfl-use-mock");

/** When true, all data comes from lib/mockData.js. When false, real API calls are made. */
export const USE_MOCK = stored !== null ? stored !== "false" : true;

/** Base URL for the FastAPI backend (no trailing slash). */
export const API_BASE_URL =
  import.meta.env.VITE_API_URL || "http://localhost:8000/api";

/** WebSocket base URL */
export const WS_BASE_URL = import.meta.env.VITE_WS_URL || "ws://localhost:8000";

/**
 * Subscription tier enforcement toggle.
 *
 * When true  — FREE users are blocked from PRO-only features in the UI.
 * When false — All tier checks are bypassed (developer bypass).
 *              RBAC role checks are NEVER bypassed regardless of this value.
 *
 * Set VITE_ENFORCE_TIER_RESTRICTIONS=false in your .env to disable.
 */
export const ENFORCE_TIER_RESTRICTIONS =
  import.meta.env.VITE_ENFORCE_TIER_RESTRICTIONS !== "false";

/** Maximum nodes allowed on the Free tier */
export const FREE_TIER_MAX_NODES = 5;
