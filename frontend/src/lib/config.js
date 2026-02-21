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
