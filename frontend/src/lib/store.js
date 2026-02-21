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
}));
