import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { toast } from "sonner";
import { useStore } from "@/lib/store";
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
  currentRound: 0,
  totalRounds: 50,
  blockNode: () => { },
  unblockNode: () => { },
  setAggregationMethod: () => { },
  pause: () => { },
  resume: () => { },
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

  const nodes = useMemo(() => nodesByProject[projectId] || [], [nodesByProject, projectId]);
  const allRounds = useMemo(() => roundsByProject[projectId] || [], [roundsByProject, projectId]);
  const project = useMemo(() => MOCK_PROJECTS.find((p) => p.id === projectId), [projectId]);

  const [currentRound, setCurrentRound] = useState(0);
  const [isRunning, setIsRunning] = useState(true);
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
        patch.trust = clampVal(node.trust + randomBetween(-0.04, 0.01), 0.02, 0.28);
        patch.cosineDistance = clampVal(node.cosineDistance + randomBetween(-0.05, 0.09), 0.5, 0.98);
      } else if (node.isSlow) {
        patch.trust = clampVal(node.trust + randomBetween(-0.01, 0.03), 0.55, 0.95);
        patch.cosineDistance = clampVal(node.cosineDistance + randomBetween(-0.02, 0.02), 0.01, 0.18);
        patch.staleness = clampVal(node.staleness + (Math.random() < 0.4 ? 1 : -1), 0, 9);
      } else {
        patch.trust = clampVal(node.trust + randomBetween(-0.01, 0.02), 0.72, 1.0);
        patch.cosineDistance = clampVal(node.cosineDistance + randomBetween(-0.015, 0.015), 0.01, 0.12);
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
      const duration = node.isSlow ? randomBetween(2.5, 5) : randomBetween(0.4, 1.5);
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

  useEffect(() => {
    if (!projectId) return;
    if (isRunning) {
      intervalRef.current = setInterval(tick, 2000);
    } else {
      clearInterval(intervalRef.current);
    }
    return () => clearInterval(intervalRef.current);
  }, [isRunning, tick, projectId]);

  const blockNode = useCallback(
    (nodeId) => {
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
    [projectId, storeBlockNode, pushActivity, pushNotification, project?.name]
  );

  const unblockNode = useCallback(
    (nodeId) => {
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
    [projectId, storeUnblockNode, pushActivity]
  );

  return useMemo(() => {
    if (!projectId) return NULL_FL;
    return {
      project,
      nodes,
      latestRound: allRounds[allRounds.length - 1] || null,
      allRounds,
      ganttBlocks: ganttBlocksRef.current,
      aggTriggerTimes,
      isRunning,
      currentRound,
      totalRounds: project?.config?.numRounds || 50,
      blockNode,
      unblockNode,
      setAggregationMethod: (method) => setMethod(projectId, method),
      pause: () => setIsRunning(false),
      resume: () => setIsRunning(true),
    };
  }, [
    projectId,
    project,
    nodes,
    allRounds,
    aggTriggerTimes,
    isRunning,
    currentRound,
    blockNode,
    unblockNode,
    setMethod,
  ]);
}
