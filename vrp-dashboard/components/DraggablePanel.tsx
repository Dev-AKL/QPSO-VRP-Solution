"use client";

import { useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";
import { GripVertical } from "lucide-react";
import { cn } from "cn";

interface DraggablePanelProps {
  children: ReactNode;
  label: string;
  initialPosition?: { x: number; y: number };
  className?: string;
}

interface DragState {
  pointerId: number;
  startX: number;
  startY: number;
  originX: number;
  originY: number;
}

/** A bounded, pointer-friendly floating panel for map/dashboard controls. */
export default function DraggablePanel({
  children,
  label,
  initialPosition = { x: 16, y: 16 },
  className,
}: DraggablePanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const dragStateRef = useRef<DragState | null>(null);
  const [position, setPosition] = useState(initialPosition);

  const handlePointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || !panelRef.current) return;
    const panel = panelRef.current;
    const offsetParent = panel.offsetParent as HTMLElement | null;
    const parentRect = offsetParent?.getBoundingClientRect();
    const panelRect = panel.getBoundingClientRect();

    dragStateRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: panelRect.left - (parentRect?.left ?? 0),
      originY: panelRect.top - (parentRect?.top ?? 0),
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const handlePointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragStateRef.current;
    const panel = panelRef.current;
    if (!drag || !panel || drag.pointerId !== event.pointerId) return;

    const offsetParent = panel.offsetParent as HTMLElement | null;
    const maxX = Math.max(0, (offsetParent?.clientWidth ?? window.innerWidth) - panel.offsetWidth - 8);
    const maxY = Math.max(0, (offsetParent?.clientHeight ?? window.innerHeight) - panel.offsetHeight - 8);
    setPosition({
      x: Math.max(8, Math.min(maxX, drag.originX + event.clientX - drag.startX)),
      y: Math.max(8, Math.min(maxY, drag.originY + event.clientY - drag.startY)),
    });
  };

  const stopDragging = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (dragStateRef.current?.pointerId === event.pointerId) {
      dragStateRef.current = null;
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
    }
  };

  return (
    <div
      ref={panelRef}
      className={cn("absolute z-30 max-w-[calc(100vw-1rem)]", className)}
      style={{ left: `${position.x}px`, top: `${position.y}px` }}
    >
      <div
        role="toolbar"
        aria-label={`Move ${label}`}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={stopDragging}
        onPointerCancel={stopDragging}
        className="flex cursor-grab touch-none select-none items-center gap-1.5 border-b border-border/70 px-2.5 py-1.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground active:cursor-grabbing"
      >
        <GripVertical className="size-3.5 shrink-0" />
        <span>{label}</span>
        <span className="ml-auto normal-case tracking-normal text-muted-foreground/60">drag to move</span>
      </div>
      {children}
    </div>
  );
}
