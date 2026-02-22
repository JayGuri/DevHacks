import React, {
  useRef,
  useState,
  useEffect,
  useMemo,
  useCallback,
} from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls, Html, Line, Billboard, Text } from "@react-three/drei";
import * as THREE from "three";
import { motion, AnimatePresence } from "framer-motion";
import useFL from "@/hooks/useFL";
import { useStore } from "@/lib/store";

/* ═══════════════════════════════════════════════════════════════
   CONFIG
   ═══════════════════════════════════════════════════════════════ */
const NODE_CONFIG = {
  ACTIVE: {
    color: "#10b981",
    emissive: "#064e3b",
    glowColor: "#34d399",
    label: "Active",
    pulseSpeed: 1.2,
  },
  SLOW: {
    color: "#f59e0b",
    emissive: "#451a03",
    glowColor: "#fbbf24",
    label: "Slow/Async",
    pulseSpeed: 0.6,
  },
  BYZANTINE: {
    color: "#f43f5e",
    emissive: "#4c0519",
    glowColor: "#fb7185",
    label: "Flagged",
    pulseSpeed: 2.5,
  },
  BLOCKED: {
    color: "#475569",
    emissive: "#0f172a",
    glowColor: "#64748b",
    label: "Blocked",
    pulseSpeed: 0,
  },
  JOINING: {
    color: "#818cf8",
    emissive: "#1e1b4b",
    glowColor: "#a5b4fc",
    label: "Joining",
    pulseSpeed: 1.8,
  },
  SERVER: {
    color: "#06b6d4",
    emissive: "#083344",
    glowColor: "#22d3ee",
    label: "Server",
    pulseSpeed: 0.8,
  },
};

const ORBIT_RADIUS = 4.5;
const SERVER_SIZE = 0.55;
const CLIENT_SIZE = 0.28;

/* ═══════════════════════════════════════════════════════════════
   POSITION CALCULATOR  (Fibonacci sphere layout)
   ═══════════════════════════════════════════════════════════════ */
function computeNodePositions(nodes) {
  const phi = Math.PI * (3 - Math.sqrt(5));
  const positions = new Map();
  const n = nodes.length;
  nodes.forEach((node, i) => {
    const y = 1 - (i / (n - 1)) * 2 || 0;
    const radius = Math.sqrt(1 - y * y);
    const theta = phi * i;
    const x = Math.cos(theta) * radius * ORBIT_RADIUS;
    const z = Math.sin(theta) * radius * ORBIT_RADIUS;
    const yPos = y * (ORBIT_RADIUS * 0.7);
    positions.set(node.nodeId, { position: [x, yPos, z], node });
  });
  return positions;
}

/* ═══════════════════════════════════════════════════════════════
   3D COMPONENTS  (inside <Canvas>)
   ═══════════════════════════════════════════════════════════════ */

/* ─── AnimatedEdge ─────────────────────────────────────────── */
function AnimatedEdge({ start, end, status, active, nodeId, isHovered }) {
  const packetRef = useRef(null);
  const progressRef = useRef(Math.random());

  const config = NODE_CONFIG[status] || NODE_CONFIG.ACTIVE;
  const isBlocked = status === "BLOCKED";
  const isByzantine = status === "BYZANTINE";
  const isSlow = status === "SLOW";

  const curve = useMemo(() => {
    const hash = nodeId
      .split("")
      .reduce((acc, char) => acc + char.charCodeAt(0), 0);
    const off = (hash % 10) / 10 - 0.5;
    const mid = [
      (start[0] + end[0]) / 2 + off,
      (start[1] + end[1]) / 2 + 0.5,
      (start[2] + end[2]) / 2 + off,
    ];
    return new THREE.CatmullRomCurve3([
      new THREE.Vector3(...start),
      new THREE.Vector3(...mid),
      new THREE.Vector3(...end),
    ]);
  }, [start, end, nodeId]);

  const points = useMemo(() => curve.getPoints(50), [curve]);

  const lineOpacity =
    isHovered ? 1.0
    : isByzantine ? 0.7
    : isSlow ? 0.35
    : isBlocked ? 0.1
    : 0.6;

  const lineWidth =
    isHovered ? 2.5
    : isByzantine ? 1.5
    : isSlow ? 0.8
    : isBlocked ? 0.5
    : 1;

  const packetSize = isByzantine ? 0.09 : 0.06;

  useFrame((state, delta) => {
    if (active && !isBlocked && packetRef.current) {
      const speed = isByzantine ? 0.55 : isSlow ? 0.15 : 0.4;
      progressRef.current = (progressRef.current + delta * speed) % 1.0;
      const pt = curve.getPoint(progressRef.current);
      packetRef.current.position.set(pt.x, pt.y, pt.z);
      const s =
        packetSize * (1 + Math.sin(state.clock.elapsedTime * 10) * 0.2);
      packetRef.current.scale.setScalar(s);
    }
  });

  return (
    <group>
      <Line
        points={points}
        color={config.glowColor}
        lineWidth={lineWidth}
        transparent
        opacity={lineOpacity}
        depthWrite={false}
      />
      {active && !isBlocked && (
        <mesh ref={packetRef}>
          <sphereGeometry args={[1, 8, 8]} />
          <meshBasicMaterial
            color={config.glowColor}
            transparent
            opacity={0.9}
          />
        </mesh>
      )}
    </group>
  );
}

/* ─── ServerNode ───────────────────────────────────────────── */
function ServerNode({ position, onHover, onUnhover, hovered, onClick }) {
  const meshRef = useRef();
  const ringRef = useRef();
  const glowRef = useRef();

  useFrame((state, delta) => {
    if (!meshRef.current || !ringRef.current) return;
    meshRef.current.rotation.y += delta * 0.4;
    meshRef.current.rotation.x += delta * 0.15;
    ringRef.current.rotation.z += delta * 0.6;
    ringRef.current.rotation.x = Math.PI / 2.5;
    const breath = 1 + Math.sin(state.clock.elapsedTime * 1.2) * 0.04;
    meshRef.current.scale.setScalar(breath);
    if (glowRef.current?.material) {
      glowRef.current.material.opacity =
        0.25 + Math.sin(state.clock.elapsedTime * 2) * 0.15;
    }
  });

  return (
    <group position={position}>
      <mesh ref={meshRef} onPointerEnter={onHover} onPointerLeave={onUnhover} onClick={onClick}>
        <sphereGeometry args={[SERVER_SIZE, 32, 32]} />
        <meshStandardMaterial
          color={NODE_CONFIG.SERVER.color}
          emissive={NODE_CONFIG.SERVER.emissive}
          emissiveIntensity={hovered ? 2.5 : 1.2}
          metalness={0.9}
          roughness={0.1}
        />
      </mesh>

      <mesh ref={glowRef}>
        <sphereGeometry args={[SERVER_SIZE * 1.6, 24, 24]} />
        <meshBasicMaterial
          color={NODE_CONFIG.SERVER.glowColor}
          transparent
          opacity={0.08}
          depthWrite={false}
        />
      </mesh>

      <mesh ref={ringRef}>
        <torusGeometry args={[SERVER_SIZE * 1.8, 0.015, 8, 64]} />
        <meshBasicMaterial
          color={NODE_CONFIG.SERVER.glowColor}
          transparent
          opacity={0.5}
        />
      </mesh>

      <mesh rotation={[Math.PI / 3, 0, Math.PI / 4]}>
        <torusGeometry args={[SERVER_SIZE * 2.2, 0.01, 8, 64]} />
        <meshBasicMaterial
          color={NODE_CONFIG.SERVER.color}
          transparent
          opacity={0.2}
        />
      </mesh>

      <Billboard follow lockX={false} lockY={false} lockZ={false}>
        <Text
          position={[0, SERVER_SIZE + 0.4, 0]}
          fontSize={0.18}
          color={NODE_CONFIG.SERVER.glowColor}
          anchorX="center"
          anchorY="middle"
        >
          SERVER
        </Text>
        <Text
          position={[0, SERVER_SIZE + 0.22, 0]}
          fontSize={0.1}
          color="#94a3b8"
          anchorX="center"
          anchorY="middle"
        >
          GLOBAL MODEL
        </Text>
      </Billboard>
    </group>
  );
}

/* ─── ClientNode ───────────────────────────────────────────── */
function ClientNode({ node, position, onHover, onUnhover, hovered, onClick }) {
  const meshRef = useRef();
  const glowRef = useRef();
  const config = NODE_CONFIG[node.status] || NODE_CONFIG.ACTIVE;

  useFrame((state) => {
    if (!meshRef.current) return;
    if (config.pulseSpeed > 0) {
      const pulse =
        1 + Math.sin(state.clock.elapsedTime * config.pulseSpeed) * 0.08;
      meshRef.current.scale.setScalar(pulse);
    }
    if (glowRef.current?.material) {
      glowRef.current.material.opacity =
        0.15 +
        Math.sin(state.clock.elapsedTime * config.pulseSpeed * 0.7) * 0.1;
    }
    if (node.status === "BYZANTINE") {
      meshRef.current.position.x =
        Math.sin(state.clock.elapsedTime * 3.7) * 0.04;
      meshRef.current.position.y =
        Math.cos(state.clock.elapsedTime * 2.9) * 0.04;
    } else if (node.status === "SLOW") {
      meshRef.current.position.y =
        Math.sin(state.clock.elapsedTime * 0.5) * 0.06;
    }
  });

  return (
    <group position={position}>
      <mesh ref={meshRef} onPointerEnter={onHover} onPointerLeave={onUnhover} onClick={onClick}>
        <sphereGeometry args={[CLIENT_SIZE, 24, 24]} />
        <meshStandardMaterial
          color={config.color}
          emissive={config.emissive}
          emissiveIntensity={
            hovered ? 1.0 : node.status === "BYZANTINE" ? 0.6 : 0.3
          }
          metalness={node.status === "BLOCKED" ? 0.1 : 0.5}
          roughness={node.status === "BLOCKED" ? 0.9 : 0.3}
          transparent={node.status === "BLOCKED"}
          opacity={node.status === "BLOCKED" ? 0.4 : 1.0}
        />
      </mesh>

      <mesh ref={glowRef}>
        <sphereGeometry args={[CLIENT_SIZE * 1.8, 16, 16]} />
        <meshBasicMaterial
          color={config.glowColor}
          transparent
          opacity={0.12}
          depthWrite={false}
        />
      </mesh>

      <mesh>
        <sphereGeometry args={[CLIENT_SIZE * 0.45, 12, 12]} />
        <meshBasicMaterial
          color={config.glowColor}
          transparent
          opacity={0.6}
        />
      </mesh>

      {node.status === "BYZANTINE" && (
        <mesh rotation={[Math.PI / 4, 0, 0]}>
          <torusGeometry args={[CLIENT_SIZE * 1.5, 0.02, 6, 32]} />
          <meshBasicMaterial color="#f43f5e" transparent opacity={0.7} />
        </mesh>
      )}

      <Billboard>
        <Text
          position={[0, CLIENT_SIZE + 0.22, 0]}
          fontSize={0.1}
          color={config.glowColor}
          anchorX="center"
          anchorY="middle"
        >
          {node.displayId}
        </Text>
        <Text
          position={[0, CLIENT_SIZE + 0.1, 0]}
          fontSize={0.08}
          color="#64748b"
          anchorX="center"
          anchorY="middle"
        >
          {config.label}
        </Text>
      </Billboard>
    </group>
  );
}

/* ═══════════════════════════════════════════════════════════════
   TOOLTIP COMPONENTS  (Html overlay inside Canvas)
   ─  Always dark-themed since they float over the 3D scene
   ═══════════════════════════════════════════════════════════════ */
function ServerTooltipContent({ fl }) {
  const method =
    fl.project?.config?.aggregationMethod?.replace(/_/g, " ") ||
    "Federated Averaging";
  const activeNodes = fl.nodes.filter(
    (n) => n.status !== "BLOCKED" && n.status !== "BYZANTINE",
  ).length;

  return (
    <div className="flex flex-col gap-2">
      <div className="font-bold text-cyan-400 text-sm">⬡ CENTRAL SERVER</div>
      <div className="h-px bg-slate-700 w-full" />
      <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs">
        <span className="text-slate-400">Role:</span>
        <span className="text-slate-200">Global Model Host</span>
        <span className="text-slate-400">Status:</span>
        <span className="text-emerald-400">● Online</span>
        <span className="text-slate-400">Aggregator:</span>
        <span className="text-cyan-200 capitalize">{method}</span>
        <span className="text-slate-400">Round:</span>
        <span className="text-slate-200">{fl.currentRound}</span>
        <span className="text-slate-400">Active Nodes:</span>
        <span className="text-slate-200">{activeNodes}</span>
      </div>
    </div>
  );
}

function NodeTooltipContent({
  node,
  isAdmin,
  onBlock,
  onUnblock,
  setHoveredNodeId,
}) {
  const config = NODE_CONFIG[node.status] || NODE_CONFIG.ACTIVE;

  return (
    <div className="flex flex-col gap-2" style={{ pointerEvents: "auto" }}>
      <div
        className="font-bold flex items-center gap-2 text-sm"
        style={{ color: config.glowColor }}
      >
        <span>●</span>
        <span>{node.displayId}</span>
        <span
          className="text-[10px] px-2 py-0.5 rounded-full"
          style={{
            background: `${config.glowColor}20`,
            border: `1px solid ${config.glowColor}40`,
          }}
        >
          {config.label}
        </span>
      </div>
      <div className="h-px bg-slate-700 w-full" />
      <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs">
        <span className="text-slate-400">Trust Score:</span>
        <div className="flex items-center gap-2">
          <div className="h-1.5 w-20 bg-slate-800 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full"
              style={{
                width: `${node.trust * 100}%`,
                background:
                  node.trust > 0.7 ? "#10b981"
                  : node.trust > 0.4 ? "#f59e0b"
                  : "#f43f5e",
              }}
            />
          </div>
          <span className="text-slate-200">
            {(node.trust * 100).toFixed(1)}%
          </span>
        </div>
        <span className="text-slate-400">Cos. Distance:</span>
        <span
          className={
            node.cosineDistance > 0.45 ? "text-rose-400" : "text-slate-200"
          }
        >
          {node.cosineDistance?.toFixed(3) || "0.000"}
        </span>
        <span className="text-slate-400">Staleness:</span>
        <span className="text-slate-200">{node.staleness || 0}r</span>
        <span className="text-slate-400">Rounds Done:</span>
        <span className="text-slate-200">{node.roundsContributed || 0}</span>
      </div>

      {node.status === "BYZANTINE" && (
        <div className="mt-1 p-2 bg-rose-950 border border-rose-900 rounded text-[11px] text-rose-300">
          ⚠ FLAGGED — Update excluded from aggregation
        </div>
      )}
      {node.status === "BLOCKED" && (
        <div className="mt-1 p-2 bg-slate-900 border border-slate-700 rounded text-[11px] text-slate-400">
          🚫 BLOCKED — Manually excluded by admin
        </div>
      )}

      {isAdmin && (
        <div className="mt-2 pt-2 border-t border-slate-700 flex justify-end">
          {node.status === "BLOCKED" ? (
            <button
              className="px-3 py-1 bg-emerald-600/20 hover:bg-emerald-600/40 text-emerald-400 border border-emerald-600/50 rounded-full text-xs transition-colors cursor-pointer"
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                onUnblock(node.nodeId);
                setHoveredNodeId(null);
              }}
            >
              Unblock Node
            </button>
          ) : (
            <button
              className="px-3 py-1 bg-rose-600/20 hover:bg-rose-600/40 text-rose-400 border border-rose-600/50 rounded-full text-xs transition-colors cursor-pointer"
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                onBlock(node.nodeId);
                setHoveredNodeId(null);
              }}
            >
              Block Node
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function NodeTooltip({
  node,
  position,
  visible,
  isServer,
  fl,
  isAdmin,
  onBlock,
  onUnblock,
  setHoveredNodeId,
}) {
  return (
    <Html
      position={position}
      center
      distanceFactor={8}
      occlude={false}
      style={{ pointerEvents: "none", userSelect: "none", zIndex: 100 }}
    >
      <AnimatePresence>
        {visible && (
          <motion.div
            initial={{ opacity: 0, scale: 0.85, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.85, y: 8 }}
            transition={{ duration: 0.18 }}
            className="rounded-[10px] shadow-2xl"
            style={{
              background: "hsl(222, 47%, 9%)",
              border: "1px solid hsl(222, 30%, 18%)",
              padding: "12px 16px",
              minWidth: "220px",
              maxWidth: "280px",
              fontFamily: "'JetBrains Mono', monospace",
              color: "#c8d8f0",
              pointerEvents: isAdmin && !isServer ? "auto" : "none",
            }}
          >
            {isServer ? (
              <ServerTooltipContent fl={fl} />
            ) : (
              <NodeTooltipContent
                node={node}
                isAdmin={isAdmin}
                onBlock={onBlock}
                onUnblock={onUnblock}
                setHoveredNodeId={setHoveredNodeId}
              />
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </Html>
  );
}

/* ═══════════════════════════════════════════════════════════════
   HUD OVERLAYS  (HTML on top of Canvas — theme-aware)
   ═══════════════════════════════════════════════════════════════ */

function LiveLog({ events }) {
  return (
    <div
      className={[
        // Hidden on very small phones, visible from 480px+
        "hidden min-[480px]:flex",
        "absolute top-2 right-2 sm:top-4 sm:right-4",
        "w-48 sm:w-56 md:w-72 max-h-36 sm:max-h-48 md:max-h-72",
        "overflow-hidden rounded-lg backdrop-blur-md p-2 sm:p-3",
        "z-10 pointer-events-none flex-col",
        "bg-white/80 border border-slate-200",
        "dark:bg-[#050810]/85 dark:border-white/10",
      ].join(" ")}
    >
      <div className="text-cyan-600 dark:text-cyan-400 font-mono text-[10px] sm:text-xs font-bold mb-1 sm:mb-2 tracking-wider">
        LIVE LOG
      </div>
      <div className="flex-1 overflow-y-auto flex flex-col gap-0.5 pr-1">
        <AnimatePresence initial={false}>
          {events.map((ev) => (
            <motion.div
              key={ev.id}
              initial={{ opacity: 0, y: -12, height: 0 }}
              animate={{ opacity: 1, y: 0, height: "auto" }}
              transition={{ duration: 0.2 }}
              className="text-[8px] sm:text-[9px] md:text-[10px] font-mono whitespace-nowrap overflow-hidden text-ellipsis leading-tight"
              style={{
                color:
                  ev.type === "join" ? "#818cf8"
                  : ev.type === "byzantine" ? "#f43f5e"
                  : ev.type === "blocked" ? "#f59e0b"
                  : ev.type === "round" ? "#10b981"
                  : ev.type === "aggregation" ? "#06b6d4"
                  : "#64748b",
              }}
            >
              <span className="opacity-70 mr-1">[{ev.timestamp}]</span>
              {ev.message}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}

function NetworkLegend() {
  return (
    <div
      className={[
        // Hidden on very small phones, visible from 480px+
        "hidden min-[480px]:block",
        "absolute bottom-2 left-2 sm:bottom-4 sm:left-4",
        "p-1.5 sm:p-2 md:p-3 rounded-lg backdrop-blur-md z-10 pointer-events-none",
        "bg-white/80 border border-slate-200",
        "dark:bg-[#050810]/85 dark:border-white/10",
      ].join(" ")}
    >
      <div className="grid grid-cols-2 gap-x-2 sm:gap-x-4 gap-y-0.5 sm:gap-y-1.5 mb-1 sm:mb-2">
        {[
          { color: "text-emerald-500", label: "Active" },
          { color: "text-amber-500", label: "Slow" },
          { color: "text-rose-500", label: "Flagged" },
          { color: "text-slate-500 dark:text-slate-400", label: "Blocked" },
          { color: "text-indigo-500 dark:text-indigo-400", label: "Joining" },
          { color: "text-cyan-500 dark:text-cyan-400", label: "Server", icon: "⬡" },
        ].map(({ color, label, icon }) => (
          <div
            key={label}
            className="flex items-center gap-1 text-[9px] sm:text-[10px] md:text-xs text-slate-600 dark:text-slate-300 font-mono"
          >
            <span className={color}>{icon || "●"}</span> {label}
          </div>
        ))}
      </div>
      <div className="text-[7px] sm:text-[8px] md:text-[9px] text-slate-400 dark:text-slate-500 font-mono pt-1 border-t border-slate-200 dark:border-slate-700/50">
        Drag to orbit · Scroll to zoom
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   3D SCENE  (lives inside <Canvas>)
   ─  Always dark – the 3D space scene is inherently dark-themed
   ═══════════════════════════════════════════════════════════════ */
function NetworkScene({
  fl,
  isRunning,
  onBlockNode,
  onUnblockNode,
  isAdmin,
  autoRotate,
}) {
  const [hoveredNodeId, setHoveredNodeId] = useState(null);
  const [hoveredServer, setHoveredServer] = useState(false);
  // Track whether current selection was from a tap (persists until dismissed)
  const [tappedNodeId, setTappedNodeId] = useState(null);
  const [tappedServer, setTappedServer] = useState(false);
  const nodes = fl.nodes;

  // Combined: a node is "active" if hovered OR tapped
  const activeNodeId = hoveredNodeId || tappedNodeId;
  const activeServer = hoveredServer || tappedServer;

  const nodePositions = useMemo(() => computeNodePositions(nodes), [nodes]);

  const starsRef = useRef();
  const starPositions = useMemo(() => {
    const pos = new Float32Array(400 * 3);
    for (let i = 0; i < 400; i++) {
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      const r = 25 + Math.random() * 15;
      pos[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      pos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
      pos[i * 3 + 2] = r * Math.cos(phi);
    }
    return pos;
  }, []);

  useFrame((state) => {
    if (starsRef.current) {
      starsRef.current.rotation.y = state.clock.elapsedTime * 0.02;
      starsRef.current.rotation.x = state.clock.elapsedTime * 0.01;
    }
  });

  return (
    <>
      {/* Lighting */}
      <ambientLight intensity={0.6} />
      <pointLight
        position={[0, 0, 0]}
        intensity={2}
        color="#06b6d4"
        distance={15}
        decay={2}
      />
      <directionalLight position={[10, 10, 5]} intensity={1.2} />
      <directionalLight
        position={[-8, -4, -8]}
        intensity={0.4}
        color="#818cf8"
      />

      {/* Background — always dark for contrast */}
      <color attach="background" args={["#0a0f1a"]} />

      {/* Stars */}
      <points ref={starsRef}>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            args={[starPositions, 3]}
          />
        </bufferGeometry>
        <pointsMaterial
          size={0.06}
          color="#94a3b8"
          transparent
          opacity={0.4}
          sizeAttenuation
        />
      </points>

      {/* Grid floor */}
      <gridHelper
        args={[24, 24, "#0f1a2e", "#0a1220"]}
        position={[0, -4, 0]}
      />
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -3.9, 0]}>
        <ringGeometry args={[4.4, 4.6, 64]} />
        <meshBasicMaterial color="#06b6d4" transparent opacity={0.08} />
      </mesh>

      {/* Background click to dismiss tapped tooltip */}
      <mesh
        position={[0, 0, -20]}
        onClick={(e) => {
          // Only dismiss if clicking the background mesh itself
          e.stopPropagation();
          setTappedNodeId(null);
          setTappedServer(false);
        }}
      >
        <planeGeometry args={[100, 100]} />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>

      {/* Controls */}
      <OrbitControls
        enableDamping
        dampingFactor={0.05}
        minDistance={4}
        maxDistance={14}
        autoRotate={autoRotate && !activeNodeId && !activeServer}
        autoRotateSpeed={0.4}
      />

      {/* Edges */}
      {nodes.map((node) => {
        const posData = nodePositions.get(node.nodeId);
        if (!posData) return null;
        return (
          <AnimatedEdge
            key={`edge-${node.nodeId}`}
            nodeId={node.nodeId}
            start={[0, 0, 0]}
            end={posData.position}
            status={node.status}
            active={isRunning}
            isHovered={hoveredNodeId === node.nodeId}
          />
        );
      })}

      {/* Server */}
      <ServerNode
        position={[0, 0, 0]}
        onHover={() => setHoveredServer(true)}
        onUnhover={() => setHoveredServer(false)}
        hovered={activeServer}
        onClick={(e) => {
          e.stopPropagation();
          setTappedServer((prev) => !prev);
          setTappedNodeId(null);
        }}
      />
      {activeServer && (
        <NodeTooltip
          position={[0, SERVER_SIZE + 0.5, 0]}
          visible
          isServer
          fl={fl}
        />
      )}

      {/* Client nodes */}
      {nodes.map((node) => {
        const posData = nodePositions.get(node.nodeId);
        if (!posData) return null;
        const isActive = activeNodeId === node.nodeId;
        return (
          <React.Fragment key={`node-${node.nodeId}`}>
            <ClientNode
              node={node}
              position={posData.position}
              onHover={() => setHoveredNodeId(node.nodeId)}
              onUnhover={() => setHoveredNodeId(null)}
              hovered={isActive}
              onClick={(e) => {
                e.stopPropagation();
                setTappedNodeId((prev) =>
                  prev === node.nodeId ? null : node.nodeId,
                );
                setTappedServer(false);
              }}
            />
            {isActive && (
              <NodeTooltip
                node={node}
                position={posData.position}
                visible
                isServer={false}
                isAdmin={isAdmin}
                onBlock={onBlockNode}
                onUnblock={onUnblockNode}
                setHoveredNodeId={(id) => {
                  setHoveredNodeId(id);
                  if (id === null) setTappedNodeId(null);
                }}
              />
            )}
          </React.Fragment>
        );
      })}
    </>
  );
}

/* ═══════════════════════════════════════════════════════════════
   MAIN COMPONENT  (theme-aware wrapper)
   ═══════════════════════════════════════════════════════════════ */
function NetworkTopology({ projectId }) {
  const fl = useFL(projectId);
  const currentUser = useStore((s) => s.user);
  const projectRoles = useStore((s) => s.projectRoles);

  const isAdmin = useMemo(() => {
    const role = projectRoles?.[projectId]?.[currentUser?.id];
    if (role) return role === "lead";
    const proj = fl.project;
    const member = proj?.members?.find((m) => m.userId === currentUser?.id);
    return member?.role === "lead";
  }, [projectRoles, projectId, currentUser?.id, fl.project]);

  const [logEvents, setLogEvents] = useState([]);
  const lastLoggedNodesRef = useRef(0);
  const prevRoundRef = useRef(fl.currentRound);
  const [autoRotate, setAutoRotate] = useState(true);

  const pushLog = useCallback((message, type) => {
    const timestamp = new Date().toLocaleTimeString("en-US", {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
    setLogEvents((prev) =>
      [
        { id: Math.random().toString(), timestamp, message, type },
        ...prev,
      ].slice(0, 15),
    );
  }, []);

  useEffect(() => {
    if (!fl.nodes || fl.nodes.length === 0) return;
    if (lastLoggedNodesRef.current === 0) {
      pushLog(
        "Network initialized with " + fl.nodes.length + " clients",
        "default",
      );
      lastLoggedNodesRef.current = fl.nodes.length;
    }
  }, [fl.nodes?.length, pushLog]);

  useEffect(() => {
    if (fl.currentRound !== prevRoundRef.current && fl.latestRound) {
      pushLog(
        `Round ${fl.currentRound} complete — accuracy: ${fl.latestRound.globalAccuracy?.toFixed(1) || 0}%`,
        "round",
      );
      if (fl.currentRound > 0 && fl.currentRound % 5 === 0) {
        pushLog(
          `Round ${fl.currentRound} aggregation triggered`,
          "aggregation",
        );
      }
      prevRoundRef.current = fl.currentRound;
    }
  }, [fl.currentRound, fl.latestRound, pushLog]);

  /* ── Loading ── */
  if (!fl.nodes || fl.nodes.length === 0) {
    return (
      <div className="h-[350px] sm:h-[400px] md:h-[460px] lg:h-[520px] w-full flex items-center justify-center bg-slate-50 dark:bg-[#050810] rounded-xl border border-border">
        <div className="flex flex-col items-center gap-3 text-slate-500 dark:text-slate-400 font-mono text-xs sm:text-sm">
          <div className="w-5 h-5 sm:w-6 sm:h-6 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin" />
          Initializing network…
        </div>
      </div>
    );
  }

  /* ── Derived metrics ── */
  const activeCount = fl.nodes.filter(
    (n) => n.status === "ACTIVE" || n.status === "SLOW",
  ).length;
  const flaggedCount = fl.nodes.filter(
    (n) => n.status === "BYZANTINE",
  ).length;
  const avgTrust = (
    (fl.nodes.reduce((acc, n) => acc + (n.trust || 0), 0) /
      Math.max(fl.nodes.length, 1)) *
    100
  ).toFixed(1);

  return (
    <div
      className={[
        "relative w-full flex flex-col overflow-hidden rounded-xl border",
        // Responsive heights — tall enough for the 3D scene to be clearly visible
        "h-[350px] sm:h-[400px] md:h-[460px] lg:h-[520px]",
        // Light mode
        "bg-slate-50 border-slate-200",
        // Dark mode
        "dark:bg-[#050810] dark:border-white/10",
      ].join(" ")}
    >
      {/* ─── Status Bar — compact single row on mobile ──── */}
      <div
        className={[
          "flex-none flex items-center justify-between",
          "px-2 sm:px-4 py-1 sm:py-2 z-10 border-b",
          "bg-white/90 backdrop-blur border-slate-200",
          "dark:bg-slate-900/80 dark:backdrop-blur dark:border-white/5",
        ].join(" ")}
      >
        {/* Left: compact metrics — always single row */}
        <div className="flex items-center gap-2 sm:gap-3 md:gap-4 overflow-x-auto">
          {/* Active */}
          <div className="flex items-center gap-1 shrink-0">
            <span className="w-1.5 h-1.5 sm:w-2 sm:h-2 rounded-full bg-emerald-500" />
            <span className="text-[8px] sm:text-[10px] font-mono uppercase tracking-wider font-semibold text-slate-500 dark:text-slate-400 hidden min-[400px]:inline">
              Active
            </span>
            <span className="font-mono text-[9px] sm:text-xs font-bold text-emerald-600 dark:text-emerald-400">
              {activeCount}
            </span>
          </div>
          {/* Flagged */}
          <div className="flex items-center gap-1 shrink-0">
            <span className="w-1.5 h-1.5 sm:w-2 sm:h-2 rounded-full bg-rose-500" />
            <span className="text-[8px] sm:text-[10px] font-mono uppercase tracking-wider font-semibold text-slate-500 dark:text-slate-400 hidden min-[400px]:inline">
              Flagged
            </span>
            <span className="font-mono text-[9px] sm:text-xs font-bold text-rose-600 dark:text-rose-400">
              {flaggedCount}
            </span>
          </div>
          {/* Avg Trust — only on 640px+ */}
          <div className="hidden sm:flex items-center gap-1 shrink-0">
            <span className="text-[10px] font-mono uppercase tracking-wider font-semibold text-slate-500 dark:text-slate-400">
              Trust
            </span>
            <span className="font-mono text-xs font-bold text-cyan-600 dark:text-cyan-400">
              {avgTrust}%
            </span>
          </div>
          {/* Round */}
          <div className="flex items-center gap-1 shrink-0">
            <span className="text-[8px] sm:text-[10px] font-mono uppercase tracking-wider font-semibold text-slate-500 dark:text-slate-400">
              R
            </span>
            <span className="font-mono text-[9px] sm:text-xs font-bold text-slate-700 dark:text-slate-200">
              {fl.currentRound}
            </span>
          </div>
        </div>

        {/* Right: orbit toggle */}
        <div className="flex items-center gap-1.5 shrink-0 ml-2">
          {isAdmin && (
            <div className="text-[10px] text-slate-400 dark:text-slate-500 font-mono hidden lg:block px-2 py-1 bg-slate-100 dark:bg-white/5 rounded">
              Hover node → Block
            </div>
          )}
          <button
            className={[
              "px-1.5 sm:px-3 py-0.5 sm:py-1 rounded text-[9px] sm:text-xs font-mono transition-colors whitespace-nowrap",
              "bg-slate-100 hover:bg-slate-200 dark:bg-white/5 dark:hover:bg-white/10",
              autoRotate
                ? "text-cyan-600 dark:text-cyan-400"
                : "text-slate-500 dark:text-slate-400",
            ].join(" ")}
            onClick={() => setAutoRotate(!autoRotate)}
          >
            {autoRotate ? "Orbit: ON" : "Orbit: OFF"}
          </button>
        </div>
      </div>

      {/* ─── 3D Canvas — guaranteed min height ─────────── */}
      <div className="flex-1 relative" style={{ minHeight: "200px" }}>
        <Canvas
          camera={{ position: [0, 5, 12], fov: 50 }}
          frameloop="always"
          gl={{ antialias: true }}
        >
          <NetworkScene
            fl={fl}
            isRunning={fl.isRunning}
            onBlockNode={fl.blockNode}
            onUnblockNode={fl.unblockNode}
            isAdmin={isAdmin}
            autoRotate={autoRotate}
          />
        </Canvas>

        <LiveLog events={logEvents} />
        <NetworkLegend />
      </div>
    </div>
  );
}

export default NetworkTopology;
