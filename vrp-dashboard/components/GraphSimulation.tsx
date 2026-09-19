"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Minus, Pause, Play, Plus, RotateCcw, Route, SlidersHorizontal, ZoomIn, ZoomOut } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Coordinate = [number, number];
type RouteCollection = GeoJSON.FeatureCollection<GeoJSON.LineString, Record<string, unknown>>;

type GraphEdge = GeoJSON.Feature<GeoJSON.LineString, {
  source: string;
  target: string;
  distance_m: number;
  travel_time_s: number;
  weight: number;
  weight_ratio: number;
  speed_kmh: number;
}>;

type GraphResponse = {
  bounds: [[number, number], [number, number]];
  stats: { nodes: number; edges: number };
  edges: GeoJSON.FeatureCollection<GeoJSON.LineString, GraphEdge["properties"]>;
};

type GraphSimulationProps = {
  activeCity: "salt-lake" | "manhattan";
  trafficMode: "simulated" | "live";
  trafficSeed: number;
  distanceWeight: number;
  routesGeoJSON: RouteCollection | null | undefined;
};

function isCoordinate(value: unknown): value is Coordinate {
  return Array.isArray(value)
    && value.length >= 2
    && typeof value[0] === "number"
    && typeof value[1] === "number"
    && Number.isFinite(value[0])
    && Number.isFinite(value[1]);
}

function pointAlongLine(points: Coordinate[], progress: number): Coordinate {
  if (points.length === 0) return [0, 0];
  if (points.length === 1) return points[0];
  const lengths = points.slice(1).map((point, index) => Math.hypot(
    point[0] - points[index][0], point[1] - points[index][1],
  ));
  const total = lengths.reduce((sum, value) => sum + value, 0);
  let remaining = Math.max(0, Math.min(1, progress)) * total;
  for (let index = 0; index < lengths.length; index += 1) {
    if (remaining <= lengths[index] || index === lengths.length - 1) {
      const ratio = lengths[index] === 0 ? 0 : remaining / lengths[index];
      return [
        points[index][0] + (points[index + 1][0] - points[index][0]) * ratio,
        points[index][1] + (points[index + 1][1] - points[index][1]) * ratio,
      ];
    }
    remaining -= lengths[index];
  }
  return points[points.length - 1];
}

function linePrefix(points: Coordinate[], progress: number): Coordinate[] {
  if (points.length < 2) return points;
  const clamped = Math.max(0, Math.min(1, progress));
  if (clamped <= 0) return [points[0], points[0]];
  if (clamped >= 1) return points;

  const lengths = points.slice(1).map((point, index) => Math.hypot(
    point[0] - points[index][0], point[1] - points[index][1],
  ));
  const total = lengths.reduce((sum, value) => sum + value, 0);
  let remaining = clamped * total;
  const prefix = [points[0]];

  for (let index = 0; index < lengths.length; index += 1) {
    if (remaining > lengths[index]) {
      prefix.push(points[index + 1]);
      remaining -= lengths[index];
      continue;
    }
    const ratio = lengths[index] === 0 ? 0 : remaining / lengths[index];
    prefix.push([
      points[index][0] + (points[index + 1][0] - points[index][0]) * ratio,
      points[index][1] + (points[index + 1][1] - points[index][1]) * ratio,
    ]);
    break;
  }
  return prefix;
}

function routePoints(route: GeoJSON.Feature<GeoJSON.LineString, Record<string, unknown>>): Coordinate[] {
  return route.geometry.coordinates.filter(isCoordinate) as Coordinate[];
}

export default function GraphSimulation({
  activeCity,
  trafficMode,
  trafficSeed,
  distanceWeight,
  routesGeoJSON,
}: GraphSimulationProps) {
  const [graph, setGraph] = useState<GraphResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [speed, setSpeed] = useState(1);
  const [isPlaying, setIsPlaying] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const animationRef = useRef<number | null>(null);
  const progressRef = useRef(0);
  const graphSvgRef = useRef<SVGSVGElement | null>(null);
  const dragRef = useRef<{ pointerId: number; x: number; y: number } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const loadGraph = async () => {
      setGraph(null);
      setError(null);
      setProgress(0);
      progressRef.current = 0;
      setIsPlaying(false);
      setPan({ x: 0, y: 0 });
      const params = new URLSearchParams({
        region: activeCity,
        traffic_mode: trafficMode,
        traffic_seed: String(trafficSeed),
        distance_weight: String(distanceWeight),
      });
      try {
        const response = await fetch(`${API_BASE_URL}/api/graph?${params.toString()}`, { signal: controller.signal });
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(body.detail || `Graph request failed: HTTP ${response.status}`);
        }
        setGraph(await response.json() as GraphResponse);
      } catch (reason: unknown) {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "Unable to load the regional graph");
      }
    };
    void loadGraph();
    return () => controller.abort();
  }, [activeCity, distanceWeight, trafficMode, trafficSeed]);

  useEffect(() => {
    progressRef.current = progress;
  }, [progress]);

  const routes = useMemo(
    () => routesGeoJSON?.features.filter((feature) => routePoints(feature).length > 1) ?? [],
    [routesGeoJSON],
  );

  useEffect(() => {
    if (!isPlaying) return;
    const startedAt = performance.now() - progressRef.current * 18000 / speed;
    const tick = (now: number) => {
      const next = Math.min(1, (now - startedAt) / (18000 / speed));
      setProgress(next);
      if (next < 1) animationRef.current = requestAnimationFrame(tick);
      else setIsPlaying(false);
    };
    animationRef.current = requestAnimationFrame(tick);
    return () => {
      if (animationRef.current !== null) cancelAnimationFrame(animationRef.current);
      animationRef.current = null;
    };
  }, [isPlaying, speed]);

  const project = (coordinate: Coordinate): Coordinate => {
    if (!graph) return [0, 0];
    const [[west, south], [east, north]] = graph.bounds;
    const x = ((coordinate[0] - west) / Math.max(0.00001, east - west)) * 1000;
    const y = (1 - (coordinate[1] - south) / Math.max(0.00001, north - south)) * 700;
    return [x, y];
  };

  const fluorescentRouteColors = ["#00e5ff", "#ffffff", "#60a5fa", "#c4b5fd", "#7dd3fc", "#f8fafc"];

  const startGraphDrag = (event: React.PointerEvent<SVGSVGElement>) => {
    if (event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY };
  };

  const moveGraphDrag = (event: React.PointerEvent<SVGSVGElement>) => {
    const drag = dragRef.current;
    const svg = graphSvgRef.current;
    if (!drag || !svg || drag.pointerId !== event.pointerId) return;
    const rect = svg.getBoundingClientRect();
    const scaleX = 1000 / Math.max(1, rect.width);
    const scaleY = 700 / Math.max(1, rect.height);
    setPan((current) => ({
      x: current.x + (event.clientX - drag.x) * scaleX / zoom,
      y: current.y + (event.clientY - drag.y) * scaleY / zoom,
    }));
    dragRef.current = { pointerId: drag.pointerId, x: event.clientX, y: event.clientY };
  };

  const stopGraphDrag = (event: React.PointerEvent<SVGSVGElement>) => {
    if (dragRef.current?.pointerId === event.pointerId) dragRef.current = null;
  };

  return (
    <div className="absolute inset-0 overflow-hidden bg-[#1a1a1a] text-foreground">
      <div className="absolute inset-0 opacity-90">
        {graph ? (
          <svg
            viewBox="0 0 1000 700"
            ref={graphSvgRef}
            className="h-full w-full touch-none cursor-grab active:cursor-grabbing"
            role="img"
            aria-label="Weighted regional road graph"
            onPointerDown={startGraphDrag}
            onPointerMove={moveGraphDrag}
            onPointerUp={stopGraphDrag}
            onPointerCancel={stopGraphDrag}
            onWheel={(event) => {
              event.preventDefault();
              setZoom((value) => Math.max(0.75, Math.min(4, value + (event.deltaY < 0 ? 0.15 : -0.15))));
            }}
          >
            <rect width="1000" height="700" fill="#1a1a1a" />
            <g transform={`translate(${500 + pan.x} ${350 + pan.y}) scale(${zoom}) translate(-500 -350)`}>
              {graph.edges.features.map((edge, index) => {
                const points = edge.geometry.coordinates.filter(isCoordinate).map(project);
                return (
                  <polyline
                    key={`${edge.properties.source}-${edge.properties.target}-${index}`}
                    points={points.map(([x, y]) => `${x},${y}`).join(" ")}
                    fill="none"
                    stroke="#ffffff"
                    strokeWidth={(0.65 + edge.properties.weight_ratio * 1.15) / Math.max(1, zoom * 1.15)}
                    strokeOpacity={0.12 + edge.properties.weight_ratio * 0.78}
                  />
                );
              })}
              {routes.map((route, index) => {
                const points = routePoints(route).map(project);
                const traveledPoints = linePrefix(routePoints(route), progress).map(project);
                const color = fluorescentRouteColors[index % fluorescentRouteColors.length];
                const vehiclePosition = project(pointAlongLine(routePoints(route), progress));
                return (
                  <g key={`simulation-route-${index}`}>
                    <polyline
                      points={points.map(([x, y]) => `${x},${y}`).join(" ")}
                      fill="none"
                      stroke={color}
                      strokeWidth={8 / Math.max(1, Math.sqrt(zoom))}
                      strokeOpacity={0.2}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                    <polyline
                      points={traveledPoints.map(([x, y]) => `${x},${y}`).join(" ")}
                      fill="none"
                      stroke={color}
                      strokeWidth={1.5 / Math.max(1, Math.sqrt(zoom))}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                    <circle cx={vehiclePosition[0]} cy={vehiclePosition[1]} r={8 / Math.max(1, Math.sqrt(zoom))} fill={color} fillOpacity="0.3" />
                    <circle cx={vehiclePosition[0]} cy={vehiclePosition[1]} r={5 / Math.max(1, Math.sqrt(zoom))} fill={color} stroke="#ffffff" strokeWidth={2 / Math.max(1, Math.sqrt(zoom))} />
                  </g>
                );
              })}
            </g>
          </svg>
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            {error ? "Unable to load regional graph" : "Loading regional road graph…"}
          </div>
        )}
      </div>

      <div className="pointer-events-none absolute inset-x-0 top-0 flex justify-between gap-4 p-4 sm:p-6">
        <div className="pointer-events-auto max-w-xl rounded-xl border border-border/80 bg-card/90 p-4 shadow-2xl backdrop-blur-xl">
          <div className="flex items-center gap-3">
            <div className="flex size-9 items-center justify-center rounded-lg bg-primary text-primary-foreground"><Route className="size-4" /></div>
            <div>
              <div className="text-sm font-semibold">Regional routing graph</div>
              <div className="text-xs text-muted-foreground">Weighted road network · {activeCity === "salt-lake" ? "Salt Lake Sector V" : "Manhattan"}</div>
            </div>
            <Badge variant="outline" className="ml-2 font-mono text-[10px]">{graph ? `${graph.stats.edges.toLocaleString()} edges` : "loading"}</Badge>
          </div>
          {error && <p className="mt-3 text-xs text-destructive">{error}</p>}
        </div>
        <div className="pointer-events-auto hidden w-56 rounded-xl border border-border/80 bg-card/90 p-3 text-xs shadow-2xl backdrop-blur-xl sm:block">
          <div className="mb-2 font-medium">Edge weight</div>
          <div className="h-2 rounded-full bg-gradient-to-r from-white/15 via-white/55 to-white" />
          <div className="mt-1 flex justify-between font-mono text-[10px] text-muted-foreground"><span>low</span><span>high</span></div>
          <p className="mt-2 leading-relaxed text-muted-foreground">Travel time plus the selected distance penalty.</p>
        </div>
      </div>

      <div className="absolute inset-x-0 bottom-0 flex justify-center p-4 sm:p-6">
        <div className="flex w-[min(48rem,calc(100vw-2rem))] items-center gap-2 rounded-xl border border-border/80 bg-card/95 p-3 shadow-2xl backdrop-blur-xl">
          <div className="flex items-center gap-1 rounded-md border border-border bg-background/70 p-0.5">
            <Button size="icon-sm" variant="ghost" onClick={() => setZoom((value) => Math.min(4, value + 0.25))} aria-label="Zoom in graph">
              <Plus className="size-3.5" />
            </Button>
            <Button size="icon-sm" variant="ghost" onClick={() => setZoom((value) => Math.max(0.75, value - 0.25))} aria-label="Zoom out graph">
              <Minus className="size-3.5" />
            </Button>
            <Button size="icon-sm" variant="ghost" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }} aria-label="Reset graph zoom and position" title="Reset graph zoom and position">
              {zoom >= 1 ? <ZoomOut className="size-3.5" /> : <ZoomIn className="size-3.5" />}
            </Button>
          </div>
          <Badge variant="outline" className="font-mono text-[10px]">{Math.round(zoom * 100)}%</Badge>
          <Button size="sm" variant="secondary" onClick={() => setIsPlaying((playing) => !playing)} disabled={routes.length === 0}>
            {isPlaying ? <Pause className="mr-1.5 size-3.5" /> : <Play className="mr-1.5 size-3.5" />}
            {isPlaying ? "Pause simulation" : "Play simulation"}
          </Button>
          <Button size="icon-sm" variant="ghost" onClick={() => { setIsPlaying(false); setProgress(0); }} aria-label="Reset graph simulation">
            <RotateCcw className="size-3.5" />
          </Button>
          <SlidersHorizontal className="ml-1 size-3.5 text-muted-foreground" />
          <input
            aria-label="Graph simulation progress"
            className="min-w-0 flex-1 accent-[var(--primary)]"
            type="range"
            min="0"
            max="1"
            step="0.001"
            value={progress}
            onChange={(event) => { setIsPlaying(false); setProgress(Number(event.target.value)); }}
          />
          <div className="flex items-center gap-1 rounded-md border border-border bg-background/60 p-0.5">
            {[1, 2, 4].map((value) => (
              <button key={value} type="button" onClick={() => setSpeed(value)} className={`rounded px-2 py-1 text-[10px] font-mono ${speed === value ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"}`}>{value}×</button>
            ))}
          </div>
          <Badge variant="outline" className="font-mono text-[10px]">{Math.round(progress * 100)}%</Badge>
        </div>
      </div>
    </div>
  );
}
