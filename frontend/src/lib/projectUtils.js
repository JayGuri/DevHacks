import { MOCK_PROJECTS } from "@/lib/mockData";
import { USE_MOCK } from "@/lib/config";

/** Combine static mock projects with dynamically created ones from the store,
 *  or use API-fetched projects when USE_MOCK is false */
export function getAllProjects(store) {
  if (!USE_MOCK) {
    return store.projects || [];
  }
  return [...MOCK_PROJECTS, ...(store.extraProjects || [])];
}

/** Projects this user has joined */
export function getUserJoinedProjects(userId, store) {
  if (!USE_MOCK) {
    // In API mode, the project list already reflects membership via the backend
    const projects = store.projects || [];
    return projects.filter((p) => p.members?.some((m) => m.userId === userId));
  }
  const joinedIds = store.userProjects[userId] || [];
  return getAllProjects(store).filter((p) => joinedIds.includes(p.id));
}

/** Projects where this user is the lead */
export function getUserManagedProjects(userId, store) {
  if (!USE_MOCK) {
    const projects = store.projects || [];
    return projects.filter((p) =>
      p.members?.some((m) => m.userId === userId && m.role === "lead"),
    );
  }
  return getAllProjects(store).filter((p) =>
    isProjectLead(userId, p.id, store),
  );
}

/** All public, active projects */
export function getPublicProjects(store) {
  return getAllProjects(store).filter(
    (p) => p.visibility === "public" && p.isActive,
  );
}

/** Public, active projects the user hasn't joined yet */
export function getAvailableToJoin(userId, store) {
  if (!USE_MOCK) {
    const projects = store.projects || [];
    return projects.filter(
      (p) =>
        p.isActive &&
        p.visibility === "public" &&
        !p.members?.some((m) => m.userId === userId),
    );
  }
  const joinedIds = store.userProjects[userId] || [];
  return getAllProjects(store).filter(
    (p) => p.isActive && !joinedIds.includes(p.id) && p.visibility === "public",
  );
}

/** Pending join requests for a specific project */
export function getPendingRequests(projectId, store) {
  const requests =
    USE_MOCK ? store.joinRequests || [] : store.fetchedJoinRequests || [];
  return requests.filter(
    (r) => r.projectId === projectId && r.status === "pending",
  );
}

/** Check if a user already has a pending request for a project */
export function getUserPendingRequest(userId, projectId, store) {
  const requests =
    USE_MOCK ? store.joinRequests || [] : store.fetchedJoinRequests || [];
  return requests.find(
    (r) =>
      r.userId === userId &&
      r.projectId === projectId &&
      r.status === "pending",
  );
}

/**
 * Get a user's role in a specific project.
 * Checks store.projectRoles overrides first (mock), then falls back to the
 * members array in the project data.
 */
export function getUserProjectRole(userId, projectId, store) {
  if (USE_MOCK) {
    const override = store.projectRoles?.[projectId]?.[userId];
    if (override) return override;
  }
  const project = getAllProjects(store).find((p) => p.id === projectId);
  const member = project?.members?.find((m) => m.userId === userId);
  return member?.role || null;
}

/** Shorthand: is this user a lead in this project? */
export function isProjectLead(userId, projectId, store) {
  return getUserProjectRole(userId, projectId, store) === "lead";
}
