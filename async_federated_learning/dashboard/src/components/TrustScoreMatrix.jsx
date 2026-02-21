// dashboard/src/components/TrustScoreMatrix.jsx — Heatmap of trust scores over rounds
import React from "react";

const CLIENT_ORDER = [
  "client-alice-img",
  "client-alice-txt",
  "client-bob-img",
  "client-bob-txt",
  "client-mallory-img",
  "client-mallory-txt",
];

const CLIENT_LABELS = {
  "client-alice-img": "Alice_Image",
  "client-alice-txt": "Alice_Text",
  "client-bob-img": "Bob_Image",
  "client-bob-txt": "Bob_Text",
  "client-mallory-img": "Mallory_Image",
  "client-mallory-txt": "Mallory_Text",
};

function getTrustColor(score) {
  if (score === undefined || score === null) return "#333";
  if (score >= 0.9) return "#2ecc71"; // green
  if (score >= 0.4) return "#f1c40f"; // yellow
  return "#e74c3c"; // red
}

export default function TrustScoreMatrix({ trustHistory }) {
  // trustHistory: { clientId: [{ round, score }, ...] }
  const history = trustHistory || {};

  // Find max round
  let maxRound = 0;
  for (const clientId of CLIENT_ORDER) {
    const entries = history[clientId] || [];
    for (const entry of entries) {
      if (entry.round > maxRound) maxRound = entry.round;
    }
  }

  const rounds = [];
  for (let r = 1; r <= Math.max(maxRound, 1); r++) {
    rounds.push(r);
  }

  // Limit display to last 20 rounds for readability
  const displayRounds = rounds.slice(-20);

  return (
    <div style={{ border: "1px solid #444", borderRadius: 8, padding: 12, background: "#1a1a2e" }}>
      <h3 style={{ margin: "0 0 8px", color: "#eee", fontSize: 14 }}>Trust Score Matrix</h3>
      {maxRound === 0 ? (
        <div style={{ color: "#666", height: 200, display: "flex", alignItems: "center", justifyContent: "center" }}>
          Waiting for trust score data...
        </div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead>
              <tr>
                <th style={{ color: "#aaa", fontSize: 10, padding: "4px 8px", textAlign: "left" }}>
                  Client
                </th>
                {displayRounds.map((r) => (
                  <th
                    key={r}
                    style={{ color: "#aaa", fontSize: 9, padding: "4px 4px", textAlign: "center", minWidth: 28 }}
                  >
                    R{r}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {CLIENT_ORDER.map((clientId) => {
                const entries = history[clientId] || [];
                const scoreByRound = {};
                for (const entry of entries) {
                  scoreByRound[entry.round] = entry.score;
                }

                return (
                  <tr key={clientId}>
                    <td style={{ color: "#ccc", fontSize: 10, padding: "4px 8px", whiteSpace: "nowrap" }}>
                      {CLIENT_LABELS[clientId] || clientId}
                    </td>
                    {displayRounds.map((r) => {
                      const score = scoreByRound[r];
                      const bgColor = getTrustColor(score);
                      return (
                        <td
                          key={r}
                          title={`${CLIENT_LABELS[clientId]} R${r}: ${score !== undefined ? score.toFixed(2) : "N/A"}`}
                          style={{
                            backgroundColor: bgColor,
                            padding: "4px",
                            textAlign: "center",
                            fontSize: 8,
                            color: "white",
                            minWidth: 28,
                            border: "1px solid #222",
                          }}
                        >
                          {score !== undefined ? score.toFixed(1) : ""}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Legend */}
      <div style={{ display: "flex", gap: 16, marginTop: 8, fontSize: 11, color: "#ccc" }}>
        <span><span style={{ color: "#2ecc71" }}>■</span> 1.0 (Trusted)</span>
        <span><span style={{ color: "#f1c40f" }}>■</span> 0.5 (Uncertain)</span>
        <span><span style={{ color: "#e74c3c" }}>■</span> 0.0 (Rejected)</span>
      </div>
    </div>
  );
}
