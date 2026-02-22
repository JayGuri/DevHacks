import { randomBetween, clampVal } from "./utils";

// ─── Users ───────────────────────────────────────────────────────────
export const MOCK_USERS = [
  { id: "u1", name: "Alex Morgan",  email: "lead@arfl.dev",          password: "password", role: "TEAM_LEAD",   subscriptionTier: "PRO",  createdAt: "2025-01-15" },
  { id: "u2", name: "Sam Chen",     email: "contributor1@arfl.dev",  password: "password", role: "CONTRIBUTOR", subscriptionTier: "FREE", createdAt: "2025-02-01" },
  { id: "u3", name: "Priya Patel",  email: "contributor2@arfl.dev",  password: "password", role: "CONTRIBUTOR", subscriptionTier: "FREE", createdAt: "2025-02-10" },
  { id: "u4", name: "Jordan Lee",   email: "contributor3@arfl.dev",  password: "password", role: "CONTRIBUTOR", subscriptionTier: "FREE", createdAt: "2025-02-20" },
  { id: "u5", name: "Riley Kim",    email: "contributor4@arfl.dev",  password: "password", role: "CONTRIBUTOR", subscriptionTier: "FREE", createdAt: "2025-03-01" },
  { id: "u6", name: "Taylor Wu",    email: "contributor5@arfl.dev",  password: "password", role: "CONTRIBUTOR", subscriptionTier: "FREE", createdAt: "2025-03-10" },
  // Dev testing: FREE-tier Team Lead to verify tier gates independently of RBAC
  { id: "u7", name: "Dev Free Lead", email: "free-lead@arfl.dev",    password: "password", role: "TEAM_LEAD",   subscriptionTier: "FREE", createdAt: "2025-03-15" },
];

// ─── Projects ────────────────────────────────────────────────────────
export const MOCK_PROJECTS = [
  {
    id: "p1",
    name: "Hospital Network FL",
    description: "Federated learning across 10 hospital nodes for patient outcome prediction with sign-flipping attack simulation.",
    createdBy: "u1",
    createdAt: "2025-02-15",
    isActive: true,
    visibility: "public",
    inviteCode: null,
    joinRequests: [],
    maxMembers: 10,
    config: {
      numClients: 10,
      byzantineFraction: 0.2,
      attackType: "sign_flipping",
      aggregationMethod: "trimmed_mean",
      numRounds: 50,
      dirichletAlpha: 0.5,
      useDifferentialPrivacy: true,
      dpNoiseMultiplier: 0.1,
      dpMaxGradNorm: 1.0,
      sabdAlpha: 0.5,
      localEpochs: 3,
    },
    members: [
      { userId: "u1", userName: "Alex Morgan",  nodeId: "NODE_A1", role: "lead",        joinedAt: "2025-02-15" },
      { userId: "u2", userName: "Sam Chen",     nodeId: "NODE_B2", role: "contributor",  joinedAt: "2025-02-16" },
      { userId: "u3", userName: "Priya Patel",  nodeId: "NODE_C3", role: "contributor",  joinedAt: "2025-02-17" },
    ],
  },
  {
    id: "p2",
    name: "Cross-Bank Fraud Detection",
    description: "Multi-bank federated fraud detection using scaling attack resilience and coordinate-wise median aggregation.",
    createdBy: "u1",
    createdAt: "2025-03-01",
    isActive: true,
    visibility: "private",
    inviteCode: "FX9K3R",
    joinRequests: [],
    maxMembers: 10,
    config: {
      numClients: 10,
      byzantineFraction: 0.2,
      attackType: "scaling",
      aggregationMethod: "coordinate_median",
      numRounds: 50,
      dirichletAlpha: 0.5,
      useDifferentialPrivacy: true,
      dpNoiseMultiplier: 0.1,
      dpMaxGradNorm: 1.0,
      sabdAlpha: 0.5,
      localEpochs: 3,
    },
    members: [
      { userId: "u1", userName: "Alex Morgan", nodeId: "NODE_A1", role: "lead",        joinedAt: "2025-03-01" },
      { userId: "u4", userName: "Jordan Lee",  nodeId: "NODE_B2", role: "contributor",  joinedAt: "2025-03-02" },
    ],
  },
  {
    id: "p3",
    name: "IoT Anomaly Detection",
    description: "Edge-device federated anomaly detection with Gaussian noise attack vectors and reputation-based aggregation.",
    createdBy: "u1",
    createdAt: "2025-03-15",
    isActive: true,
    visibility: "public",
    inviteCode: null,
    joinRequests: [],
    maxMembers: 10,
    config: {
      numClients: 10,
      byzantineFraction: 0.2,
      attackType: "gaussian_noise",
      aggregationMethod: "reputation",
      numRounds: 50,
      dirichletAlpha: 0.5,
      useDifferentialPrivacy: true,
      dpNoiseMultiplier: 0.1,
      dpMaxGradNorm: 1.0,
      sabdAlpha: 0.5,
      localEpochs: 3,
    },
    members: [
      { userId: "u1", userName: "Alex Morgan", nodeId: "NODE_A1", role: "lead",        joinedAt: "2025-03-15" },
      { userId: "u2", userName: "Sam Chen",    nodeId: "NODE_B2", role: "contributor",  joinedAt: "2025-03-16" },
      { userId: "u5", userName: "Riley Kim",   nodeId: "NODE_C3", role: "contributor",  joinedAt: "2025-03-17" },
    ],
  },
];

// ─── Node generator ──────────────────────────────────────────────────
// Produces a realistic node array for a given project config.
// Fixed indices for byzantine (3,7) and slow (1,5,8) nodes allow
// consistent demo behaviour across refreshes.

const DISPLAY_LETTERS = "ABCDEFGHIJ";
const BYZANTINE_INDICES = new Set([3, 7]);
const SLOW_INDICES = new Set([1, 5, 8]);

export function generateNodes(config) {
  const count = config.numClients || 10;
  return Array.from({ length: count }, (_, i) => {
    const letter = DISPLAY_LETTERS[i] || String.fromCharCode(65 + i);
    const number = (i % 3) + 1;
    const displayId = `NODE_${letter}${number}`;
    const isByzantine = BYZANTINE_INDICES.has(i);
    const isSlow = SLOW_INDICES.has(i);

    let status, trust, cosineDistance, staleness;

    if (isByzantine) {
      status = "BYZANTINE";
      trust = randomBetween(0.05, 0.2);
      cosineDistance = randomBetween(0.6, 0.95);
      staleness = Math.floor(randomBetween(5, 15));
    } else if (isSlow) {
      status = "SLOW";
      trust = randomBetween(0.7, 0.9);
      cosineDistance = randomBetween(0.02, 0.15);
      staleness = Math.floor(randomBetween(2, 6));
    } else {
      status = "ACTIVE";
      trust = randomBetween(0.85, 1.0);
      cosineDistance = randomBetween(0.01, 0.1);
      staleness = Math.floor(randomBetween(0, 2));
    }

    return {
      nodeId: `node-${i}`,
      displayId,
      userId: null,
      status,
      trust,
      cosineDistance,
      staleness,
      roundsContributed: 0,
      isByzantine,
      isSlow,
      isBlocked: false,
    };
  });
}

// ─── Round metrics generator ─────────────────────────────────────────
// Simulates a single round of FL training metrics.
// FedAvg stays low (simulates no byzantine protection) while
// robust aggregators converge toward 90%+ accuracy.

export function generateRoundMetrics(round) {
  const trimmedAccuracy = clampVal(
    10 + 81 * (1 - Math.exp(-round / 12)) + randomBetween(-1.5, 1.5),
    0,
    93
  );

  return {
    round,
    timestamp: new Date().toISOString(),
    fedavgAccuracy: clampVal(
      13 + Math.sin(round * 0.4) * 4 + randomBetween(-2, 2),
      8,
      22
    ),
    trimmedAccuracy,
    medianAccuracy: clampVal(
      8 + 79 * (1 - Math.exp(-round / 15)) + randomBetween(-1.5, 1.5),
      0,
      89
    ),
    globalAccuracy: trimmedAccuracy,
    globalLoss: clampVal(
      2.3 * Math.exp(-round / 20) + randomBetween(-0.05, 0.05),
      0.2,
      2.5
    ),
    epsilonSpent: clampVal(round * 0.065, 0, 9.8),
    flaggedNodes: round > 3 ? 2 + (Math.random() < 0.2 ? 1 : 0) : 0,
    activeNodes: 8 + (Math.random() < 0.15 ? -1 : 0),
    sabdFPR: clampVal(0.72 - 0.64 * (round / 100), 0.05, 0.72),
    sabdRecall: clampVal(0.91 + 0.06 * (round / 100), 0.91, 0.97),
    aggregationMethod: "trimmed_mean",
  };
}
