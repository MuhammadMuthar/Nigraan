"use client";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), { ssr: false });

type GNode = { id: string; kind: string; label: string };
type GEdge = { source: string; target: string };

const COLORS: Record<string, string> = {
  vendor: "#0f766e", employee: "#b91c1c", user: "#7c3aed", bank: "#52525b", phone: "#52525b", address: "#52525b", cnic: "#52525b",
};
const KIND_LABEL: Record<string, string> = { bank: "Bank", phone: "Phone", address: "Address", cnic: "CNIC" };

/** Relationship graph around a vendor; the suspicious path is highlighted. */
export function GraphView({ nodes, edges, path, height = 340 }: { nodes: GNode[]; edges: GEdge[]; path: string[]; height?: number }) {
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(600);
  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setWidth(el.clientWidth));
    ro.observe(el);
    setWidth(el.clientWidth);
    return () => ro.disconnect();
  }, []);
  const onPath = useMemo(() => new Set(path), [path]);
  const data = useMemo(() => ({
    nodes: nodes.map((n) => ({ ...n })),
    links: edges.map((e) => ({ ...e, hot: onPath.has(e.source) && onPath.has(e.target) })),
  }), [nodes, edges, onPath]);

  if (nodes.length === 0) return <div className="py-10 text-center text-sm text-muted-foreground">No shared identifiers found for this vendor.</div>;
  return (
    <div ref={wrap} className="overflow-hidden rounded-md border border-border bg-[#fbfbfc]">
      <ForceGraph2D
        graphData={data}
        width={width}
        height={height}
        cooldownTicks={80}
        nodeRelSize={5}
        linkColor={(l: object) => ((l as { hot?: boolean }).hot ? "#b91c1c" : "#d4d4d8")}
        linkWidth={(l: object) => ((l as { hot?: boolean }).hot ? 2.5 : 1)}
        nodeCanvasObject={(obj: object, ctx: CanvasRenderingContext2D, scale: number) => {
          const node = obj as GNode & { x?: number; y?: number };
          const hot = onPath.has(node.id);
          const isEntity = ["vendor", "employee", "user"].includes(node.kind);
          const r = isEntity ? 7 : 4.5;
          ctx.beginPath();
          ctx.arc(node.x ?? 0, node.y ?? 0, r, 0, 2 * Math.PI);
          ctx.fillStyle = COLORS[node.kind] ?? "#71717a";
          ctx.globalAlpha = hot || isEntity ? 1 : 0.55;
          ctx.fill();
          if (hot) {
            ctx.lineWidth = 2 / scale;
            ctx.strokeStyle = "#b91c1c";
            ctx.stroke();
          }
          ctx.globalAlpha = 1;
          const label = isEntity ? node.label : `${KIND_LABEL[node.kind] ?? node.kind}: ${node.label}`;
          const fs = Math.max(10 / scale, 2.5);
          ctx.font = `${hot ? "600 " : ""}${fs}px Inter, sans-serif`;
          ctx.fillStyle = hot ? "#18181b" : "#52525b";
          ctx.textAlign = "center";
          ctx.fillText(label.length > 42 ? label.slice(0, 40) + "…" : label, node.x ?? 0, (node.y ?? 0) + r + fs + 1);
        }}
      />
    </div>
  );
}
