"use client";
import dynamic from "next/dynamic";
import { useResolvedTheme } from "@/lib/preferences";
import { GRAPH_PALETTE, type GEdge, type GNode } from "@/components/app/graph-palette";

const GraphCanvas = dynamic(() => import("@/components/app/graph-canvas"), {
  ssr: false,
  loading: () => <div className="skeleton-shimmer h-full min-h-60" />,
});

/** Relationship graph around a vendor; the suspicious path is highlighted and animated. */
export function GraphView({ nodes, edges, path, height = 340 }: { nodes: GNode[]; edges: GEdge[]; path: string[]; height?: number }) {
  const theme = useResolvedTheme();
  const pal = GRAPH_PALETTE[theme];
  if (nodes.length === 0) return <div className="py-10 text-center text-sm text-muted-foreground">No shared identifiers found for this vendor.</div>;
  const legend = [
    { label: "Vendor", color: pal.vendor },
    { label: "Employee", color: pal.employee },
    { label: "User", color: pal.user },
    { label: "Identifier (phone, bank, address)", color: pal.identifier },
  ].filter((l) => l.label !== "User" || nodes.some((n) => n.kind === "user"));
  return (
    <div>
      <div
        className="relative overflow-hidden rounded-xl border border-border bg-[var(--graph-bg)] [background-image:radial-gradient(var(--graph-dot)_1px,transparent_1px)] [background-size:18px_18px]"
        style={{ height }}
      >
        {/* re-mount on theme change so the canvas repaints with the new palette */}
        <GraphCanvas key={theme} nodes={nodes} edges={edges} path={path} height={height} theme={theme} />
        <div className="pointer-events-none absolute left-3 top-2.5 text-[10px] text-muted-foreground">Drag nodes · scroll to zoom · hover for details</div>
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
        {legend.map((l) => <span key={l.label} className="flex items-center gap-1.5"><span className="inline-block size-2.5 rounded-full" style={{ background: l.color }} />{l.label}</span>)}
        {path.length > 0 && <span className="flex items-center gap-1.5"><span className="inline-block h-0.5 w-4 rounded" style={{ background: pal.hot }} />Suspicious link</span>}
      </div>
    </div>
  );
}
