"use client";

import { useEffect, useRef, useState, useMemo, useCallback } from "react";
import {
  Search,
  RefreshCw,
  Sliders,
  ZoomIn,
  ZoomOut,
  Maximize2,
  ExternalLink,
  ArrowRight,
  ShieldCheck,
  User,
  Info,
  Layers,
  Sparkles,
  Sun,
  Moon,
} from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api/client";

interface GraphNodeData {
  id: string;
  name: string;
  qualified_name: string;
  asset_type: string;
  certification_status: string;
  owner_name?: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  degree: number;
}

interface GraphEdgeData {
  id: string;
  source: string;
  target: string;
  sourceNode?: GraphNodeData;
  targetNode?: GraphNodeData;
  type: string;
  confidence: number;
}

const TYPE_COLORS: Record<string, string> = {
  TABLE: "#0284c7", // Sky blue
  DATABASE: "#0369a1", // Deep blue
  TRANSFORMATION_MODEL: "#059669", // Emerald green
  DASHBOARD: "#7c3aed", // Violet purple
  METRIC: "#d97706", // Amber
  DOCUMENTATION: "#ea580c", // Orange
  PULL_REQUEST: "#9333ea", // Purple
  CHANNEL: "#db2777", // Pink
};

const STATUS_COLORS: Record<string, string> = {
  CERTIFIED: "#10b981",
  DISPUTED: "#ef4444",
  PENDING_REVIEW: "#f59e0b",
  UNVERIFIED: "#64748b",
};

export default function ContextGraphPage() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  // Raw data from API
  const [rawNodes, setRawNodes] = useState<any[]>([]);
  const [rawEdges, setRawEdges] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  // Simulation State
  const nodesRef = useRef<GraphNodeData[]>([]);
  const edgesRef = useRef<GraphEdgeData[]>([]);
  const animFrameIdRef = useRef<number | null>(null);
  const alphaRef = useRef<number>(1.0);

  // Camera View Transform (Pan & Zoom)
  const cameraRef = useRef<{ x: number; y: number; zoom: number }>({ x: 0, y: 0, zoom: 1.0 });

  // Interaction State
  const hoveredNodeRef = useRef<GraphNodeData | null>(null);
  const selectedNodeRef = useRef<GraphNodeData | null>(null);
  const draggedNodeRef = useRef<GraphNodeData | null>(null);
  const dragStartPosRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const isPanningRef = useRef<boolean>(false);
  const panStartRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });

  // UI State
  const [selectedNode, setSelectedNode] = useState<GraphNodeData | null>(null);
  const [hoveredNode, setHoveredNode] = useState<GraphNodeData | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [filterType, setFilterType] = useState<string>("ALL");
  const [colorMode, setColorMode] = useState<"type" | "status">("type");
  const [themeMode, setThemeMode] = useState<"light" | "dark">("light");
  const [showSettings, setShowSettings] = useState(false);

  // Physics Config Sliders
  const [repulsion, setRepulsion] = useState(240);
  const [linkDistance, setLinkDistance] = useState(120);
  const [gravity, setGravity] = useState(0.04);
  const [nodeScale, setNodeScale] = useState(1.0);
  const [showLabels, setShowLabels] = useState(true);

  const repulsionRef = useRef(repulsion);
  const linkDistRef = useRef(linkDistance);
  const gravityRef = useRef(gravity);
  const nodeScaleRef = useRef(nodeScale);
  const showLabelsRef = useRef(showLabels);
  const colorModeRef = useRef(colorMode);
  const themeModeRef = useRef(themeMode);
  const searchTermRef = useRef(searchTerm);
  const filterTypeRef = useRef(filterType);

  useEffect(() => {
    repulsionRef.current = repulsion;
    linkDistRef.current = linkDistance;
    gravityRef.current = gravity;
    nodeScaleRef.current = nodeScale;
    showLabelsRef.current = showLabels;
    colorModeRef.current = colorMode;
    themeModeRef.current = themeMode;
    searchTermRef.current = searchTerm;
    filterTypeRef.current = filterType;
    alphaRef.current = Math.max(alphaRef.current, 0.3); // Re-energize simulation
  }, [repulsion, linkDistance, gravity, nodeScale, showLabels, colorMode, themeMode, searchTerm, filterType]);

  // Load Graph Data
  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getGlobalGraph(200);
      setRawNodes(data.nodes || []);
      setRawEdges(data.edges || []);
      initSimulation(data.nodes || [], data.edges || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Sync initial theme with global state
    const isDark = document.documentElement.classList.contains("dark");
    setThemeMode(isDark ? "dark" : "light");

    const onThemeChange = (e: any) => {
      const next = e.detail?.theme || (document.documentElement.classList.contains("dark") ? "dark" : "light");
      setThemeMode(next);
    };

    window.addEventListener("contextos-theme-change", onThemeChange);
    return () => window.removeEventListener("contextos-theme-change", onThemeChange);
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Initialize Force Simulation
  const initSimulation = (nodesData: any[], edgesData: any[]) => {
    const canvas = canvasRef.current;
    const width = canvas ? canvas.clientWidth : 1000;
    const height = canvas ? canvas.clientHeight : 700;

    // Center camera
    cameraRef.current = { x: width / 2, y: height / 2, zoom: 0.95 };

    // Calculate degree centrality (number of connections)
    const degreeMap: Record<string, number> = {};
    edgesData.forEach((e) => {
      degreeMap[e.source] = (degreeMap[e.source] || 0) + 1;
      degreeMap[e.target] = (degreeMap[e.target] || 0) + 1;
    });

    // Create initial circular orbital layout
    const count = nodesData.length;
    const radiusSpread = Math.min(width, height) * 0.32;

    const simNodes: GraphNodeData[] = nodesData.map((n, i) => {
      const angle = (i / Math.max(count, 1)) * Math.PI * 2;
      const deg = degreeMap[n.id] || 1;
      return {
        ...n,
        x: Math.cos(angle) * (radiusSpread + (Math.random() - 0.5) * 80),
        y: Math.sin(angle) * (radiusSpread + (Math.random() - 0.5) * 80),
        vx: (Math.random() - 0.5) * 2,
        vy: (Math.random() - 0.5) * 2,
        radius: Math.max(8, Math.min(24, 8 + deg * 3.5)),
        degree: deg,
      };
    });

    const nodeMap = new Map<string, GraphNodeData>();
    simNodes.forEach((n) => nodeMap.set(n.id, n));

    const simEdges: GraphEdgeData[] = edgesData
      .map((e) => ({
        ...e,
        sourceNode: nodeMap.get(e.source),
        targetNode: nodeMap.get(e.target),
      }))
      .filter((e) => e.sourceNode && e.targetNode);

    nodesRef.current = simNodes;
    edgesRef.current = simEdges;
    alphaRef.current = 1.0;
  };

  // Main Physics Simulation & Canvas Render Loop
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let isRunning = true;

    const render = () => {
      if (!isRunning) return;

      const dpr = window.devicePixelRatio || 1;
      const width = canvas.clientWidth;
      const height = canvas.clientHeight;

      if (canvas.width !== width * dpr || canvas.height !== height * dpr) {
        canvas.width = width * dpr;
        canvas.height = height * dpr;
      }

      ctx.save();
      ctx.scale(dpr, dpr);

      // 1. Physics Step (Velocity-Verlet with Damping & Cooling)
      const alpha = alphaRef.current;
      const nodes = nodesRef.current;
      const edges = edgesRef.current;

      if (alpha > 0.005) {
        const repForce = repulsionRef.current;
        const linkDist = linkDistRef.current;
        const grav = gravityRef.current;

        // Repulsion between all node pairs (Coulomb force)
        for (let i = 0; i < nodes.length; i++) {
          for (let j = i + 1; j < nodes.length; j++) {
            const a = nodes[i];
            const b = nodes[j];
            const dx = b.x - a.x;
            const dy = b.y - a.y;
            const distSq = dx * dx + dy * dy + 1;
            const dist = Math.sqrt(distSq);

            if (dist < 600) {
              const force = (repForce * 120 * alpha) / distSq;
              const fx = (dx / dist) * force;
              const fy = (dy / dist) * force;

              if (a !== draggedNodeRef.current) {
                a.vx -= fx;
                a.vy -= fy;
              }
              if (b !== draggedNodeRef.current) {
                b.vx += fx;
                b.vy += fy;
              }
            }
          }
        }

        // Spring attraction along edges (Hooke's law)
        for (let i = 0; i < edges.length; i++) {
          const e = edges[i];
          const a = e.sourceNode!;
          const b = e.targetNode!;
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const dist = Math.sqrt(dx * dx + dy * dy) + 0.1;
          const delta = dist - linkDist;
          const force = delta * 0.045 * alpha;
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;

          if (a !== draggedNodeRef.current) {
            a.vx += fx;
            a.vy += fy;
          }
          if (b !== draggedNodeRef.current) {
            b.vx -= fx;
            b.vy -= fy;
          }
        }

        // Center gravity pull
        for (let i = 0; i < nodes.length; i++) {
          const n = nodes[i];
          if (n !== draggedNodeRef.current) {
            n.vx += -n.x * grav * alpha;
            n.vy += -n.y * grav * alpha;

            // Damping velocity
            n.vx *= 0.86;
            n.vy *= 0.86;

            n.x += n.vx;
            n.y += n.vy;
          }
        }

        // Cool alpha
        alphaRef.current = Math.max(0.002, alpha * 0.985);
      }

      // 2. Clear Screen — Matching App Theme
      const isDark = themeModeRef.current === "dark";
      ctx.fillStyle = isDark ? "#0c0e14" : "#f8fafc";
      ctx.fillRect(0, 0, width, height);

      // Camera Transform
      const { x: camX, y: camY, zoom } = cameraRef.current;
      ctx.save();
      ctx.translate(camX, camY);
      ctx.scale(zoom, zoom);

      // Dot Grid Matrix
      const gridSize = 36;
      const startX = Math.floor((-camX / zoom - 200) / gridSize) * gridSize;
      const endX = Math.ceil((width / zoom - camX / zoom + 200) / gridSize) * gridSize;
      const startY = Math.floor((-camY / zoom - 200) / gridSize) * gridSize;
      const endY = Math.ceil((height / zoom - camY / zoom + 200) / gridSize) * gridSize;

      ctx.fillStyle = isDark ? "rgba(255, 255, 255, 0.04)" : "rgba(148, 163, 184, 0.28)";
      for (let gx = startX; gx <= endX; gx += gridSize) {
        for (let gy = startY; gy <= endY; gy += gridSize) {
          ctx.beginPath();
          ctx.arc(gx, gy, 1, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      // Active focus tracking
      const activeNode = hoveredNodeRef.current || selectedNodeRef.current;
      const activeNeighbors = new Set<string>();
      if (activeNode) {
        activeNeighbors.add(activeNode.id);
        edges.forEach((e) => {
          if (e.sourceNode?.id === activeNode.id) activeNeighbors.add(e.targetNode!.id);
          if (e.targetNode?.id === activeNode.id) activeNeighbors.add(e.sourceNode!.id);
        });
      }

      const activeSearch = searchTermRef.current.toLowerCase();
      const currentFilter = filterTypeRef.current;

      // 3. Draw Edges (Subtle lines in light/dark theme)
      for (let i = 0; i < edges.length; i++) {
        const e = edges[i];
        const a = e.sourceNode!;
        const b = e.targetNode!;

        const isConnectedToActive =
          activeNode && (a.id === activeNode.id || b.id === activeNode.id);

        let strokeColor = isDark
          ? "rgba(148, 163, 184, 0.2)"
          : "rgba(148, 163, 184, 0.4)";
        let lineWidth = 1.2;

        if (activeNode) {
          if (isConnectedToActive) {
            strokeColor = isDark
              ? e.type === "INFERRED_SAME_AS"
                ? "#38bdf8"
                : "#c084fc"
              : e.type === "INFERRED_SAME_AS"
              ? "#0284c7"
              : "#7c3aed";
            lineWidth = 2.2;
          } else {
            strokeColor = isDark ? "rgba(148, 163, 184, 0.04)" : "rgba(148, 163, 184, 0.1)";
          }
        }

        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.strokeStyle = strokeColor;
        ctx.lineWidth = lineWidth / zoom;
        ctx.stroke();

        // Edge indicator pulse on active edge
        if (isConnectedToActive) {
          const midX = (a.x + b.x) / 2;
          const midY = (a.y + b.y) / 2;
          ctx.save();
          ctx.fillStyle = strokeColor;
          ctx.beginPath();
          ctx.arc(midX, midY, 2.5 / zoom, 0, Math.PI * 2);
          ctx.fill();
          ctx.restore();
        }
      }

      // 4. Draw Nodes (Obsidian Floating Orbital Bubbles)
      const scale = nodeScaleRef.current;
      const cMode = colorModeRef.current;

      for (let i = 0; i < nodes.length; i++) {
        const n = nodes[i];
        const isHovered = hoveredNodeRef.current?.id === n.id;
        const isSelected = selectedNodeRef.current?.id === n.id;
        const isNeighbor = activeNeighbors.has(n.id);
        const matchesFilter = currentFilter === "ALL" || n.asset_type === currentFilter;
        const matchesSearch =
          !activeSearch ||
          n.name.toLowerCase().includes(activeSearch) ||
          n.qualified_name.toLowerCase().includes(activeSearch);

        const baseColor =
          cMode === "status"
            ? STATUS_COLORS[n.certification_status] || "#64748b"
            : TYPE_COLORS[n.asset_type] || "#0284c7";

        let nodeAlpha = 1.0;
        if (activeNode) {
          nodeAlpha = isHovered || isSelected ? 1.0 : isNeighbor ? 0.9 : 0.15;
        } else if (!matchesFilter || !matchesSearch) {
          nodeAlpha = 0.15;
        }

        const r = n.radius * scale;

        // Outer Glow / Halo for focused node
        if (isSelected || isHovered || (activeSearch && matchesSearch)) {
          ctx.save();
          ctx.beginPath();
          ctx.arc(n.x, n.y, r + 6, 0, Math.PI * 2);
          ctx.fillStyle = isDark
            ? isSelected
              ? "rgba(255, 255, 255, 0.25)"
              : "rgba(56, 189, 248, 0.25)"
            : isSelected
            ? "rgba(15, 23, 42, 0.15)"
            : "rgba(2, 132, 199, 0.2)";
          ctx.fill();
          ctx.restore();
        }

        // Inner Planetary Node Body with radial depth
        ctx.save();
        ctx.globalAlpha = nodeAlpha;
        ctx.beginPath();
        ctx.arc(n.x, n.y, r, 0, Math.PI * 2);

        const grad = ctx.createRadialGradient(
          n.x - r * 0.3,
          n.y - r * 0.3,
          r * 0.1,
          n.x,
          n.y,
          r
        );
        grad.addColorStop(0, "#ffffff");
        grad.addColorStop(0.35, baseColor);
        grad.addColorStop(1, baseColor);

        ctx.fillStyle = grad;
        ctx.fill();

        // Node outline
        ctx.strokeStyle = isDark ? "rgba(255, 255, 255, 0.4)" : "rgba(255, 255, 255, 0.85)";
        ctx.lineWidth = 1.5 / zoom;
        ctx.stroke();
        ctx.restore();

        // 5. Floating Text Labels
        const showThisLabel =
          showLabelsRef.current &&
          (zoom > 0.65 || isHovered || isSelected || isNeighbor || n.degree >= 3);

        if (showThisLabel && nodeAlpha > 0.3) {
          ctx.save();
          ctx.globalAlpha = isHovered || isSelected ? 1.0 : isNeighbor ? 0.95 : 0.75;
          ctx.font = `${isHovered || isSelected ? "bold " : ""}11px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`;
          ctx.textAlign = "center";
          ctx.textBaseline = "top";

          // Light mode text shadow / halo for maximum legibility
          if (!isDark) {
            ctx.fillStyle = "rgba(255, 255, 255, 0.95)";
            ctx.fillText(n.name, n.x + 0.5, n.y + r + 5.5);
            ctx.fillText(n.name, n.x - 0.5, n.y + r + 4.5);
            ctx.fillStyle = isHovered || isSelected ? "#0f172a" : "#334155";
          } else {
            ctx.fillStyle = "rgba(0, 0, 0, 0.8)";
            ctx.fillText(n.name, n.x + 0.5, n.y + r + 5.5);
            ctx.fillStyle = isHovered || isSelected ? "#ffffff" : "#cbd5e1";
          }

          ctx.fillText(n.name, n.x, n.y + r + 5);
          ctx.restore();
        }
      }

      ctx.restore(); // Restore camera scale & pan
      ctx.restore(); // Restore DPR scale

      animFrameIdRef.current = requestAnimationFrame(render);
    };

    animFrameIdRef.current = requestAnimationFrame(render);

    return () => {
      isRunning = false;
      if (animFrameIdRef.current) cancelAnimationFrame(animFrameIdRef.current);
    };
  }, []);

  // Screen -> World coordinate conversion
  const screenToWorld = useCallback((clientX: number, clientY: number) => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    const sx = clientX - rect.left;
    const sy = clientY - rect.top;
    const { x: camX, y: camY, zoom } = cameraRef.current;
    return {
      x: (sx - camX) / zoom,
      y: (sy - camY) / zoom,
    };
  }, []);

  // Node Collision Detection
  const getNodeAt = useCallback(
    (worldX: number, worldY: number) => {
      const nodes = nodesRef.current;
      const scale = nodeScaleRef.current;
      for (let i = nodes.length - 1; i >= 0; i--) {
        const n = nodes[i];
        const dx = worldX - n.x;
        const dy = worldY - n.y;
        const hitRadius = n.radius * scale + 6;
        if (dx * dx + dy * dy <= hitRadius * hitRadius) {
          return n;
        }
      }
      return null;
    },
    []
  );

  // Mouse Handlers
  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const world = screenToWorld(e.clientX, e.clientY);
    const hit = getNodeAt(world.x, world.y);

    if (hit) {
      draggedNodeRef.current = hit;
      dragStartPosRef.current = { x: world.x, y: world.y };
      alphaRef.current = 0.5; // Re-energize physics while dragging
    } else {
      isPanningRef.current = true;
      panStartRef.current = { x: e.clientX, y: e.clientY };
    }
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const world = screenToWorld(e.clientX, e.clientY);

    // If dragging a node
    if (draggedNodeRef.current) {
      draggedNodeRef.current.x = world.x;
      draggedNodeRef.current.y = world.y;
      draggedNodeRef.current.vx = 0;
      draggedNodeRef.current.vy = 0;
      alphaRef.current = Math.max(alphaRef.current, 0.4);
      return;
    }

    // If panning camera
    if (isPanningRef.current) {
      const dx = e.clientX - panStartRef.current.x;
      const dy = e.clientY - panStartRef.current.y;
      cameraRef.current.x += dx;
      cameraRef.current.y += dy;
      panStartRef.current = { x: e.clientX, y: e.clientY };
      return;
    }

    // Hover detection
    const hit = getNodeAt(world.x, world.y);
    if (hit !== hoveredNodeRef.current) {
      hoveredNodeRef.current = hit;
      setHoveredNode(hit);
      if (canvasRef.current) {
        canvasRef.current.style.cursor = hit ? "pointer" : "grab";
      }
    }
  };

  const handleMouseUp = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const world = screenToWorld(e.clientX, e.clientY);
    const hit = getNodeAt(world.x, world.y);

    if (draggedNodeRef.current) {
      const dx = world.x - dragStartPosRef.current.x;
      const dy = world.y - dragStartPosRef.current.y;
      if (Math.sqrt(dx * dx + dy * dy) < 4) {
        selectedNodeRef.current = draggedNodeRef.current;
        setSelectedNode(draggedNodeRef.current);
      }
      draggedNodeRef.current = null;
    } else if (isPanningRef.current) {
      isPanningRef.current = false;
      const dx = e.clientX - panStartRef.current.x;
      const dy = e.clientY - panStartRef.current.y;
      if (Math.sqrt(dx * dx + dy * dy) < 4 && !hit) {
        selectedNodeRef.current = null;
        setSelectedNode(null);
      }
    }
  };

  // Zoom on Mouse Wheel
  const handleWheel = (e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    const zoomFactor = e.deltaY < 0 ? 1.12 : 0.88;
    const currentZoom = cameraRef.current.zoom;
    const newZoom = Math.min(2.8, Math.max(0.25, currentZoom * zoomFactor));

    cameraRef.current.x = mouseX - (mouseX - cameraRef.current.x) * (newZoom / currentZoom);
    cameraRef.current.y = mouseY - (mouseY - cameraRef.current.y) * (newZoom / currentZoom);
    cameraRef.current.zoom = newZoom;
  };

  // Reset Center View
  const handleCenterView = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    cameraRef.current = {
      x: canvas.clientWidth / 2,
      y: canvas.clientHeight / 2,
      zoom: 0.95,
    };
    alphaRef.current = 0.6;
  };

  const handleToggleTheme = () => {
    const next = themeMode === "light" ? "dark" : "light";
    setThemeMode(next);
    document.documentElement.classList.toggle("dark", next === "dark");
    localStorage.setItem("contextos-theme", next);
    window.dispatchEvent(new CustomEvent("contextos-theme-change", { detail: { theme: next } }));
  };

  const handleZoomIn = () => {
    cameraRef.current.zoom = Math.min(2.8, cameraRef.current.zoom * 1.25);
  };

  const handleZoomOut = () => {
    cameraRef.current.zoom = Math.max(0.25, cameraRef.current.zoom * 0.8);
  };

  // Inspector Node Connections
  const nodeConnections = useMemo(() => {
    if (!selectedNode) return { incoming: [], outgoing: [] };
    const incoming = edgesRef.current.filter((e) => e.target === selectedNode.id);
    const outgoing = edgesRef.current.filter((e) => e.source === selectedNode.id);
    return { incoming, outgoing };
  }, [selectedNode]);

  return (
    <div className="space-y-4 max-w-7xl mx-auto h-[calc(100vh-100px)] flex flex-col font-sans">
      {/* Page Header (Consistent with All Screens) */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-2 border-b border-slate-200 dark:border-slate-800 shrink-0">
        <div>
          <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100 tracking-tight flex items-center space-x-2">
            <span>Context Graph Exploration</span>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-700">
              Obsidian Force Layout
            </span>
          </h1>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Interactive force-directed galaxy: drag nodes, inspect clusters, and trace multi-hop dependencies.
          </p>
        </div>

        {/* Top Header Actions */}
        <div className="flex items-center space-x-2">
          {/* Node/Edge Stats Pill */}
          <div className="text-xs font-mono text-slate-600 dark:text-slate-400 flex items-center space-x-2 bg-white dark:bg-slate-900 px-2.5 py-1 rounded border border-slate-200 dark:border-slate-800 shadow-xs">
            <span className="flex items-center space-x-1">
              <span className="w-2 h-2 rounded-full bg-emerald-500" />
              <span>Nodes: <strong className="text-slate-900 dark:text-slate-100">{rawNodes.length}</strong></span>
            </span>
            <span>•</span>
            <span>Links: <strong className="text-slate-900 dark:text-slate-100">{rawEdges.length}</strong></span>
          </div>

          {/* Theme Toggle (Light / Dark Obsidian) */}
          <button
            onClick={handleToggleTheme}
            className="p-1.5 border border-slate-200 dark:border-slate-750 bg-white dark:bg-slate-850 rounded text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800 shadow-xs flex items-center space-x-1 text-xs"
            title={`Switch to ${themeMode === "light" ? "Dark Obsidian" : "Bright"} theme`}
          >
            {themeMode === "light" ? (
              <>
                <Moon className="w-3.5 h-3.5 text-slate-500" />
                <span className="text-[11px] font-medium">Dark Mode</span>
              </>
            ) : (
              <>
                <Sun className="w-3.5 h-3.5 text-amber-500" />
                <span className="text-[11px] font-medium">Bright Mode</span>
              </>
            )}
          </button>

          {/* Physics Settings Button */}
          <button
            onClick={() => setShowSettings(!showSettings)}
            className={`px-2.5 py-1 text-xs border rounded transition-colors flex items-center space-x-1.5 shadow-xs font-medium ${
              showSettings
                ? "bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 border-slate-900 dark:border-slate-100"
                : "bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800"
            }`}
          >
            <Sliders className="w-3.5 h-3.5" />
            <span>Physics Controls</span>
          </button>
        </div>
      </div>

      {/* Main Graph Canvas Container (Framed with Theme Consistency) */}
      <div className="flex-1 relative border border-slate-200 dark:border-slate-800 rounded-xl overflow-hidden bg-white dark:bg-slate-900 shadow-xs min-h-0 flex">
        {/* Floating Controls Bar (Inside Canvas) */}
        <div className="absolute top-3 left-3 z-20 flex items-center space-x-2">
          {/* Search Box */}
          <div className="relative flex items-center bg-white/95 dark:bg-slate-800/95 backdrop-blur-md border border-slate-200 dark:border-slate-700 rounded-lg px-2.5 py-1.5 shadow-sm">
            <Search className="w-3.5 h-3.5 text-slate-400 mr-1.5" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search nodes..."
              className="bg-transparent text-xs text-slate-800 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none w-36 font-sans"
            />
            {searchTerm && (
              <button
                onClick={() => setSearchTerm("")}
                className="text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 ml-1"
              >
                ✕
              </button>
            )}
          </div>

          {/* Filter Dropdown */}
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="bg-white/95 dark:bg-slate-800/95 backdrop-blur-md border border-slate-200 dark:border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-700 dark:text-slate-200 focus:outline-none cursor-pointer shadow-sm"
          >
            <option value="ALL">All Categories</option>
            <option value="TABLE">Tables</option>
            <option value="TRANSFORMATION_MODEL">dbt Models</option>
            <option value="DASHBOARD">Dashboards</option>
            <option value="METRIC">Metrics</option>
            <option value="DOCUMENTATION">Docs</option>
            <option value="PULL_REQUEST">PRs</option>
            <option value="CHANNEL">Slack</option>
          </select>

          {/* Color Mode Toggle */}
          <div className="bg-white/95 dark:bg-slate-800/95 backdrop-blur-md border border-slate-200 dark:border-slate-700 rounded-lg p-0.5 shadow-sm flex text-[11px]">
            <button
              onClick={() => setColorMode("type")}
              className={`px-2 py-1 rounded font-medium transition-colors ${
                colorMode === "type"
                  ? "bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900"
                  : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100"
              }`}
            >
              By Type
            </button>
            <button
              onClick={() => setColorMode("status")}
              className={`px-2 py-1 rounded font-medium transition-colors ${
                colorMode === "status"
                  ? "bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900"
                  : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100"
              }`}
            >
              By Status
            </button>
          </div>
        </div>

        {/* Physics Controls Popover (Obsidian Style) */}
        {showSettings && (
          <div className="absolute top-14 left-3 z-30 w-72 bg-white/95 dark:bg-slate-850/95 backdrop-blur-xl border border-slate-200 dark:border-slate-750 rounded-xl p-4 shadow-xl space-y-3.5 text-xs animate-in fade-in duration-150 text-slate-700 dark:text-slate-200">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100 dark:border-slate-800">
              <span className="font-semibold text-slate-900 dark:text-slate-100 uppercase tracking-wider text-[11px] flex items-center space-x-1.5">
                <Sparkles className="w-3.5 h-3.5 text-sky-600 dark:text-sky-400" />
                <span>Obsidian Physics Forces</span>
              </span>
              <button
                onClick={() => setShowSettings(false)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 text-xs px-1"
              >
                ✕
              </button>
            </div>

            {/* Repulsion Force */}
            <div className="space-y-1">
              <div className="flex justify-between text-slate-500 dark:text-slate-400 text-[11px]">
                <span>Repulsion (Node Spread)</span>
                <span className="font-mono text-slate-800 dark:text-slate-200">{repulsion}</span>
              </div>
              <input
                type="range"
                min="80"
                max="500"
                value={repulsion}
                onChange={(e) => setRepulsion(parseInt(e.target.value))}
                className="w-full accent-slate-900 dark:accent-sky-500 cursor-pointer h-1 bg-slate-200 dark:bg-slate-700 rounded"
              />
            </div>

            {/* Link Distance */}
            <div className="space-y-1">
              <div className="flex justify-between text-slate-500 dark:text-slate-400 text-[11px]">
                <span>Link Distance (Springs)</span>
                <span className="font-mono text-slate-800 dark:text-slate-200">{linkDistance}px</span>
              </div>
              <input
                type="range"
                min="50"
                max="250"
                value={linkDistance}
                onChange={(e) => setLinkDistance(parseInt(e.target.value))}
                className="w-full accent-slate-900 dark:accent-sky-500 cursor-pointer h-1 bg-slate-200 dark:bg-slate-700 rounded"
              />
            </div>

            {/* Center Gravity */}
            <div className="space-y-1">
              <div className="flex justify-between text-slate-500 dark:text-slate-400 text-[11px]">
                <span>Center Gravity</span>
                <span className="font-mono text-slate-800 dark:text-slate-200">{gravity.toFixed(3)}</span>
              </div>
              <input
                type="range"
                min="0.01"
                max="0.1"
                step="0.005"
                value={gravity}
                onChange={(e) => setGravity(parseFloat(e.target.value))}
                className="w-full accent-slate-900 dark:accent-sky-500 cursor-pointer h-1 bg-slate-200 dark:bg-slate-700 rounded"
              />
            </div>

            {/* Node Size Scale */}
            <div className="space-y-1">
              <div className="flex justify-between text-slate-500 dark:text-slate-400 text-[11px]">
                <span>Node Scale</span>
                <span className="font-mono text-slate-800 dark:text-slate-200">{nodeScale.toFixed(1)}x</span>
              </div>
              <input
                type="range"
                min="0.6"
                max="2.0"
                step="0.1"
                value={nodeScale}
                onChange={(e) => setNodeScale(parseFloat(e.target.value))}
                className="w-full accent-slate-900 dark:accent-sky-500 cursor-pointer h-1 bg-slate-200 dark:bg-slate-700 rounded"
              />
            </div>

            {/* Show Labels Toggle */}
            <div className="pt-2 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
              <span className="text-[11px] text-slate-700 dark:text-slate-300">Display Text Labels</span>
              <input
                type="checkbox"
                checked={showLabels}
                onChange={(e) => setShowLabels(e.target.checked)}
                className="accent-slate-900 dark:accent-sky-500 cursor-pointer w-4 h-4 rounded"
              />
            </div>
          </div>
        )}

        {/* Bottom Left Zoom Controls */}
        <div className="absolute bottom-4 left-4 z-20 flex flex-col space-y-1 bg-white/95 dark:bg-slate-800/95 backdrop-blur-md border border-slate-200 dark:border-slate-700 rounded-lg p-1 shadow-md">
          <button
            onClick={handleZoomIn}
            title="Zoom In"
            className="p-1.5 hover:bg-slate-100 dark:hover:bg-slate-700 rounded text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white transition-colors"
          >
            <ZoomIn className="w-4 h-4" />
          </button>
          <button
            onClick={handleZoomOut}
            title="Zoom Out"
            className="p-1.5 hover:bg-slate-100 dark:hover:bg-slate-700 rounded text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white transition-colors"
          >
            <ZoomOut className="w-4 h-4" />
          </button>
          <div className="border-t border-slate-200 dark:border-slate-700 my-0.5" />
          <button
            onClick={handleCenterView}
            title="Center Graph"
            className="p-1.5 hover:bg-slate-100 dark:hover:bg-slate-700 rounded text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white transition-colors"
          >
            <Maximize2 className="w-4 h-4" />
          </button>
        </div>

        {/* Main Fullscreen HTML5 Force Simulation Canvas */}
        <canvas
          ref={canvasRef}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onWheel={handleWheel}
          className="w-full h-full cursor-grab active:cursor-grabbing block"
        />

        {/* Hover Tooltip (Light / Dark Card) */}
        {hoveredNode && !selectedNode && (
          <div className="pointer-events-none absolute bottom-4 left-24 z-30 bg-white/95 dark:bg-slate-800/95 backdrop-blur-md border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-1.5 shadow-md text-xs flex items-center space-x-2.5 animate-in fade-in duration-100">
            <div
              className="w-2.5 h-2.5 rounded-full"
              style={{
                backgroundColor:
                  colorMode === "status"
                    ? STATUS_COLORS[hoveredNode.certification_status] || "#64748b"
                    : TYPE_COLORS[hoveredNode.asset_type] || "#0284c7",
              }}
            />
            <div>
              <div className="font-bold text-slate-900 dark:text-slate-100">{hoveredNode.name}</div>
              <div className="text-[10px] font-mono text-slate-400">{hoveredNode.qualified_name}</div>
            </div>
            <span className="text-[10px] px-1.5 py-0.5 rounded font-mono bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-600">
              {hoveredNode.degree} links
            </span>
          </div>
        )}

        {/* Selected Node Details Drawer (Right Side Flyout) */}
        {selectedNode && (
          <div className="absolute top-3 right-3 bottom-3 z-40 w-80 bg-white/95 dark:bg-slate-850/95 backdrop-blur-xl border border-slate-200 dark:border-slate-750 rounded-xl p-4 shadow-xl flex flex-col space-y-3.5 overflow-y-auto animate-in fade-in slide-in-from-right-3 duration-150">
            {/* Header */}
            <div className="flex items-center justify-between pb-2 border-b border-slate-100 dark:border-slate-800">
              <div className="flex items-center space-x-2">
                <div
                  className="w-2.5 h-2.5 rounded-full"
                  style={{
                    backgroundColor:
                      colorMode === "status"
                        ? STATUS_COLORS[selectedNode.certification_status] || "#64748b"
                        : TYPE_COLORS[selectedNode.asset_type] || "#0284c7",
                  }}
                />
                <span className="text-[11px] font-mono font-semibold uppercase text-slate-500 dark:text-slate-400">
                  {selectedNode.asset_type.replace("_", " ")}
                </span>
              </div>
              <button
                onClick={() => setSelectedNode(null)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 text-xs px-1.5 py-0.5 rounded bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
              >
                ✕ Close
              </button>
            </div>

            {/* Node Identity */}
            <div className="space-y-0.5">
              <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100">{selectedNode.name}</h2>
              <div className="text-[10px] font-mono text-slate-400 break-all">
                {selectedNode.qualified_name}
              </div>
            </div>

            {/* Certification Badge & Owner */}
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="p-2.5 bg-slate-50 dark:bg-slate-800 rounded-lg border border-slate-100 dark:border-slate-700 space-y-1">
                <span className="text-slate-400 text-[10px] block">Certification</span>
                <span
                  className={`inline-block px-1.5 py-0.5 rounded font-mono font-semibold text-[10px] ${
                    selectedNode.certification_status === "CERTIFIED"
                      ? "bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800"
                      : selectedNode.certification_status === "DISPUTED"
                      ? "bg-rose-50 dark:bg-rose-950/60 text-rose-700 dark:text-rose-400 border border-rose-200 dark:border-rose-800"
                      : "bg-amber-50 dark:bg-amber-950/60 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-800"
                  }`}
                >
                  {selectedNode.certification_status}
                </span>
              </div>

              <div className="p-2.5 bg-slate-50 dark:bg-slate-800 rounded-lg border border-slate-100 dark:border-slate-700 space-y-1">
                <span className="text-slate-400 text-[10px] block">Owner</span>
                <span className="text-slate-800 dark:text-slate-200 font-medium text-[11px] block truncate">
                  {selectedNode.owner_name || "Unassigned"}
                </span>
              </div>
            </div>

            {/* Incoming Connections */}
            <div className="space-y-1.5 flex-1">
              <div className="text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                Incoming Dependencies ({nodeConnections.incoming.length})
              </div>
              {nodeConnections.incoming.length === 0 ? (
                <div className="text-slate-400 dark:text-slate-500 text-[11px] italic p-2 bg-slate-50 dark:bg-slate-800 rounded border border-slate-100 dark:border-slate-700">
                  Root origin source.
                </div>
              ) : (
                <div className="space-y-1 max-h-28 overflow-y-auto">
                  {nodeConnections.incoming.map((e) => (
                    <div
                      key={e.id}
                      className="p-1.5 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded text-xs space-y-0.5"
                    >
                      <div className="flex items-center justify-between text-[10px] text-slate-400">
                        <span className="font-mono text-sky-700 dark:text-sky-400 font-medium">{e.type}</span>
                        <span>From</span>
                      </div>
                      <div className="font-mono text-slate-800 dark:text-slate-200 text-[11px] truncate">{e.source}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Outgoing Connections */}
            <div className="space-y-1.5 flex-1">
              <div className="text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                Downstream Dependents ({nodeConnections.outgoing.length})
              </div>
              {nodeConnections.outgoing.length === 0 ? (
                <div className="text-slate-400 dark:text-slate-500 text-[11px] italic p-2 bg-slate-50 dark:bg-slate-800 rounded border border-slate-100 dark:border-slate-700">
                  Terminal consumer leaf.
                </div>
              ) : (
                <div className="space-y-1 max-h-28 overflow-y-auto">
                  {nodeConnections.outgoing.map((e) => (
                    <div
                      key={e.id}
                      className="p-1.5 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded text-xs space-y-0.5"
                    >
                      <div className="flex items-center justify-between text-[10px] text-slate-400">
                        <span className="font-mono text-purple-700 dark:text-purple-400 font-medium">{e.type}</span>
                        <span>To</span>
                      </div>
                      <div className="font-mono text-slate-800 dark:text-slate-200 text-[11px] truncate">{e.target}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Action Buttons */}
            <div className="pt-2 border-t border-slate-100 dark:border-slate-800 flex items-center space-x-2">
              <Link
                href={`/catalog?query=${encodeURIComponent(selectedNode.name)}`}
                className="flex-1 py-1.5 px-3 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 text-xs font-medium rounded text-center transition-colors flex items-center justify-center space-x-1 shadow-xs"
              >
                <span>Catalog</span>
                <ExternalLink className="w-3 h-3 text-slate-400" />
              </Link>
              <Link
                href={`/lineage?assetId=${encodeURIComponent(selectedNode.id)}`}
                className="flex-1 py-1.5 px-3 bg-slate-900 dark:bg-slate-100 hover:bg-slate-800 dark:hover:bg-white text-white dark:text-slate-900 text-xs font-medium rounded text-center transition-colors flex items-center justify-center space-x-1 shadow-xs"
              >
                <span>Lineage</span>
                <ArrowRight className="w-3 h-3 text-slate-300 dark:text-slate-600" />
              </Link>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
