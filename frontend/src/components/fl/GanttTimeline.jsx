import { useRef, useEffect, useCallback } from "react";
import { motion } from "framer-motion";

const PALETTE = {
  dark: {
    bg: "#0a0f1e",
    grid: "#1e2d47",
    text: "#64748b",
    honest: "#06b6d4",
    slow: "#f59e0b",
    byz: "#f43f5e",
    agg: "#f59e0b",
  },
  light: {
    bg: "#f8fafc",
    grid: "#e2e8f0",
    text: "#94a3b8",
    honest: "#0891b2",
    slow: "#d97706",
    byz: "#e11d48",
    agg: "#d97706",
  },
};

function getColors() {
  const isDark = document.documentElement.classList.contains("dark");
  return isDark ? PALETTE.dark : PALETTE.light;
}

function nodeColor(node, colors) {
  if (node.isByzantine) return colors.byz;
  if (node.isSlow) return colors.slow;
  return colors.honest;
}

export default function GanttTimeline({
  ganttBlocks,
  aggTriggerTimes,
  nodes,
  viewMode,
}) {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const colors = getColors();

    const NOW = Date.now() / 1000;
    const WINDOW = 60;
    const LEFT_PAD = 72;
    const BOT_PAD = 28;
    const TOP_PAD = 16;
    const numNodes = nodes.length || 10;
    const chartW = canvas.width - LEFT_PAD - 10;
    const rowH = (canvas.height - TOP_PAD - BOT_PAD) / numNodes;

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = colors.bg;
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Alternating row stripes
    for (let i = 0; i < numNodes; i++) {
      if (i % 2 === 0) {
        ctx.fillStyle = colors.grid + "22";
        ctx.fillRect(LEFT_PAD, TOP_PAD + i * rowH, chartW, rowH);
      }
    }

    // Vertical grid lines every 10s
    ctx.strokeStyle = colors.grid;
    ctx.lineWidth = 0.5;
    ctx.font = "10px monospace";
    ctx.fillStyle = colors.text;
    for (let t = 0; t <= WINDOW; t += 10) {
      const x = LEFT_PAD + (t / WINDOW) * chartW;
      ctx.beginPath();
      ctx.moveTo(x, TOP_PAD);
      ctx.lineTo(x, canvas.height - BOT_PAD);
      ctx.stroke();
      ctx.fillText(`-${WINDOW - t}s`, x - 10, canvas.height - BOT_PAD + 14);
    }

    // Node labels on left
    ctx.font = "10px monospace";
    nodes.forEach((node, i) => {
      const y = TOP_PAD + i * rowH + rowH / 2 + 3;
      ctx.fillStyle = nodeColor(node, colors);
      ctx.fillText(node.displayId, 4, y);
    });

    // Gantt blocks
    const nodeIndexMap = {};
    nodes.forEach((n, i) => {
      nodeIndexMap[n.nodeId] = i;
    });

    (ganttBlocks || []).forEach((block) => {
      const rowIdx = nodeIndexMap[block.nodeId];
      if (rowIdx === undefined) return;

      const x0 = LEFT_PAD + ((block.startSec - (NOW - WINDOW)) / WINDOW) * chartW;
      const x1 = LEFT_PAD + ((block.endSec - (NOW - WINDOW)) / WINDOW) * chartW;
      if (x1 < LEFT_PAD || x0 > LEFT_PAD + chartW) return;

      const clampedX0 = Math.max(x0, LEFT_PAD);
      const clampedX1 = Math.min(x1, LEFT_PAD + chartW);
      const y = TOP_PAD + rowIdx * rowH + 2;
      const h = rowH - 4;

      const color = block.isByzantine
        ? colors.byz
        : block.isSlow
          ? colors.slow
          : colors.honest;

      ctx.fillStyle = color + "40";
      ctx.fillRect(clampedX0, y, clampedX1 - clampedX0, h);

      ctx.fillStyle = color;
      ctx.fillRect(clampedX0, y, 2, h);
      ctx.fillRect(clampedX1 - 2, y, 2, h);
    });

    // Aggregation trigger lines
    (aggTriggerTimes || []).forEach((t) => {
      const x = LEFT_PAD + ((t - (NOW - WINDOW)) / WINDOW) * chartW;
      if (x < LEFT_PAD || x > LEFT_PAD + chartW) return;

      ctx.save();
      ctx.shadowColor = colors.agg;
      ctx.shadowBlur = 6;
      ctx.strokeStyle = colors.agg;
      ctx.lineWidth = 1.5;
      ctx.setLineDash([4, 3]);
      ctx.beginPath();
      ctx.moveTo(x, TOP_PAD);
      ctx.lineTo(x, canvas.height - BOT_PAD);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.restore();

      ctx.fillStyle = colors.agg;
      ctx.font = "10px sans-serif";
      ctx.fillText("▼", x - 4, TOP_PAD - 2);
    });

    // Axes
    ctx.strokeStyle = colors.grid;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(LEFT_PAD, TOP_PAD);
    ctx.lineTo(LEFT_PAD, canvas.height - BOT_PAD);
    ctx.lineTo(LEFT_PAD + chartW, canvas.height - BOT_PAD);
    ctx.stroke();
  }, [ganttBlocks, aggTriggerTimes, nodes]);

  // Resize canvas to container
  const resizeCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;
    const dpr = window.devicePixelRatio || 1;
    const rect = container.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    canvas.style.width = rect.width + "px";
    canvas.style.height = rect.height + "px";
    const ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);
    // Reset scale for draw — we draw in CSS pixels
    canvas.width = rect.width;
    canvas.height = rect.height;
    draw();
  }, [draw]);

  useEffect(() => {
    resizeCanvas();
    const container = containerRef.current;
    if (!container) return;
    const ro = new ResizeObserver(resizeCanvas);
    ro.observe(container);
    return () => ro.disconnect();
  }, [resizeCanvas]);

  // Redraw whenever data changes
  useEffect(() => {
    draw();
  }, [draw]);

  // Redraw on theme changes
  useEffect(() => {
    const observer = new MutationObserver(draw);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });
    return () => observer.disconnect();
  }, [draw]);

  const aggCount = (aggTriggerTimes || []).length;

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="flex h-full w-full flex-col"
    >
      <div ref={containerRef} className="flex-1">
        <canvas ref={canvasRef} className="h-full w-full" />
      </div>

      {viewMode === "detailed" && (
        <div className="mt-2 flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-[#06b6d4]" />
            Honest
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-[#f59e0b]" />
            Slow
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-[#f43f5e]" />
            Byzantine
          </span>
          <span className="mono-data ml-auto">
            Aggregations: {aggCount}
          </span>
        </div>
      )}
    </motion.div>
  );
}
