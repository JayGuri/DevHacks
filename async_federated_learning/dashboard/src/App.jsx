// dashboard/src/App.jsx — FedBuff Telemetry Dashboard
import React, { useState, useCallback } from "react";
import { useSSEFeed } from "./api/sseHook";
import NetworkTopology from "./components/NetworkTopology";
import LiveLog from "./components/LiveLog";
import ConvergenceCurve from "./components/ConvergenceCurve";
import TrustScoreMatrix from "./components/TrustScoreMatrix";

const SERVER_IP = window.location.hostname || "localhost";
const SSE_URL = `http://${SERVER_IP}:8765/telemetry/stream`;

export default function App() {
  const [selectedTask, setSelectedTask] = useState("femnist");
  const [logs, setLogs] = useState([]);
  const [connectedClients, setConnectedClients] = useState(new Set());
  const [trustScores, setTrustScores] = useState({});
  const [trustHistory, setTrustHistory] = useState({});
  const [lossHistory, setLossHistory] = useState({ femnist: [], shakespeare: [] });
  const [roundInfo, setRoundInfo] = useState({ femnist: 0, shakespeare: 0 });
  const [recentUpdates, setRecentUpdates] = useState(new Set());

  const onEvent = useCallback((event) => {
    const eventType = event.event;
    const data = event.data || {};

    // Add to logs (newest first)
    setLogs((prev) => {
      const newLogs = [event, ...prev];
      return newLogs.slice(0, 200);
    });

    switch (eventType) {
      case "client_joined":
        setConnectedClients((prev) => {
          const next = new Set(prev);
          next.add(data.client_id);
          return next;
        });
        break;

      case "client_left":
        setConnectedClients((prev) => {
          const next = new Set(prev);
          next.delete(data.client_id);
          return next;
        });
        break;

      case "update_received":
        setRecentUpdates((prev) => {
          const next = new Set(prev);
          next.add(data.client_id);
          // Clear after 2 seconds
          setTimeout(() => {
            setRecentUpdates((p) => {
              const n = new Set(p);
              n.delete(data.client_id);
              return n;
            });
          }, 2000);
          return next;
        });
        break;

      case "trust_score":
        setTrustScores((prev) => ({
          ...prev,
          [data.client_id]: data.score,
        }));
        setTrustHistory((prev) => {
          const clientHistory = prev[data.client_id] || [];
          return {
            ...prev,
            [data.client_id]: [...clientHistory, { round: data.round, score: data.score }],
          };
        });
        break;

      case "round_complete":
        if (data.task) {
          setLossHistory((prev) => ({
            ...prev,
            [data.task]: [...(prev[data.task] || []), data.loss],
          }));
          setRoundInfo((prev) => ({
            ...prev,
            [data.task]: data.round,
          }));
        }
        break;

      case "update_rejected":
        setTrustScores((prev) => ({
          ...prev,
          [data.client_id]: 0.0,
        }));
        break;

      default:
        break;
    }
  }, []);

  useSSEFeed(SSE_URL, onEvent);

  const toggleTask = () => {
    setSelectedTask((prev) => (prev === "femnist" ? "shakespeare" : "femnist"));
  };

  return (
    <div style={{ fontFamily: "sans-serif", background: "#0d0d1a", color: "#eee", minHeight: "100vh", padding: 20 }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, color: "#3498db" }}>FedBuff Dashboard</h1>
          <p style={{ margin: "4px 0 0", fontSize: 12, color: "#888" }}>
            Buffered Async Federated Learning — Live Telemetry
          </p>
        </div>

        <div style={{ display: "flex", gap: 20, alignItems: "center" }}>
          <div style={{ fontSize: 12, color: "#aaa" }}>
            FEMNIST Round: <strong style={{ color: "#3498db" }}>{roundInfo.femnist}</strong>
            {" | "}
            Shakespeare Round: <strong style={{ color: "#e67e22" }}>{roundInfo.shakespeare}</strong>
            {" | "}
            Clients: <strong style={{ color: "#2ecc71" }}>{connectedClients.size}</strong>
          </div>
          <button
            onClick={toggleTask}
            style={{
              padding: "8px 16px",
              background: selectedTask === "femnist" ? "#3498db" : "#e67e22",
              color: "white",
              border: "none",
              borderRadius: 6,
              cursor: "pointer",
              fontSize: 12,
              fontWeight: "bold",
            }}
          >
            {selectedTask === "femnist" ? "Image Task (FEMNIST)" : "Text Task (Shakespeare)"}
          </button>
        </div>
      </div>

      {/* Four-panel layout */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <NetworkTopology
          trustScores={trustScores}
          connectedClients={connectedClients}
          recentUpdates={recentUpdates}
        />
        <LiveLog logs={logs} />
        <ConvergenceCurve
          lossHistory={lossHistory[selectedTask] || []}
          selectedTask={selectedTask}
        />
        <TrustScoreMatrix trustHistory={trustHistory} />
      </div>
    </div>
  );
}
