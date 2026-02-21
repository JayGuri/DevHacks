import { useStore } from "@/lib/store";
import { getAllProjects } from "@/lib/projectUtils";
import { clampVal, randomBetween } from "@/lib/utils";

export default function useContributorStats(userId, projectId) {
  const store = useStore();
  const nodes = store.nodesByProject[projectId] || [];
  const allRounds = store.roundsByProject[projectId] || [];
  const project = getAllProjects(store).find((p) => p.id === projectId);

  const member = project?.members?.find((m) => m.userId === userId);
  // Match by displayId since members store displayId (e.g. "NODE_B2"),
  // not the internal nodeId ("node-1")
  const myNode = nodes.find((n) => n.displayId === member?.nodeId) || null;

  const roundsContributed = myNode?.roundsContributed || 0;
  const numRounds = project?.config?.numRounds || 50;
  const localEpochs = project?.config?.localEpochs || 3;

  return {
    myNode,
    roundsContributed,
    averageTrust: myNode?.trust || 0,
    uptimePercent:
      myNode ? Math.min(100, (roundsContributed / numRounds) * 100) : 0,
    totalUpdates: roundsContributed * localEpochs,
    trustHistory: allRounds.slice(-30).map((r) => ({
      round: r.round,
      trust: clampVal(
        (myNode?.trust || 0.8) + randomBetween(-0.05, 0.05),
        0.3,
        1.0,
      ),
    })),
  };
}
