// dashboard/src/components/ConvergenceCurve.jsx — Global loss vs. round chart
import React from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

export default function ConvergenceCurve({ lossHistory, selectedTask }) {
  const data = (lossHistory || []).map((loss, idx) => ({
    round: idx + 1,
    loss: typeof loss === "number" ? loss : 0,
  }));

  const taskLabel = selectedTask === "femnist" ? "FEMNIST (Image)" : "Shakespeare (Text)";

  return (
    <div style={{ border: "1px solid #444", borderRadius: 8, padding: 12, background: "#1a1a2e" }}>
      <h3 style={{ margin: "0 0 8px", color: "#eee", fontSize: 14 }}>
        Convergence: {taskLabel}
      </h3>
      {data.length === 0 ? (
        <div style={{ color: "#666", height: 250, display: "flex", alignItems: "center", justifyContent: "center" }}>
          Waiting for round completions...
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={250}>
          <LineChart data={data} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#333" />
            <XAxis
              dataKey="round"
              stroke="#888"
              label={{ value: "Round", position: "insideBottom", offset: -5, fill: "#888" }}
            />
            <YAxis
              stroke="#888"
              label={{ value: "Loss", angle: -90, position: "insideLeft", fill: "#888" }}
            />
            <Tooltip
              contentStyle={{ background: "#1a1a2e", border: "1px solid #444", color: "#eee" }}
            />
            <Legend />
            <Line
              type="monotone"
              dataKey="loss"
              stroke="#3498db"
              strokeWidth={2}
              dot={{ r: 3 }}
              name="Global Loss"
              activeDot={{ r: 5 }}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
