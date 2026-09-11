"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import dynamic from "next/dynamic";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { 
  Truck, Play, RefreshCw, Cpu, AlertCircle, Fuel, Leaf, 
  IndianRupee, TrendingDown, Layers, CalendarDays, Table as TableIcon, MapPin 
} from "lucide-react";
import TimelineGantt from "@/components/TimelineGantt";

const MapViewport = dynamic(
  () => import("@/components/MapViewport").then((mod) => mod.default),
  { ssr: false }
);

export default function VRPDashboard() {
  // Sidebar Resize State
  const [sidebarWidth, setSidebarWidth] = useState(480);
  const [isResizing, setIsResizing] = useState(false);

  const [placeName, setPlaceName] = useState("Salt Lake, Kolkata, India");
  const [customersN, setCustomersN] = useState<number[]>([10]);
  const [vehicles, setVehicles] = useState<number[]>([4]);
  const [capacity, setCapacity] = useState<number[]>([25]);

  const [trafficMode, setTrafficMode] = useState("simulated");
  const [trafficSeed, setTrafficSeed] = useState(42);

  const [distanceWeight, setDistanceWeight] = useState<number[]>([0.2]);
  const [particles, setParticles] = useState<number[]>([40]);
  const [iterations, setIterations] = useState<number[]>([100]);
  const [inspectAlgo, setInspectAlgo] = useState("QPSO");

  const [isSolving, setIsSolving] = useState(false);
  const [results, setResults] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  // Resize Handlers
  const startResizing = useCallback(() => setIsResizing(true), []);
  const stopResizing = useCallback(() => setIsResizing(false), []);
  const resize = useCallback((e: MouseEvent) => {
    if (isResizing) {
      const newWidth = e.clientX;
      if (newWidth >= 320 && newWidth <= 800) setSidebarWidth(newWidth);
    }
  }, [isResizing]);

  useEffect(() => {
    if (isResizing) {
      window.addEventListener("mousemove", resize);
      window.addEventListener("mouseup", stopResizing);
    }
    return () => {
      window.removeEventListener("mousemove", resize);
      window.removeEventListener("mouseup", stopResizing);
    };
  }, [isResizing, resize, stopResizing]);

  const safeSetArray = (val: number | number[], setter: (v: number[]) => void) => {
    setter(Array.isArray(val) ? val : [val]);
  };

  const runSolver = async () => {
    setIsSolving(true);
    setError(null);
    try {
      const response = await fetch("http://localhost:8000/api/optimize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          place_name: placeName,
          customers_n: customersN[0] ?? 10,
          num_vehicles: vehicles[0] ?? 4,
          vehicle_capacity: capacity[0] ?? 25,
          distance_weight: distanceWeight[0] ?? 0.2,
          particles: particles[0] ?? 40,
          iterations: iterations[0] ?? 100,
          traffic_mode: trafficMode,
          traffic_seed: trafficSeed,
        }),
      });

      if (!response.ok) throw new Error(`Optimization failed: HTTP ${response.status}`);
      const data = await response.json();
      setResults(data);
    } catch (err: any) {
      setError(err.message || "Failed to reach FastAPI optimization engine.");
    } finally {
      setIsSolving(false);
    }
  };

  const chartData = results?.algorithms?.QPSO?.history?.map((qpsoCost: number, idx: number) => ({
    iteration: idx + 1,
    QPSO: Number(qpsoCost.toFixed(1)),
    GA: Number(results.algorithms.GA.history[idx]?.toFixed(1) || null),
    "A* Baseline": Number(results.algorithms["A*"].score.toFixed(1)),
  }));

  return (
    <div className="flex h-screen w-screen bg-background text-foreground overflow-hidden font-sans select-none">
      <style dangerouslySetInnerHTML={{__html: `
        .custom-scrollbar::-webkit-scrollbar { width: 6px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: #3f3f46; border-radius: 10px; }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #52525b; }
      `}} />
      
      {/* Resizable Sidebar */}
      <aside 
        style={{ width: `${sidebarWidth}px` }}
        className="relative h-full flex flex-col border-r border-border bg-card/30 backdrop-blur-md z-10 shrink-0"
      >
        <header className="px-6 py-5 border-b border-border bg-background/50">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-primary/10 text-primary border border-primary/20">
                <Truck className="h-5 w-5" />
              </div>
              <div>
                <h1 className="scroll-m-20 text-xl font-semibold tracking-tight">QPSO Dispatch Platform</h1>
                <p className="text-sm text-muted-foreground leading-none mt-1">Enterprise Route Optimizer</p>
              </div>
            </div>
            <Badge variant="outline" className="font-mono text-[10px]">v2.0.1</Badge>
          </div>
        </header>

        {/* Native overflow-y-auto to fix ScrollArea clipping */}
        <div className="flex-1 overflow-y-auto overflow-x-hidden p-6 custom-scrollbar">
          <div className="space-y-8 pb-12">
            
            <section className="space-y-4">
              <h2 className="scroll-m-20 border-b border-border/50 pb-2 text-sm font-semibold tracking-tight uppercase text-muted-foreground">
                1. Environment
              </h2>
              <div className="space-y-2">
                <Label htmlFor="location" className="text-xs font-medium leading-none">OSM Location</Label>
                <div className="relative">
                  <MapPin className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                  <Input 
                    id="location" 
                    value={placeName} 
                    onChange={(e) => setPlaceName(e.target.value)} 
                    className="pl-9 h-9 text-sm font-medium"
                  />
                </div>
              </div>

              <div className="space-y-3 pt-2">
                <div className="flex justify-between items-center">
                  <Label className="text-xs font-medium leading-none">Delivery Stops</Label>
                  <span className="text-sm font-bold font-mono text-primary">{customersN[0] ?? 10} stops</span>
                </div>
                <Slider 
                  value={customersN} 
                  onValueChange={(v) => safeSetArray(v, setCustomersN)} 
                  min={4} max={40} step={1} 
                  className="cursor-grab active:cursor-grabbing"
                />
              </div>

              <div className="grid grid-cols-2 gap-4 pt-2">
                <div className="space-y-3">
                  <div className="flex justify-between items-center">
                    <Label className="text-xs font-medium leading-none">Fleet Size</Label>
                    <span className="text-sm font-bold font-mono text-primary">{vehicles[0] ?? 4} units</span>
                  </div>
                  <Slider 
                    value={vehicles} 
                    onValueChange={(v) => safeSetArray(v, setVehicles)} 
                    min={1} max={10} step={1} 
                    className="cursor-grab active:cursor-grabbing"
                  />
                </div>
                <div className="space-y-3">
                  <div className="flex justify-between items-center">
                    <Label className="text-xs font-medium leading-none">Capacity</Label>
                    <span className="text-sm font-bold font-mono text-primary">{capacity[0] ?? 25} items</span>
                  </div>
                  <Slider 
                    value={capacity} 
                    onValueChange={(v) => safeSetArray(v, setCapacity)} 
                    min={5} max={50} step={1} 
                    className="cursor-grab active:cursor-grabbing"
                  />
                </div>
              </div>
            </section>

            <section className="space-y-4">
              <h2 className="scroll-m-20 border-b border-border/50 pb-2 text-sm font-semibold tracking-tight uppercase text-muted-foreground">
                2. Traffic Engine
              </h2>
              <RadioGroup value={trafficMode} onValueChange={setTrafficMode} className="flex flex-col gap-2.5">
                <div className="flex items-center space-x-2 border border-border/50 p-2.5 rounded-md bg-background/50">
                  <RadioGroupItem value="simulated" id="simulated" />
                  <Label htmlFor="simulated" className="text-sm font-medium leading-none cursor-pointer">Simulated (Seeded)</Label>
                </div>
                <div className="flex items-center space-x-2 border border-border/50 p-2.5 rounded-md bg-background/50">
                  <RadioGroupItem value="live" id="live" />
                  <Label htmlFor="live" className="text-sm font-medium leading-none cursor-pointer text-muted-foreground">Live Traffic API (Mock)</Label>
                </div>
              </RadioGroup>
              {trafficMode === "simulated" && (
                <div className="space-y-2 pt-1">
                  <Label htmlFor="seed" className="text-xs font-medium leading-none">Stochastic Seed</Label>
                  <Input 
                    id="seed" 
                    type="number" 
                    value={trafficSeed} 
                    onChange={(e) => setTrafficSeed(Number(e.target.value))} 
                    className="h-9 font-mono text-sm"
                  />
                </div>
              )}
            </section>

            <section className="space-y-4">
              <h2 className="scroll-m-20 border-b border-border/50 pb-2 text-sm font-semibold tracking-tight uppercase text-muted-foreground">
                3. Optimization Engine
              </h2>
              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <Label className="text-xs font-medium leading-none">Distance Penalty (β)</Label>
                  <span className="text-sm font-bold font-mono text-primary">{(distanceWeight[0] ?? 0.2).toFixed(2)}</span>
                </div>
                <Slider 
                  value={distanceWeight} 
                  onValueChange={(v) => safeSetArray(v, setDistanceWeight)} 
                  min={0} max={1} step={0.05} 
                  className="cursor-grab active:cursor-grabbing"
                />
              </div>

              <div className="grid grid-cols-2 gap-4 pt-2">
                <div className="space-y-3">
                  <div className="flex justify-between items-center">
                    <Label className="text-xs font-medium leading-none text-muted-foreground">Swarm Size</Label>
                    <span className="text-xs font-bold font-mono">{particles[0] ?? 40}</span>
                  </div>
                  <Slider 
                    value={particles} 
                    onValueChange={(v) => safeSetArray(v, setParticles)} 
                    min={10} max={100} step={10} 
                    className="cursor-grab active:cursor-grabbing"
                  />
                </div>
                <div className="space-y-3">
                  <div className="flex justify-between items-center">
                    <Label className="text-xs font-medium leading-none text-muted-foreground">Iterations</Label>
                    <span className="text-xs font-bold font-mono">{iterations[0] ?? 100}</span>
                  </div>
                  <Slider 
                    value={iterations} 
                    onValueChange={(v) => safeSetArray(v, setIterations)} 
                    min={20} max={300} step={20} 
                    className="cursor-grab active:cursor-grabbing"
                  />
                </div>
              </div>
            </section>

            {/* Restored UI Feature: Inspect Algorithm Toggle */}
            {results && (
              <section className="space-y-4 animate-in fade-in slide-in-from-bottom-2">
                <h2 className="scroll-m-20 border-b border-border/50 pb-2 text-sm font-semibold tracking-tight uppercase text-muted-foreground">
                  4. Inspect Algorithm
                </h2>
                <RadioGroup value={inspectAlgo} onValueChange={setInspectAlgo} className="grid grid-cols-3 gap-2">
                  {['QPSO', 'GA', 'A*'].map((algo) => (
                    <div key={algo} className={`flex items-center space-x-2 border p-2 rounded-md justify-center transition-colors ${inspectAlgo === algo ? 'border-primary/50 bg-primary/10' : 'border-border/50 bg-background/50'}`}>
                      <RadioGroupItem value={algo} id={algo} className="hidden" />
                      <Label htmlFor={algo} className={`text-xs font-bold cursor-pointer ${inspectAlgo === algo ? 'text-primary' : 'text-muted-foreground'}`}>{algo}</Label>
                    </div>
                  ))}
                </RadioGroup>
              </section>
            )}

            <Button 
              onClick={runSolver} 
              disabled={isSolving}
              className="w-full h-11 text-sm font-medium tracking-wide shadow-sm transition-all"
            >
              {isSolving ? (
                <><RefreshCw className="mr-2 h-4 w-4 animate-spin" /> Ingesting GIS & Solving...</>
              ) : (
                <><Play className="mr-2 h-4 w-4 fill-current" /> Initialize Dispatch Sequence</>
              )}
            </Button>

            {error && (
              <div className="flex items-center gap-2 p-3 text-sm bg-destructive/10 border border-destructive/20 text-destructive rounded-lg">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span className="leading-tight">{error}</span>
              </div>
            )}
          </div>
        </div>

        {/* Dynamic Edge Resizer Handle */}
        <div 
          className="absolute top-0 right-0 w-1.5 h-full cursor-col-resize bg-transparent hover:bg-primary/50 transition-colors z-50"
          onMouseDown={startResizing}
        />
      </aside>

      <main className="flex-1 relative h-full flex flex-col bg-zinc-950">
        
        {results && (
          <div className="absolute top-4 left-4 z-20 flex gap-3">
            <Card className="p-3.5 border-border/40 bg-background/80 backdrop-blur-md shadow-lg flex items-center gap-4">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wider text-emerald-500 mb-0.5">Op Savings</p>
                <p className="text-xl font-bold font-mono leading-none tracking-tight">₹{results.business_impact.rupees_saved}</p>
              </div>
              <div className="h-8 w-px bg-border"></div>
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wider text-blue-400 mb-0.5">Fuel Cut</p>
                <p className="text-xl font-bold font-mono leading-none tracking-tight">{results.business_impact.liters_saved}<span className="text-sm font-normal text-muted-foreground ml-0.5">L</span></p>
              </div>
              <div className="h-8 w-px bg-border"></div>
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wider text-primary mb-0.5">Path Saved</p>
                <p className="text-xl font-bold font-mono leading-none tracking-tight">{results.business_impact.distance_saved_km}<span className="text-sm font-normal text-muted-foreground ml-0.5">km</span></p>
              </div>
            </Card>
          </div>
        )}

        <Tabs defaultValue="spatial" className="h-full flex flex-col relative">
          <div className="absolute top-4 right-4 z-20">
            <TabsList className="bg-background/80 backdrop-blur-md border border-border shadow-lg">
              <TabsTrigger value="spatial" className="text-xs font-medium gap-1.5"><Layers className="h-3.5 w-3.5" /> Spatial GIS</TabsTrigger>
              <TabsTrigger value="temporal" className="text-xs font-medium gap-1.5"><CalendarDays className="h-3.5 w-3.5" /> Gantt Schedule</TabsTrigger>
              <TabsTrigger value="benchmarks" className="text-xs font-medium gap-1.5"><TableIcon className="h-3.5 w-3.5" /> Benchmarks</TabsTrigger>
            </TabsList>
          </div>

          <TabsContent value="spatial" className="m-0 h-full w-full flex-1 relative">
            <div className="absolute inset-0">
              <MapViewport 
                routesGeoJSON={results?.routes} 
                customers={results?.locations?.customers || []} 
                depot={results?.locations?.depot || { id: "D", lat: 0, lng: 0 }} 
                activeLocation={placeName}
              />
            </div>
          </TabsContent>

          <TabsContent value="temporal" className="m-0 h-full w-full flex-1 bg-zinc-950 p-6 overflow-y-auto pt-20">
            <div className="max-w-4xl mx-auto">
              <TimelineGantt schedules={results?.schedules || []} />
            </div>
          </TabsContent>

          <TabsContent value="benchmarks" className="m-0 h-full w-full flex-1 bg-zinc-950 p-6 overflow-y-auto pt-20">
            <div className="max-w-4xl mx-auto space-y-6">
              <Card className="border-border/50 bg-card/30">
                <CardHeader className="pb-3">
                  <CardTitle className="text-lg font-semibold tracking-tight">Academic / Technical Proof</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="rounded-md border border-border/50">
                    <Table>
                      <TableHeader className="bg-muted/50">
                        <TableRow>
                          <TableHead className="font-semibold text-foreground">Methodology</TableHead>
                          <TableHead className="text-right font-semibold text-foreground">Total Cost</TableHead>
                          <TableHead className="text-right font-semibold text-foreground">Distance</TableHead>
                          <TableHead className="text-right font-semibold text-foreground">Travel Time</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {results ? (
                          <>
                            <TableRow>
                              <TableCell className="font-medium">QPSO (Quantum Swarm)</TableCell>
                              <TableCell className="text-right font-mono text-emerald-400">{results.algorithms.QPSO.score.toFixed(2)}</TableCell>
                              <TableCell className="text-right font-mono">{results.algorithms.QPSO.distance_km.toFixed(2)} km</TableCell>
                              <TableCell className="text-right font-mono">{results.algorithms.QPSO.travel_time_min.toFixed(1)} min</TableCell>
                            </TableRow>
                            <TableRow>
                              <TableCell className="font-medium">Genetic Algorithm</TableCell>
                              <TableCell className="text-right font-mono">{results.algorithms.GA.score.toFixed(2)}</TableCell>
                              <TableCell className="text-right font-mono">{results.algorithms.GA.distance_km.toFixed(2)} km</TableCell>
                              <TableCell className="text-right font-mono">{results.algorithms.GA.travel_time_min.toFixed(1)} min</TableCell>
                            </TableRow>
                            <TableRow>
                              <TableCell className="font-medium text-muted-foreground">A* Constructive Baseline</TableCell>
                              <TableCell className="text-right font-mono text-muted-foreground">{results.algorithms["A*"].score.toFixed(2)}</TableCell>
                              <TableCell className="text-right font-mono text-muted-foreground">{results.algorithms["A*"].distance_km.toFixed(2)} km</TableCell>
                              <TableCell className="text-right font-mono text-muted-foreground">{results.algorithms["A*"].travel_time_min.toFixed(1)} min</TableCell>
                            </TableRow>
                          </>
                        ) : (
                          <TableRow>
                            <TableCell colSpan={4} className="h-24 text-center text-sm text-muted-foreground">
                              Initialize dispatch sequence to generate metrics.
                            </TableCell>
                          </TableRow>
                        )}
                      </TableBody>
                    </Table>
                  </div>
                </CardContent>
              </Card>

              <Card className="border-border/50 bg-card/30 h-[400px] flex flex-col">
                <CardHeader className="pb-2">
                  <CardTitle className="text-lg font-semibold tracking-tight">Engine Convergence</CardTitle>
                </CardHeader>
                <CardContent className="flex-1 w-full p-4 pt-0">
                  {chartData ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={chartData} margin={{ top: 20, right: 20, left: 0, bottom: 0 }}>
                        <XAxis dataKey="iteration" stroke="#71717a" fontSize={12} tickLine={false} />
                        <YAxis stroke="#71717a" fontSize={12} tickLine={false} domain={["auto", "auto"]} />
                        <Tooltip 
                          contentStyle={{ backgroundColor: "#09090b", borderColor: "#27272a", borderRadius: "8px" }} 
                          labelStyle={{ color: "#a1a1aa", marginBottom: "4px", fontSize: "12px" }}
                          itemStyle={{ fontSize: "13px", fontFamily: "monospace", fontWeight: 600 }}
                        />
                        <Legend wrapperStyle={{ paddingTop: "20px", fontSize: "13px" }} />
                        <Line name="QPSO" type="monotone" dataKey="QPSO" stroke="#D90429" strokeWidth={3} dot={false} />
                        <Line name="Genetic Algo" type="monotone" dataKey="GA" stroke="#F4A261" strokeWidth={2} dot={false} />
                        <Line name="A* Baseline" type="stepAfter" dataKey="A* Baseline" stroke="#71717a" strokeWidth={2} strokeDasharray="5 5" dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
                      Awaiting sequence execution
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
}