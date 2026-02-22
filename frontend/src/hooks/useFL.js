import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { toast } from "sonner";
import { useStore } from "@/lib/store";
import { USE_MOCK, WS_BASE_URL } from "@/lib/config";
import {
  apiStartTraining,
  apiPauseTraining,
  apiResumeTraining,
  apiBlockNode as apiBlockNodeFn,
  apiUnblockNode as apiUnblockNodeFn,
  apiTrainingStatus,
  apiUpdateTrainingConfig,
  apiListProjects,
  getToken,
} from "@/lib/api";
import { getAllProjects } from "@/lib/projectUtils";
import {
  MOCK_PROJECTS,
  generateNodes,
  generateRoundMetrics,
} from "@/lib/mockData";
import { randomBetween, clampVal } from "@/lib/utils";

const NULL_FL = {
  project: null,
  nodes: [],
  latestRound: null,
  allRounds: [],
  ganttBlocks: [],
  aggTriggerTimes: [],
  isRunning: false,
  trainingStatus: "idle",
  loading: false,
  currentRound: 0,
  totalRounds: 50,
  blockNode: () => {},
  unblockNode: () => {},
  setAggregationMethod: () => {},
  pause: () => {},
  resume: () => {},
};

export default function useFL(projectId) {
  const nodesByProject = useStore((s) => s.nodesByProject);
  const roundsByProject = useStore((s) => s.roundsByProject);
  const setNodes = useStore((s) => s.setNodes);
  const setAllNodes = useStore((s) => s.setAllNodes); // Make sure this is in store.js
  const appendRound = useStore((s) => s.appendRound);
  const setMethod = useStore((s) => s.setMethod);
  const pushActivity = useStore((s) => s.pushActivity);
  const storeBlockNode = useStore((s) => s.blockNode);
  const storeUnblockNode = useStore((s) => s.unblockNode);
  const pushNotification = useStore((s) => s.pushNotification);

  const nodes = useMemo(
    () => nodesByProject[projectId] || [],
    [nodesByProject, projectId],
  );
  const allRounds = useMemo(
    () => roundsByProject[projectId] || [],
    [roundsByProject, projectId],
  );
  const project = useMemo(() => {
    if (USE_MOCK) {
      return MOCK_PROJECTS.find((p) => p.id === projectId);
    }
    const store = useStore.getState();
    return (store.projects || []).find((p) => p.id === projectId);
  }, [projectId]);

  const [currentRound, setCurrentRound] = useState(0);
  const [isRunning, setIsRunning] = useState(true);
  const [trainingStatus, setTrainingStatus] = useState("idle");
  const [loading, setLoading] = useState(!USE_MOCK);
  const [aggTriggerTimes, setAggTriggerTimes] = useState([]);

  const intervalRef = useRef(null);
  const currentRoundRef = useRef(0);
  const ganttBlocksRef = useRef([]);
  const nodesRef = useRef(nodes);

  useEffect(() => {
    nodesRef.current = nodes;
  }, [nodes]);

  useEffect(() => {
    if (!project || !projectId) return;

    const existingNodes = useStore.getState().nodesByProject[projectId];
    if (!existingNodes || existingNodes.length === 0) {
      setNodes(projectId, generateNodes(project.config));
    }

    const existingRounds = useStore.getState().roundsByProject[projectId];
    if (!existingRounds || existingRounds.length === 0) {
      for (let i = 1; i <= 20; i++) {
        appendRound(projectId, generateRoundMetrics(i));
      }
      setCurrentRound(20);
      currentRoundRef.current = 20;
    } else {
      const lastRound = existingRounds[existingRounds.length - 1]?.round || 0;
      setCurrentRound(lastRound);
      currentRoundRef.current = lastRound;
    }
    setLoading(false);
  }, [projectId, project, setNodes, appendRound]);

  const tick = useCallback(() => {
    const round = currentRoundRef.current + 1;
    currentRoundRef.current = round;
    setCurrentRound(round);

    const currentNodes = [...nodesRef.current];
    let hasChanges = false;
    const newGanttBlocks = [...ganttBlocksRef.current];

    const updatedNodes = currentNodes.map((node, index) => {
      if (node.isBlocked) return node;
      hasChanges = true;

      const patch = { ...node };

      if (node.isByzantine) {
        patch.trust = clampVal(
          node.trust + randomBetween(-0.04, 0.01),
          0.02,
          0.28,
        );
        patch.cosineDistance = clampVal(
          node.cosineDistance + randomBetween(-0.05, 0.09),
          0.5,
          0.98,
        );
      } else if (node.isSlow) {
        patch.trust = clampVal(
          node.trust + randomBetween(-0.01, 0.03),
          0.55,
          0.95,
        );
        patch.cosineDistance = clampVal(
          node.cosineDistance + randomBetween(-0.02, 0.02),
          0.01,
          0.18,
        );
        patch.staleness = clampVal(
          node.staleness + (Math.random() < 0.4 ? 1 : -1),
          0,
          9,
        );
      } else {
        patch.trust = clampVal(
          node.trust + randomBetween(-0.01, 0.02),
          0.72,
          1.0,
        );
        patch.cosineDistance = clampVal(
          node.cosineDistance + randomBetween(-0.015, 0.015),
          0.01,
          0.12,
        );
        patch.staleness = Math.random() < 0.1 ? 1 : 0;
      }

      if (patch.cosineDistance > 0.45 && node.status !== "BYZANTINE") {
        pushNotification({
          type: "alert",
          message: `Node ${node.displayId} flagged as Byzantine in ${project?.name || projectId}`,
          projectId,
        });
        patch.status = "BYZANTINE";
      }

      patch.roundsContributed = (node.roundsContributed || 0) + 1;

      // Update GanttRef
      const nowSec = Date.now() / 1000;
      const duration =
        node.isSlow ? randomBetween(2.5, 5) : randomBetween(0.4, 1.5);
      newGanttBlocks.push({
        nodeId: node.nodeId,
        displayId: node.displayId,
        clientIdx: index,
        startSec: nowSec - duration,
        endSec: nowSec,
        isByzantine: node.isByzantine,
        isSlow: node.isSlow,
      });

      return patch;
    });

    if (hasChanges) {
      setAllNodes(projectId, updatedNodes);
      ganttBlocksRef.current = newGanttBlocks.slice(-40);
    }

    appendRound(projectId, generateRoundMetrics(round));

    if (round % 5 === 0) {
      setAggTriggerTimes((prev) => [...prev.slice(-12), Date.now() / 1000]);
    }
  }, [projectId, setAllNodes, appendRound, project?.name, pushNotification]);

  // ── WebSocket connection for API mode ──────────────────
  const wsRef = useRef(null);

  useEffect(() => {
    if (USE_MOCK || !projectId) return;

    const token = getToken() || "";
    const wsUrl = `${WS_BASE_URL}/api/ws?projectId=${projectId}&token=${token}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log(`[WS] Connected to training for ${projectId}`);
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        const { event: eventType, data } = msg;

        if (eventType === "round_complete") {
          if (data.metrics) {
            appendRound(projectId, data.metrics);
            setCurrentRound(data.metrics.round);
            currentRoundRef.current = data.metrics.round;
          }
          if (data.nodes) {
            setAllNodes(projectId, data.nodes);
          }
          if (data.ganttBlocks) {
            ganttBlocksRef.current = [
              ...ganttBlocksRef.current,
              ...data.ganttBlocks,
            ].slice(-40);
          }
        } else if (eventType === "training_status") {
          const st = data.status;
          setIsRunning(st === "running");
          setTrainingStatus(st || "idle");
          setCurrentRound(data.currentRound || 0);
          currentRoundRef.current = data.currentRound || 0;
          setLoading(false);
        } else if (eventType === "node_flagged") {
          pushNotification({
            type: "alert",
            message: `Node ${data.displayId} flagged: ${data.reason}`,
            projectId,
          });
        } else if (eventType === "initial_state") {
          if (data.nodes) setAllNodes(projectId, data.nodes);
          if (data.metrics) {
            data.metrics.forEach((m) => appendRound(projectId, m));
          }
          if (data.status) {
            const st = data.status.status;
            setIsRunning(st === "running");
            setTrainingStatus(st || "idle");
            setCurrentRound(data.status.currentRound || 0);
            currentRoundRef.current = data.status.currentRound || 0;
          }
          setLoading(false);
        }
      } catch (err) {
        console.error("[WS] Parse error:", err);
      }
    };

    ws.onerror = () => console.error("[WS] WebSocket error");
    ws.onclose = () => console.log("[WS] Disconnected");

    // Ping every 30s to keep alive
    const pingInterval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "ping" }));
      }
    }, 30000);

    return () => {
      clearInterval(pingInterval);
      ws.close();
    };
  }, [projectId, appendRound, setAllNodes, pushNotification]);

  // ── Mock simulation timer ─────────────────────────────
  useEffect(() => {
    if (!USE_MOCK || !projectId) return;
    if (isRunning) {
      intervalRef.current = setInterval(tick, 2000);
    } else {
      clearInterval(intervalRef.current);
    }
    return () => clearInterval(intervalRef.current);
  }, [isRunning, tick, projectId]);

  const blockNode = useCallback(
    async (nodeId) => {
      if (!USE_MOCK) {
        try {
          await apiBlockNodeFn(projectId, nodeId);
        } catch (err) {
          toast.error(err.message || "Failed to block node");
          return;
        }
      }
      storeBlockNode(projectId, nodeId);
      const node = nodesRef.current.find((n) => n.nodeId === nodeId);
      const displayId = node?.displayId || nodeId;
      pushActivity({
        type: "block",
        nodeId,
        displayId,
        projectId,
        timestamp: new Date().toISOString(),
      });
      pushNotification({
        type: "node_blocked",
        message: `Node ${displayId} was blocked in ${project?.name || projectId}`,
        projectId,
      });
      toast.success(`${displayId} blocked`);
    },
    [projectId, storeBlockNode, pushActivity, pushNotification, project?.name],
  );

  const unblockNode = useCallback(
    async (nodeId) => {
      if (!USE_MOCK) {
        try {
          await apiUnblockNodeFn(projectId, nodeId);
        } catch (err) {
          toast.error(err.message || "Failed to unblock node");
          return;
        }
      }
      storeUnblockNode(projectId, nodeId);
      const node = nodesRef.current.find((n) => n.nodeId === nodeId);
      const displayId = node?.displayId || nodeId;
      pushActivity({
        type: "unblock",
        nodeId,
        displayId,
        projectId,
        timestamp: new Date().toISOString(),
      });
      toast.success(`${displayId} unblocked`);
    },
    [projectId, storeUnblockNode, pushActivity],
  );

  return useMemo(() => {
    if (!projectId) return NULL_FL;
    // Derive status string: if mock mode, derive from isRunning flag
    const status =
      USE_MOCK ?
        isRunning ? "running"
        : "idle"
      : trainingStatus;
    return {
      project,
      nodes,
      latestRound: allRounds[allRounds.length - 1] || null,
      allRounds,
      ganttBlocks: ganttBlocksRef.current,
      aggTriggerTimes,
      isRunning,
      trainingStatus: status,
      currentRound,
      totalRounds: project?.config?.numRounds || 50,
      loading,
      blockNode,
      unblockNode,
      setAggregationMethod: (method) => {
        setMethod(projectId, method);
        if (!USE_MOCK) {
          apiUpdateTrainingConfig(projectId, {
            aggregationMethod: method,
          }).catch(() => {});
        }
      },
      pause: async () => {
        if (!USE_MOCK) {
          try {
            await apiPauseTraining(projectId);
          } catch (err) {
            toast.error(err.message);
            return;
          }
        }
        setIsRunning(false);
      },
      resume: async () => {
        if (!USE_MOCK) {
          try {
            await apiResumeTraining(projectId);
          } catch (err) {
            toast.error(err.message);
            return;
          }
        }
        setIsRunning(true);
      },
      start: async () => {
        if (!USE_MOCK) {
          try {
            await apiStartTraining(projectId);
          } catch (err) {
            toast.error(err.message);
            return;
          }
        }
        setIsRunning(true);
      },
    };
  }, [
    projectId,
    project,
    nodes,
    allRounds,
    aggTriggerTimes,
    isRunning,
    trainingStatus,
    loading,
    currentRound,
    blockNode,
    unblockNode,
    setMethod,
  ]);
}
