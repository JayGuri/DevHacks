// dashboard/src/components/LiveLog.jsx — Scrolling event log
import React, { useRef, useEffect } from "react";

const MAX_ENTRIES = 200;

function formatTime(isoString) {
  if (!isoString) return "--:--:--";
  try {
    const d = new Date(isoString);
    return d.toLocaleTimeString("en-US", { hour12: false });
  } catch {
    return "--:--:--";
  }
}

function getEventColor(eventType) {
  switch (eventType) {
    case "round_complete":
      return "#2ecc71";
    case "update_rejected":
    case "client_rejected":
      return "#e74c3c";
    case "client_joined":
      return "#3498db";
    case "client_left":
      return "#f39c12";
    case "trust_score":
      return "#9b59b6";
    default:
      return "#95a5a6";
  }
}

function formatDetail(event) {
  const data = event.data || {};
  const eventType = event.event || "";

  switch (eventType) {
    case "round_complete":
      return `round=${data.round} loss=${(data.loss || 0).toFixed(4)} accepted=${data.accepted_count}`;
    case "update_received":
      return `samples=${data.num_samples} loss=${(data.local_loss || 0).toFixed(4)} norm=${(data.norm || 0).toFixed(2)}`;
    case "update_rejected":
      return `reason=${data.reason} norm=${(data.norm || 0).toFixed(2)}`;
    case "client_joined":
      return `${data.display_name} (${data.participant})`;
    case "client_left":
      return `${data.participant} disconnected`;
    case "trust_score":
      return `score=${(data.score || 0).toFixed(2)} round=${data.round}`;
    case "buffer_size":
      return `size=${data.size}/${data.capacity}`;
    default:
      return JSON.stringify(data).slice(0, 80);
  }
}

export default function LiveLog({ logs }) {
  const containerRef = useRef(null);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = 0;
    }
  }, [logs]);

  const displayLogs = (logs || []).slice(0, MAX_ENTRIES);

  return (
    <div style={{ border: "1px solid #444", borderRadius: 8, padding: 12, background: "#1a1a2e" }}>
      <h3 style={{ margin: "0 0 8px", color: "#eee", fontSize: 14 }}>Live Event Log</h3>
      <div
        ref={containerRef}
        style={{
          height: 300,
          overflowY: "auto",
          fontFamily: "monospace",
          fontSize: 11,
          lineHeight: 1.6,
          background: "#0d0d1a",
          padding: 8,
          borderRadius: 4,
        }}
      >
        {displayLogs.length === 0 && (
          <div style={{ color: "#666" }}>Waiting for events...</div>
        )}
        {displayLogs.map((entry, idx) => {
          const color = getEventColor(entry.event);
          const time = formatTime(entry.timestamp);
          const clientId = entry.data?.client_id || "";
          const task = entry.data?.task || "";
          const detail = formatDetail(entry);

          return (
            <div key={idx} style={{ color }}>
              [{time}] {entry.event}
              {clientId && ` | ${clientId}`}
              {task && ` | task=${task}`}
              {detail && ` | ${detail}`}
            </div>
          );
        })}
      </div>
    </div>
  );
}
