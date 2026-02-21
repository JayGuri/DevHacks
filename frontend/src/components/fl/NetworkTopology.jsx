import React, {
  useRef,
  useState,
  useEffect,
  useMemo,
  useCallback,
} from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { OrbitControls, Html, Line, Billboard, Text } from "@react-three/drei";
import * as THREE from "three";
import { motion, AnimatePresence } from "framer-motion";
import useFL from "@/hooks/useFL";
import { useStore } from "@/lib/store";
import { isProjectLead } from "@/lib/projectUtils";
import { Badge } from "@/components/ui/badge";

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
const LINE_OPACITY_ACTIVE = 0.6;
const LINE_OPACITY_SLOW = 0.35;
const LINE_OPACITY_BYZANTINE = 0.7;
const LINE_OPACITY_BLOCKED = 0.1;

const serverGeo = new THREE.SphereGeometry(SERVER_SIZE, 32, 32);
const clientGeo = new THREE.SphereGeometry(CLIENT_SIZE, 24, 24);
const glowGeo = new THREE.SphereGeometry(CLIENT_SIZE * 1.8, 12, 12);

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

function AnimatedEdge({
  start,
  end,
  status,
  active,
  nodeId,
  isNew,
}) {
  const edgeRef = useRef();
  const packetRef = useRef(null);
  const packetProgressRef = useRef(0);

  const curve = useMemo(() => {
    const hash = nodeId
      .split("")
      .reduce((acc, char) => acc + char.charCodeAt(0), 0);
    const randOffset = (hash % 10) / 10 - 0.5;
    const midpoint = [
      (start[0] + end[0]) / 2 + randOffset,
      (start[1] + end[1]) / 2 + 0.5,
      (start[2] + end[2]) / 2 + randOffset,
    ];
    return new THREE.CatmullRomCurve3([
      new THREE.Vector3(...start),
      new THREE.Vector3(...midpoint),
      new THREE.Vector3(...end),
    ]);
  }, [start, end, nodeId]);

  const points = useMemo(() => curve.getPoints(50), [curve]);

  const config = NODE_CONFIG[status] || NODE_CONFIG.ACTIVE;
  const isBlocked = status === "BLOCKED";
  const isByzantine = status === "BYZANTINE";
  const isSlow = status === "SLOW";

  const lineWidth =
    isByzantine ? 1.5
    : isSlow ? 0.8
    : isBlocked ? 0.5
    : 1;
  const targetOpacity =
    isByzantine ? LINE_OPACITY_BYZANTINE
    : isSlow ? LINE_OPACITY_SLOW
    : isBlocked ? LINE_OPACITY_BLOCKED
    : LINE_OPACITY_ACTIVE;

  const packetSize = isByzantine ? 0.09 : 0.06;
  const opacityRef = useRef(isNew ? 0 : targetOpacity);

  useFrame((state, delta) => {
    // Fade in new edges
    if (isNew && opacityRef.current < targetOpacity) {
      opacityRef.current = Math.min(
        targetOpacity,
        opacityRef.current + delta * 2,
      );
      if (edgeRef.current?.material) {
        edgeRef.current.material.opacity = opacityRef.current;
      }
    } else if (
      edgeRef.current?.material &&
      edgeRef.current.material.opacity !== targetOpacity
    ) {
      edgeRef.current.material.opacity = targetOpacity;
      opacityRef.current = targetOpacity;
    }

    // Animate data packet along the edge using refs — no setState
    if (active && !isBlocked && packetRef.current) {
      const speed =
        isByzantine ? 0.55
        : isSlow ? 0.15
        : 0.4;
      packetProgressRef.current = (packetProgressRef.current + delta * speed) % 1.0;
      const pt = curve.getPoint(packetProgressRef.current);
      packetRef.current.position.set(pt.x, pt.y, pt.z);
    }
  });

  return (
    <group>
      <Line
        ref={edgeRef}
        points={points}
        color={config.glowColor}
        lineWidth={lineWidth}
        transparent
        opacity={opacityRef.current}
      />
      {active && !isBlocked && (
        <mesh ref={packetRef}>
          <sphereGeometry args={[packetSize, 8, 8]} />
          <meshBasicMaterial color={config.glowColor} />
        </mesh>
      )}
    </group>
  );
}

function ServerNode({ position, onHover, onUnhover, hovered }) {
  const meshRef = useRef();
  const ringRef = useRef();
  const glowRef = useRef();

  useFrame((state, delta) => {
    if (!meshRef.current || !ringRef.current || !glowRef.current) return;
    meshRef.current.rotation.y += delta * 0.3;
    meshRef.current.rotation.x += delta * 0.1;

    ringRef.current.rotation.z += delta * 0.5;
    ringRef.current.rotation.x = Math.PI / 2.5;

    const breath = 1 + Math.sin(state.clock.elapsedTime * 0.8) * 0.03;
    meshRef.current.scale.setScalar(breath);

    const glow = 0.3 + Math.sin(state.clock.elapsedTime * 1.5) * 0.15;
    glowRef.current.material.opacity = glow;
  });

  return (
    <group position={position}>
      <mesh ref={meshRef} onPointerEnter={onHover} onPointerLeave={onUnhover}>
        <primitive object={serverGeo} attach="geometry" />
        <meshStandardMaterial
          color={NODE_CONFIG.SERVER.color}
          emissive={NODE_CONFIG.SERVER.emissive}
          emissiveIntensity={hovered ? 0.8 : 0.4}
          metalness={0.7}
          roughness={0.2}
        />
      </mesh>

      <mesh ref={glowRef}>
        <sphereGeometry args={[SERVER_SIZE * 1.6, 16, 16]} />
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

      <Billboard follow={true} lockX={false} lockY={false} lockZ={false}>
        <Text
          position={[0, SERVER_SIZE + 0.4, 0]}
          fontSize={0.18}
          color={NODE_CONFIG.SERVER.glowColor}
          anchorX="center"
          anchorY="middle"
          font="https://fonts.gstatic.com/s/jetbrainsmono/v13/tDbY2o-flEEny0FZhsfKu5WU4zr3E_BX0PnT8RD8yK1jOdnk.woff2"
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

function ClientNode({ node, position, onHover, onUnhover, hovered, isNew }) {
  const meshRef = useRef();
  const glowRef = useRef();
  const groupRef = useRef();
  const scaleRef = useRef(isNew ? 0 : 1);
  const [hasAppeared, setHasAppeared] = useState(!isNew);

  const config = NODE_CONFIG[node.status] || NODE_CONFIG.ACTIVE;

  useEffect(() => {
    if (isNew) {
      const timer = setTimeout(() => {
        setHasAppeared(true);
      }, 600);
      return () => clearTimeout(timer);
    }
  }, [isNew]);

  useFrame((state, delta) => {
    if (!meshRef.current || !glowRef.current || !groupRef.current) return;

    if (isNew && !hasAppeared) {
      const elapsed = state.clock.elapsedTime;
      if (scaleRef.current < 1) {
        scaleRef.current = Math.min(1.2, scaleRef.current + delta * 3);
      } else if (scaleRef.current > 1 && scaleRef.current !== 1.2) {
        scaleRef.current = Math.max(1, scaleRef.current - delta * 2);
      }
      groupRef.current.scale.setScalar(scaleRef.current);

      const targetPos = new THREE.Vector3(...position);
      const startPos = targetPos.clone().multiplyScalar(2.5);
      groupRef.current.position.lerpVectors(
        startPos,
        targetPos,
        scaleRef.current / 1.2,
      );
    } else {
      groupRef.current.position.set(...position);
      groupRef.current.scale.setScalar(1);
      if (config.pulseSpeed > 0) {
        const pulse =
          1 + Math.sin(state.clock.elapsedTime * config.pulseSpeed) * 0.08;
        meshRef.current.scale.setScalar(pulse);
      }
    }

    const glow =
      0.15 + Math.sin(state.clock.elapsedTime * config.pulseSpeed * 0.7) * 0.1;
    glowRef.current.material.opacity = glow;

    if (node.status === "BYZANTINE") {
      meshRef.current.position.x =
        Math.sin(state.clock.elapsedTime * 3.7) * 0.04;
      meshRef.current.position.y =
        Math.cos(state.clock.elapsedTime * 2.9) * 0.04;
    } else if (node.status === "SLOW") {
      meshRef.current.position.y =
        Math.sin(state.clock.elapsedTime * 0.5) * 0.06;
    } else {
      meshRef.current.position.set(0, 0, 0);
    }
  });

  return (
    <group ref={groupRef} position={position}>
      <mesh
        ref={meshRef}
        onPointerEnter={onHover}
        onPointerLeave={onUnhover}
        castShadow
      >
        <primitive object={clientGeo} attach="geometry" />
        <meshStandardMaterial
          color={config.color}
          emissive={config.emissive}
          emissiveIntensity={
            hovered ? 1.0
            : node.status === "BYZANTINE" ?
              0.6
            : 0.3
          }
          metalness={node.status === "BLOCKED" ? 0.1 : 0.5}
          roughness={node.status === "BLOCKED" ? 0.9 : 0.3}
          transparent={node.status === "BLOCKED"}
          opacity={node.status === "BLOCKED" ? 0.4 : 1.0}
        />
      </mesh>

      <mesh ref={glowRef}>
        <primitive object={glowGeo} attach="geometry" />
        <meshBasicMaterial
          color={config.glowColor}
          transparent
          opacity={0.12}
          depthWrite={false}
        />
      </mesh>

      <mesh>
        <sphereGeometry args={[CLIENT_SIZE * 0.45, 12, 12]} />
        <meshBasicMaterial color={config.glowColor} transparent opacity={0.6} />
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

function ServerTooltipContent({ fl }) {
  const method =
    fl.project?.config?.aggregationMethod?.replace(/_/g, " ") ||
    "Federated Averaging";
  const activeNodes = fl.nodes.filter(
    (n) => n.status !== "BLOCKED" && n.status !== "BYZANTINE",
  ).length;

  return (
    <div className="flex flex-col gap-2">
      <div className="font-bold text-cyan-400">⬡ CENTRAL SERVER</div>
      <div className="h-px bg-slate-700 w-full" />
      <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs">
        <span className="text-slate-400">Role:</span>
        <span className="text-slate-200">Global Model Host</span>
        <span className="text-slate-400">Status:</span>
        <span className="text-emerald-400">● Online</span>
        <span className="text-slate-400">Function:</span>
        <span className="text-slate-200">Aggregation Engine</span>
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
  const typeLabel =
    node.status === "BYZANTINE" ? "Byzantine"
    : node.status === "SLOW" ? "Honest Slow"
    : node.status === "BLOCKED" ? "Blocked"
    : "Honest Fast";

  return (
    <div className="flex flex-col gap-2" style={{ pointerEvents: "auto" }}>
      <div
        className="font-bold flex items-center gap-2"
        style={{ color: config.glowColor }}
      >
        <span>●</span>
        <span>{node.displayId}</span>
        <span
          className="text-xs px-2 py-0.5 rounded-full"
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
        <span className="text-slate-400">Type:</span>
        <span className="text-slate-200">{typeLabel}</span>
      </div>

      {node.status === "BYZANTINE" && (
        <div className="mt-1 p-2 bg-rose-950 border border-rose-900 rounded text-xs text-rose-300">
          ⚠ FLAGGED — Update excluded from aggregation
        </div>
      )}
      {node.status === "BLOCKED" && (
        <div className="mt-1 p-2 bg-slate-900 border border-slate-700 rounded text-xs text-slate-400">
          🚫 BLOCKED — Manually excluded by admin
        </div>
      )}
      {node.status === "SLOW" && (
        <div className="mt-1 p-2 bg-amber-950 border border-amber-900 rounded text-xs text-amber-300">
          ⏱ ASYNC — Update delayed by {node.staleness || 0} rounds
        </div>
      )}

      {isAdmin && (
        <div className="mt-2 pt-2 border-t border-slate-700 flex justify-end">
          {node.status === "BLOCKED" ?
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
          : <button
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
          }
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
            style={{
              background: "hsl(222, 47%, 9%)",
              border: "1px solid hsl(222, 30%, 18%)",
              borderRadius: "10px",
              padding: "12px 16px",
              minWidth: "220px",
              boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
              fontFamily: "'JetBrains Mono', monospace",
              color: "#c8d8f0",
              pointerEvents: isAdmin && !isServer ? "auto" : "none",
            }}
          >
            {isServer ?
              <ServerTooltipContent fl={fl} />
            : <NodeTooltipContent
                node={node}
                isAdmin={isAdmin}
                onBlock={onBlock}
                onUnblock={onUnblock}
                setHoveredNodeId={setHoveredNodeId}
              />
            }
          </motion.div>
        )}
      </AnimatePresence>
    </Html>
  );
}

function LiveLog({ events }) {
  return (
    <div className="absolute top-4 right-4 w-72 max-h-72 overflow-hidden bg-[#050810]/85 border border-white/10 rounded-lg backdrop-blur-md p-3 z-10 pointer-events-none flex flex-col">
      <div className="text-cyan-400 font-mono text-xs font-bold mb-2 tracking-wider">
        LIVE LOG
      </div>
      <div className="flex-1 overflow-y-auto flex flex-col gap-1 pr-1">
        <AnimatePresence initial={false}>
          {events.map((ev) => (
            <motion.div
              key={ev.id}
              initial={{ opacity: 0, y: -12, height: 0 }}
              animate={{ opacity: 1, y: 0, height: "auto" }}
              transition={{ duration: 0.2 }}
              className="text-[10px] font-mono whitespace-nowrap overflow-hidden text-ellipsis leading-tight"
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
    <div className="absolute bottom-4 left-4 p-3 bg-[#050810]/85 border border-white/10 rounded-lg backdrop-blur-md z-10 pointer-events-none">
      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 mb-2">
        <div className="flex items-center gap-1.5 text-xs text-slate-300 font-mono">
          <span className="text-emerald-500">●</span> Active
        </div>
        <div className="flex items-center gap-1.5 text-xs text-slate-300 font-mono">
          <span className="text-amber-500">●</span> Slow/Async
        </div>
        <div className="flex items-center gap-1.5 text-xs text-slate-300 font-mono">
          <span className="text-rose-500">●</span> Flagged
        </div>
        <div className="flex items-center gap-1.5 text-xs text-slate-300 font-mono">
          <span className="text-slate-500">●</span> Blocked
        </div>
        <div className="flex items-center gap-1.5 text-xs text-slate-300 font-mono">
          <span className="text-indigo-400">●</span> Joining
        </div>
        <div className="flex items-center gap-1.5 text-xs text-slate-300 font-mono">
          <span className="text-cyan-400">⬡</span> Server
        </div>
      </div>
      <div className="text-[9px] text-slate-500 font-mono pt-1.5 border-t border-slate-700/50">
        Drag to orbit · Scroll to zoom
        <br />
        Hover for details
      </div>
    </div>
  );
}

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

  const nodes = fl.nodes;

  const nodePositions = useMemo(() => computeNodePositions(nodes), [nodes]);

  const starPositions = useMemo(() => {
    const pos = new Float32Array(300 * 3);
    for (let i = 0; i < 300; i++) {
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      const r = 20 + Math.random() * 10;
      pos[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      pos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
      pos[i * 3 + 2] = r * Math.cos(phi);
    }
    return pos;
  }, []);

  return (
    <>
      <ambientLight intensity={0.3} />
      <pointLight
        position={[0, 0, 0]}
        intensity={2}
        color="#06b6d4"
        distance={12}
        decay={2}
      />
      <pointLight position={[8, 8, 8]} intensity={0.4} color="#ffffff" />
      <pointLight position={[-8, -4, -8]} intensity={0.2} color="#818cf8" />

      <color attach="background" args={["#050810"]} />

      <points>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            args={[starPositions, 3]}
          />
        </bufferGeometry>
        <pointsMaterial size={0.04} color="#475569" transparent opacity={0.6} />
      </points>

      <gridHelper args={[24, 24, "#0f1a2e", "#0a1220"]} position={[0, -4, 0]} />

      <OrbitControls
        enableDamping={true}
        dampingFactor={0.05}
        minDistance={4}
        maxDistance={14}
        autoRotate={autoRotate && !hoveredNodeId && !hoveredServer}
        autoRotateSpeed={0.4}
      />

      <group>
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
              isNew={!node.roundsContributed}
            />
          );
        })}

        <ServerNode
          position={[0, 0, 0]}
          onHover={() => setHoveredServer(true)}
          onUnhover={() => setHoveredServer(false)}
          hovered={hoveredServer}
        />

        {hoveredServer && (
          <NodeTooltip
            position={[0, SERVER_SIZE + 0.5, 0]}
            visible={true}
            isServer={true}
            fl={fl}
          />
        )}

        {nodes.map((node) => {
          const posData = nodePositions.get(node.nodeId);
          if (!posData) return null;
          const isHovered = hoveredNodeId === node.nodeId;

          return (
            <React.Fragment key={`node-${node.nodeId}`}>
              <ClientNode
                node={node}
                position={posData.position}
                onHover={() => setHoveredNodeId(node.nodeId)}
                onUnhover={() => setHoveredNodeId(null)}
                hovered={isHovered}
                isNew={!node.roundsContributed}
              />
              {isHovered && (
                <NodeTooltip
                  node={node}
                  position={posData.position}
                  visible={true}
                  isServer={false}
                  isAdmin={isAdmin}
                  onBlock={onBlockNode}
                  onUnblock={onUnblockNode}
                  setHoveredNodeId={setHoveredNodeId}
                />
              )}
            </React.Fragment>
          );
        })}
      </group>
    </>
  );
}

function NetworkTopology({ projectId }) {
  const fl = useFL(projectId);
  const store = useStore();
  const currentUser = store.user;
  const isAdmin = isProjectLead(currentUser?.id, projectId, store);

  const [logEvents, setLogEvents] = useState([]);
  const prevNodesRef = useRef([]);
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

    if (prevNodesRef.current.length > 0) {
      fl.nodes.forEach((node) => {
        const prev = prevNodesRef.current.find((n) => n.nodeId === node.nodeId);
        if (!prev) {
          pushLog(
            `NODE_${node.displayId || node.nodeId.substring(0, 4)} joined the network`,
            "join",
          );
        } else if (prev.status !== node.status) {
          if (node.status === "BYZANTINE")
            pushLog(`${node.displayId} flagged as malicious`, "byzantine");
          else if (node.status === "BLOCKED")
            pushLog(`${node.displayId} blocked by admin`, "blocked");
          else if (node.status === "ACTIVE" && prev.status === "BYZANTINE")
            pushLog(`${node.displayId} cleared`, "join");
          else if (node.status === "SLOW")
            pushLog(`${node.displayId} experiencing latency`, "default");
        }
      });
    } else {
      pushLog(
        "Network initialized with " + fl.nodes.length + " clients",
        "default",
      );
    }
    prevNodesRef.current = fl.nodes;
  }, [fl.nodes, pushLog]);

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

  if (!fl.nodes || fl.nodes.length === 0) {
    return (
      <div className="h-[320px] md:h-[520px] w-full flex items-center justify-center bg-[#050810] rounded-xl border border-border">
        <div className="flex flex-col items-center gap-3 text-slate-400 font-mono text-sm">
          <div className="w-6 h-6 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin" />
          Initializing network...
        </div>
      </div>
    );
  }

  return (
    <div className="relative w-full h-[320px] md:h-[520px] flex flex-col bg-[#050810] rounded-xl border border-border overflow-hidden">
      <div className="flex-none flex items-center justify-between px-4 py-2 bg-slate-900/80 backdrop-blur z-10 border-b border-white/5">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5 metric-label">
            <span className="w-2 h-2 rounded-full bg-emerald-500" />
            <span className="text-slate-300">Active</span>
            <span className="mono-data ml-1 text-emerald-400">
              {
                fl.nodes.filter(
                  (n) => n.status === "ACTIVE" || n.status === "SLOW",
                ).length
              }
            </span>
          </div>
          <div className="flex items-center gap-1.5 metric-label">
            <span className="w-2 h-2 rounded-full bg-rose-500" />
            <span className="text-slate-300">Flagged</span>
            <span className="mono-data ml-1 text-rose-400">
              {fl.nodes.filter((n) => n.status === "BYZANTINE").length}
            </span>
          </div>
          <div className="flex items-center gap-1.5 metric-label">
            <span className="text-slate-300">Avg Trust</span>
            <span className="mono-data ml-1 text-cyan-400">
              {(
                (fl.nodes.reduce((acc, n) => acc + (n.trust || 0), 0) /
                  Math.max(fl.nodes.length, 1)) *
                100
              ).toFixed(1)}
              %
            </span>
          </div>
          <div className="flex items-center gap-1.5 metric-label">
            <span className="text-slate-300">Round</span>
            <span className="mono-data ml-1 text-slate-200">
              {fl.currentRound}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {isAdmin && (
            <div className="text-[10px] text-slate-400 font-mono hidden sm:block mr-2 px-2 py-1 bg-white/5 rounded">
              Hover node → Block in tooltip
            </div>
          )}
          <button
            className={`px-3 py-1 bg-white/5 hover:bg-white/10 rounded text-xs font-mono transition-colors ${autoRotate ? "text-cyan-400" : "text-slate-400"}`}
            onClick={() => setAutoRotate(!autoRotate)}
          >
            {autoRotate ? "Orbit: ON" : "Orbit: OFF"}
          </button>
        </div>
      </div>

      <div className="flex-1 relative">
        <Canvas
          camera={{ position: [0, 3, 10], fov: 55 }}
          shadows
          gl={{
            antialias: true,
            alpha: false,
            powerPreference: "high-performance",
          }}
          frameloop={fl.isRunning ? "always" : "demand"}
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

export default React.memo(NetworkTopology);
