// Centralized API service — wraps every backend endpoint.
// Each function hits the real FastAPI backend.
// Consumers decide whether to call these or use mock data based on USE_MOCK.

import { API_BASE_URL } from "./config";

// ────────────────────────────────────────────────────────
// Token helpers
// ────────────────────────────────────────────────────────

const TOKEN_KEY = "arfl-token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

// ────────────────────────────────────────────────────────
// Generic fetch wrapper
// ────────────────────────────────────────────────────────

export async function apiFetch(path, options = {}) {
  const token = getToken();
  const headers = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  };

  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const msg = body.detail || `API error ${res.status}`;
    throw new Error(msg);
  }

  // Some endpoints return 204 / empty body
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

// ────────────────────────────────────────────────────────
// Auth
// ────────────────────────────────────────────────────────

export async function apiSignup(name, email, password) {
  return apiFetch("/auth/signup", {
    method: "POST",
    body: JSON.stringify({ name, email, password }),
  });
}

export async function apiLogin(email, password) {
  return apiFetch("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function apiGetMe() {
  return apiFetch("/auth/me");
}

export async function apiListUsers() {
  return apiFetch("/users");
}

export async function apiUpdateUserRole(userId, role) {
  return apiFetch(`/users/${userId}/role`, {
    method: "PATCH",
    body: JSON.stringify({ role }),
  });
}

// ────────────────────────────────────────────────────────
// Projects
// ────────────────────────────────────────────────────────

export async function apiListProjects() {
  return apiFetch("/projects");
}

export async function apiGetProject(projectId) {
  return apiFetch(`/projects/${projectId}`);
}

export async function apiCreateProject(data) {
  return apiFetch("/projects", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function apiUpdateProject(projectId, data) {
  return apiFetch(`/projects/${projectId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function apiDeleteProject(projectId) {
  return apiFetch(`/projects/${projectId}`, {
    method: "DELETE",
  });
}

export async function apiJoinProject(projectId, inviteCode) {
  return apiFetch(`/projects/${projectId}/join`, {
    method: "POST",
    body: JSON.stringify({ inviteCode: inviteCode || null }),
  });
}

export async function apiValidateCode(code) {
  return apiFetch("/projects/validate-code", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
}

// ────────────────────────────────────────────────────────
// Join Requests
// ────────────────────────────────────────────────────────

export async function apiListJoinRequests(params = {}) {
  const qs = new URLSearchParams();
  if (params.projectId) qs.set("projectId", params.projectId);
  if (params.userId) qs.set("userId", params.userId);
  if (params.status) qs.set("status", params.status);
  const query = qs.toString();
  return apiFetch(`/join-requests${query ? `?${query}` : ""}`);
}

export async function apiCreateJoinRequest(projectId, message = "") {
  return apiFetch("/join-requests", {
    method: "POST",
    body: JSON.stringify({ projectId, message }),
  });
}

export async function apiApproveJoinRequest(requestId) {
  return apiFetch(`/join-requests/${requestId}/approve`, {
    method: "PATCH",
  });
}

export async function apiRejectJoinRequest(requestId) {
  return apiFetch(`/join-requests/${requestId}/reject`, {
    method: "PATCH",
  });
}

// ────────────────────────────────────────────────────────
// Notifications
// ────────────────────────────────────────────────────────

export async function apiListNotifications() {
  return apiFetch("/notifications");
}

export async function apiMarkNotificationRead(notificationId) {
  return apiFetch(`/notifications/${notificationId}/read`, {
    method: "PATCH",
  });
}

export async function apiMarkAllNotificationsRead() {
  return apiFetch("/notifications/read-all", {
    method: "PATCH",
  });
}

// ────────────────────────────────────────────────────────
// Training
// ────────────────────────────────────────────────────────

export async function apiStartTraining(projectId) {
  return apiFetch(`/projects/${projectId}/training/start`, {
    method: "POST",
  });
}

export async function apiPauseTraining(projectId) {
  return apiFetch(`/projects/${projectId}/training/pause`, {
    method: "POST",
  });
}

export async function apiResumeTraining(projectId) {
  return apiFetch(`/projects/${projectId}/training/resume`, {
    method: "POST",
  });
}

export async function apiResetTraining(projectId) {
  return apiFetch(`/projects/${projectId}/training/reset`, {
    method: "POST",
  });
}

export async function apiTrainingStatus(projectId) {
  return apiFetch(`/projects/${projectId}/training/status`);
}

export async function apiUpdateTrainingConfig(projectId, updates) {
  return apiFetch(`/projects/${projectId}/config`, {
    method: "PATCH",
    body: JSON.stringify(updates),
  });
}

export async function apiBlockNode(projectId, nodeId) {
  return apiFetch(`/projects/${projectId}/nodes/${nodeId}/block`, {
    method: "POST",
  });
}

export async function apiUnblockNode(projectId, nodeId) {
  return apiFetch(`/projects/${projectId}/nodes/${nodeId}/unblock`, {
    method: "POST",
  });
}

export async function apiExportMetrics(projectId) {
  return apiFetch(`/projects/${projectId}/export`);
}

// ────────────────────────────────────────────────────────
// Contributor gradient submission
// ────────────────────────────────────────────────────────

/**
 * Submit a gradient update from the contributor's local training run.
 *
 * The backend applies L2 norm clipping and zero-sum masking before
 * queuing the update for the next FL aggregation round.
 *
 * @param {string} projectId
 * @param {{ nodeId: string, gradients: Record<string,number[]>, dataSize?: number, round?: number }} payload
 */
export async function apiSubmitUpdate(projectId, payload) {
  return apiFetch(`/projects/${projectId}/training/submit-update`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
