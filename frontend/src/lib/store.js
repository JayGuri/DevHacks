import { create } from "zustand";

const savedMode = localStorage.getItem("arfl-view-mode") || "simple";

export const useStore = create((set) => ({
  // ── Auth ────────────────────────────────────────────────
  user: null,
  setUser: (u) => set({ user: u }),

  // ── View mode (persisted to localStorage) ──────────────
  viewMode: savedMode,
  setViewMode: (m) => {
    localStorage.setItem("arfl-view-mode", m);
    set({ viewMode: m });
  },

  // ── Active project ─────────────────────────────────────
  activeProjectId: null,
  setActiveProjectId: (id) => set({ activeProjectId: id }),

  // ── Node state per project ─────────────────────────────
  nodesByProject: {},
  setNodes: (projectId, nodes) =>
    set((s) => ({
      nodesByProject: { ...s.nodesByProject, [projectId]: nodes },
    })),

  setAllNodes: (projectId, nodes) =>
    set((s) => ({
      nodesByProject: { ...s.nodesByProject, [projectId]: nodes }
    })),

  updateNode: (projectId, nodeId, patch) =>
    set((s) => {
      const nodes = s.nodesByProject[projectId] || [];
      return {
        nodesByProject: {
          ...s.nodesByProject,
          [projectId]: nodes.map((n) =>
            n.nodeId === nodeId ? { ...n, ...patch } : n
          ),
        },
      };
    }),

  blockNode: (projectId, nodeId) =>
    set((s) => {
      const nodes = s.nodesByProject[projectId] || [];
      return {
        nodesByProject: {
          ...s.nodesByProject,
          [projectId]: nodes.map((n) =>
            n.nodeId === nodeId
              ? { ...n, isBlocked: true, status: "BLOCKED" }
              : n
          ),
        },
      };
    }),

  unblockNode: (projectId, nodeId) =>
    set((s) => {
      const nodes = s.nodesByProject[projectId] || [];
      return {
        nodesByProject: {
          ...s.nodesByProject,
          [projectId]: nodes.map((n) => {
            if (n.nodeId !== nodeId) return n;
            // Restore original status based on node type
            let restoredStatus = "ACTIVE";
            if (n.isByzantine) restoredStatus = "BYZANTINE";
            else if (n.isSlow) restoredStatus = "SLOW";
            return { ...n, isBlocked: false, status: restoredStatus };
          }),
        },
      };
    }),

  // ── Round metrics per project (keep last 80) ──────────
  roundsByProject: {},
  appendRound: (projectId, metrics) =>
    set((s) => {
      const existing = s.roundsByProject[projectId] || [];
      const updated = [...existing, metrics].slice(-80);
      return {
        roundsByProject: { ...s.roundsByProject, [projectId]: updated },
      };
    }),

  // ── Aggregation method per project ─────────────────────
  methodByProject: {},
  setMethod: (projectId, method) =>
    set((s) => ({
      methodByProject: { ...s.methodByProject, [projectId]: method },
    })),

  // ── Activity log (most-recent first, cap at 20) ───────
  activityLog: [],
  pushActivity: (event) =>
    set((s) => ({
      activityLog: [event, ...s.activityLog].slice(0, 20),
    })),

  // ── User-joined projects (mock join flow) ──────────────
  userProjects: {
    u1: ["p1", "p2", "p3"],
    u2: ["p1", "p3"],
    u3: ["p1"],
    u4: ["p2"],
    u5: ["p3"],
    u6: [],
  },
  joinProject: (userId, projectId) =>
    set((s) => {
      const current = s.userProjects[userId] || [];
      if (current.includes(projectId)) return s;
      return {
        userProjects: {
          ...s.userProjects,
          [userId]: [...current, projectId],
        },
      };
    }),

  // ── Join request management ───────────────────────────
  joinRequests: [],
  submitJoinRequest: (request) =>
    set((s) => ({
      joinRequests: [
        ...s.joinRequests,
        {
          ...request,
          id: `req-${Date.now()}`,
          status: "pending",
          requestedAt: new Date().toISOString(),
          resolvedAt: null,
          resolvedBy: null,
        },
      ],
    })),
  approveRequest: (requestId, leadId) =>
    set((s) => {
      const req = s.joinRequests.find((r) => r.id === requestId);
      if (!req) return s;
      const currentProjects = s.userProjects[req.userId] || [];
      return {
        joinRequests: s.joinRequests.map((r) =>
          r.id === requestId
            ? { ...r, status: "approved", resolvedAt: new Date().toISOString(), resolvedBy: leadId }
            : r
        ),
        userProjects: {
          ...s.userProjects,
          [req.userId]: [...currentProjects, req.projectId],
        },
      };
    }),
  rejectRequest: (requestId, leadId) =>
    set((s) => ({
      joinRequests: s.joinRequests.map((r) =>
        r.id === requestId
          ? { ...r, status: "rejected", resolvedAt: new Date().toISOString(), resolvedBy: leadId }
          : r
      ),
    })),

  // ── Per-project role overrides ────────────────────────
  projectRoles: {
    p1: { u1: "lead", u2: "contributor", u3: "contributor" },
    p2: { u1: "lead", u4: "contributor" },
    p3: { u1: "lead", u2: "contributor", u5: "contributor" },
  },
  setProjectRole: (projectId, userId, role) =>
    set((s) => ({
      projectRoles: {
        ...s.projectRoles,
        [projectId]: { ...(s.projectRoles[projectId] || {}), [userId]: role },
      },
    })),

  // ── Notifications ─────────────────────────────────────
  notifications: [],
  pushNotification: (notif) =>
    set((s) => ({
      notifications: [
        { ...notif, id: `notif-${Date.now()}`, read: false, createdAt: new Date().toISOString() },
        ...s.notifications,
      ].slice(0, 50),
    })),
  markNotificationRead: (id) =>
    set((s) => ({
      notifications: s.notifications.map((n) =>
        n.id === id ? { ...n, read: true } : n
      ),
    })),
  markAllRead: () =>
    set((s) => ({
      notifications: s.notifications.map((n) => ({ ...n, read: true })),
    })),

  // ── Extra projects (created via admin dialog) ─────────
  extraProjects: [],
  addProject: (project) =>
    set((s) => ({ extraProjects: [...s.extraProjects, project] })),
  archiveProject: (id) =>
    set((s) => ({
      extraProjects: s.extraProjects.map((p) =>
        p.id === id ? { ...p, isActive: false } : p
      ),
    })),
  updateExtraProject: (id, patch) =>
    set((s) => ({
      extraProjects: s.extraProjects.map((p) =>
        p.id === id ? { ...p, ...patch } : p
      ),
    })),
}));
