"use client";

import { Clock, Truck } from "lucide-react";

interface ScheduleItem {
  vehicle: number;
  color: string;
  stops: string[];
  totalTime_min: number;
  timeline: Array<{ stopId: string; arrivalTime_s: number; isDepot: boolean }>;
}

export default function TimelineGantt({ schedules }: { schedules: ScheduleItem[] }) {
  if (!schedules || schedules.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-xs text-muted-foreground font-mono">
        No active dispatch sequences. Execute optimization to generate timelines.
      </div>
    );
  }

  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center justify-between pb-2 border-b border-border">
        <h3 className="text-xs uppercase tracking-wider font-mono font-medium flex items-center gap-2">
          <Clock className="h-4 w-4 text-primary" /> Vehicle Transit & Service Allocations
        </h3>
        <span className="text-[11px] text-muted-foreground font-mono">Service Window: 10m/stop</span>
      </div>

      <div className="space-y-3">
        {schedules.map((item) => (
          <div key={item.vehicle} className="space-y-1.5 bg-background/40 p-3 rounded-lg border border-border/50">
            <div className="flex justify-between items-center text-xs font-mono">
              <span className="flex items-center gap-2 font-medium" style={{ color: item.color }}>
                <Truck className="h-3.5 w-3.5" /> Vehicle #{item.vehicle}
              </span>
              <span className="text-muted-foreground">Est. Total: {item.totalTime_min} min</span>
            </div>

            <div className="flex items-center gap-1.5 overflow-x-auto py-1">
              {item.stops.map((stop, idx) => (
                <div key={idx} className="flex items-center gap-1 shrink-0">
                  <div
                    className="px-2.5 py-1 rounded text-[11px] font-mono font-medium border text-white shadow-xs"
                    style={{ backgroundColor: `${item.color}cc`, borderColor: item.color }}
                  >
                    {stop}
                  </div>
                  {idx < item.stops.length - 1 && (
                    <span className="text-muted-foreground/60 text-xs">→</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}