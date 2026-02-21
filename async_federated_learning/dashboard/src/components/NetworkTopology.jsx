// dashboard/src/components/NetworkTopology.jsx — Hub-and-spoke SVG graph
import React from "react";

const CLIENT_NODES = [
  { id: "client-alice-img", label: "Alice_Image", participant: "Alice", group: 0 },
  { id: "client-alice-txt", label: "Alice_Text", participant: "Alice", group: 0 },
  { id: "client-bob-img", label: "Bob_Image", participant: "Bob", group: 1 },
  { id: "client-bob-txt", label: "Bob_Text", participant: "Bob", group: 1 },
  { id: "client-mallory-img", label: "Mallory_Image", participant: "Mallory", group: 2 },
  { id: "client-mallory-txt", label: "Mallory_Text", participant: "Mallory", group: 2 },
];

function getNodeColor(clientId, trustScores, connectedClients) {
  const isConnected = connectedClients.has(clientId);
  if (!isConnected) return "#95a5a6"; // grey — disconnected

  const trust = trustScores[clientId];
  if (trust === undefined || trust === null) return "#f1c40f"; // yellow — pending
  if (trust === 0.0) return "#e74c3c"; // red — flagged
  if (trust === 1.0) return "#2ecc71"; // green — trusted
  return "#f1c40f"; // yellow — in between
}

export default function NetworkTopology({ trustScores, connectedClients, recentUpdates }) {
  const centerX = 250;
  const centerY = 200;
  const radius = 150;

  // Position nodes in a circle, grouped by participant
  const nodePositions = CLIENT_NODES.map((node, i) => {
    const angle = (i / CLIENT_NODES.length) * 2 * Math.PI - Math.PI / 2;
    return {
      ...node,
      x: centerX + radius * Math.cos(angle),
      y: centerY + radius * Math.sin(angle),
    };
  });

  const connectedSet = new Set(connectedClients || []);

  return (
    <div style={{ border: "1px solid #444", borderRadius: 8, padding: 12, background: "#1a1a2e" }}>
      <h3 style={{ margin: "0 0 8px", color: "#eee", fontSize: 14 }}>Network Topology</h3>
      <svg width={500} height={400} viewBox="0 0 500 400">
        {/* Edges */}
        {nodePositions.map((node) => {
          const isRecent = recentUpdates && recentUpdates.has(node.id);
          return (
            <line
              key={`edge-${node.id}`}
              x1={centerX}
              y1={centerY}
              x2={node.x}
              y2={node.y}
              stroke={isRecent ? "#3498db" : "#555"}
              strokeWidth={isRecent ? 3 : 1.5}
              strokeDasharray={connectedSet.has(node.id) ? "none" : "5,5"}
            >
              {isRecent && (
                <animate
                  attributeName="stroke-opacity"
                  values="1;0.3;1"
                  dur="1s"
                  repeatCount="3"
                />
              )}
            </line>
          );
        })}

        {/* Center Hub */}
        <circle cx={centerX} cy={centerY} r={30} fill="#2c3e50" stroke="#3498db" strokeWidth={3} />
        <text x={centerX} y={centerY - 5} textAnchor="middle" fill="white" fontSize={9} fontWeight="bold">
          Aggregation
        </text>
        <text x={centerX} y={centerY + 8} textAnchor="middle" fill="white" fontSize={9}>
          Hub
        </text>

        {/* Client Nodes */}
        {nodePositions.map((node) => {
          const color = getNodeColor(node.id, trustScores || {}, connectedSet);
          return (
            <g key={node.id}>
              <circle
                cx={node.x}
                cy={node.y}
                r={22}
                fill={color}
                stroke="#333"
                strokeWidth={2}
                opacity={connectedSet.has(node.id) ? 1.0 : 0.4}
              />
              <text
                x={node.x}
                y={node.y - 3}
                textAnchor="middle"
                fill="white"
                fontSize={8}
                fontWeight="bold"
              >
                {node.participant}
              </text>
              <text
                x={node.x}
                y={node.y + 8}
                textAnchor="middle"
                fill="white"
                fontSize={7}
              >
                {node.id.includes("img") ? "IMG" : "TXT"}
              </text>
            </g>
          );
        })}
      </svg>

      {/* Legend */}
      <div style={{ display: "flex", gap: 16, marginTop: 8, fontSize: 11, color: "#ccc" }}>
        <span><span style={{ color: "#2ecc71" }}>●</span> Trusted</span>
        <span><span style={{ color: "#f1c40f" }}>●</span> Pending</span>
        <span><span style={{ color: "#e74c3c" }}>●</span> Flagged</span>
        <span><span style={{ color: "#95a5a6" }}>●</span> Offline</span>
      </div>
    </div>
  );
}
