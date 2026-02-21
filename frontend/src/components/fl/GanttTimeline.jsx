import { useRef, useEffect, useCallback, memo } from "react";
import { motion } from "framer-motion";

const PALETTE = {
  dark: {
    bg: "transparent",
    grid: "rgba(255,255,255,0.06)",
    text: "rgba(148,163,184,0.6)",
    honest: "#06b6d4",
    slow: "#f59e0b",
    byz: "#f43f5e",
    agg: "#06b6d4",
  },
  light: {
    bg: "transparent",
    grid: "rgba(0,0,0,0.06)",
    text: "rgba(100,116,139,0.5)",
    honest: "#0891b2",
    slow: "#d97706",
    byz: "#e11d48",
    agg: "#0891b2",
  },
};

const getColors = () => {
  const isDark = document.documentElement.classList.contains("dark");
  return isDark ? PALETTE.dark : PALETTE.light;
};

const nodeColor = (node, colors) => {
  if (node.isByzantine) return colors.byz;
  if (node.isSlow) return colors.slow;
  return colors.honest;
};

const GanttTimeline = memo(({
  ganttBlocks,
  aggTriggerTimes,
  nodes,
  viewMode,
}) => {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);
  const requestRef = useRef(null);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const colors = getColors();

    const NOW = Date.now() / 1000;
    const WINDOW = 60;
    const LEFT_PAD = 80;
    const BOT_PAD = 32;
    const TOP_PAD = 16;
    const numNodes = nodes.length || 10;
    const chartW = canvas.width - LEFT_PAD - 12;
    const rowH = (canvas.height - TOP_PAD - BOT_PAD) / numNodes;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Row backgrounds
    for (let i = 0; i < numNodes; i++) {
      if (i % 2 === 0) {
        ctx.fillStyle = colors.grid;
        ctx.fillRect(LEFT_PAD, TOP_PAD + i * rowH, chartW, rowH);
      }
    }

    // Vertical grid lines
    ctx.strokeStyle = colors.grid;
    ctx.lineWidth = 1;
    ctx.font = "bold 9px var(--font-mono)";
    ctx.fillStyle = colors.text;
    for (let t = 0; t <= WINDOW; t += 10) {
      const x = LEFT_PAD + (t / WINDOW) * chartW;
      ctx.beginPath();
      ctx.moveTo(x, TOP_PAD);
      ctx.lineTo(x, canvas.height - BOT_PAD);
      ctx.stroke();
      if (t < WINDOW) {
        ctx.fillText(`-${WINDOW - t}S`, x - 10, canvas.height - BOT_PAD + 16);
      } else {
        ctx.fillText("NOW", x - 10, canvas.height - BOT_PAD + 16);
      }
    }

    // Node labels
    ctx.font = "bold 10px var(--font-mono)";
    nodes.forEach((node, i) => {
      const y = TOP_PAD + i * rowH + rowH / 2 + 4;
      ctx.fillStyle = nodeColor(node, colors);
      ctx.fillText(node.displayId, 12, y);
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
      const y = TOP_PAD + rowIdx * rowH + 3;
      const h = Math.max(rowH - 6, 2);

      const color = block.isByzantine
        ? colors.byz
        : block.isSlow
          ? colors.slow
          : colors.honest;

      ctx.fillStyle = color + "25";
      ctx.fillRect(clampedX0, y, clampedX1 - clampedX0, h);

      ctx.fillStyle = color;
      ctx.fillRect(clampedX0, y, 2, h);
    });

    // Aggregation trigger lines
    (aggTriggerTimes || []).forEach((t) => {
      const x = LEFT_PAD + ((t - (NOW - WINDOW)) / WINDOW) * chartW;
      if (x < LEFT_PAD || x > LEFT_PAD + chartW) return;

      ctx.save();
      ctx.strokeStyle = colors.agg;
      ctx.lineWidth = 1;
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(x, TOP_PAD);
      ctx.lineTo(x, canvas.height - BOT_PAD);
      ctx.stroke();
      ctx.restore();

      ctx.fillStyle = colors.agg;
      ctx.fillText("▼", x - 4, TOP_PAD - 4);
    });

    // Axis line
    ctx.strokeStyle = colors.grid;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(LEFT_PAD, TOP_PAD);
    ctx.lineTo(LEFT_PAD, canvas.height - BOT_PAD);
    ctx.lineTo(LEFT_PAD + chartW, canvas.height - BOT_PAD);
    ctx.stroke();
  }, [ganttBlocks, aggTriggerTimes, nodes]);

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

  useEffect(() => {
    const scheduleDraw = () => {
      draw();
      requestRef.current = requestAnimationFrame(scheduleDraw);
    };
    requestRef.current = requestAnimationFrame(scheduleDraw);
    return () => cancelAnimationFrame(requestRef.current);
  }, [draw]);

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
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="flex h-full w-full flex-col min-w-0"
    >
      <div ref={containerRef} className="flex-1 card-base bg-card/10 backdrop-blur-[2px] overflow-hidden">
        <canvas ref={canvasRef} className="h-full w-full" />
      </div>

      {viewMode === "detailed" && (
        <div className="mt-3 flex flex-wrap items-center gap-4 text-[10px] font-mono tracking-wider uppercase opacity-60">
          <div className="flex items-center gap-1.5">
            <div className="h-2 w-2 rounded-full bg-cyan-500 shadow-[0_0_8px_rgba(6,182,212,0.4)]" />
            <span>Honest Node</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="h-2 w-2 rounded-full bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.4)]" />
            <span>Late Latency</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="h-2 w-2 rounded-full bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.4)]" />
            <span>Distortion</span>
          </div>
          <div className="ml-auto text-primary font-bold">
            Buffered Agg: {aggCount}
          </div>
        </div>
      )}
    </motion.div>
  );
});

export default GanttTimeline;
