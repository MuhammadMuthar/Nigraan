"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D, { type ForceGraphMethods, type LinkObject, type NodeObject } from "react-force-graph-2d";
import { Maximize2 } from "lucide-react";
import { GRAPH_PALETTE, type GEdge, type GNode } from "@/components/app/graph-palette";

type SimNode = NodeObject<GNode>;
type SimLink = LinkObject<GNode, { hot: boolean }>;

const KIND_LABEL: Record<string, string> = { bank: "Bank", phone: "Phone", address: "Address", cnic: "CNIC" };
const ENTITY = new Set(["vendor", "employee", "user"]);
const FONT_PX = 11; // labels keep this on-screen size at any zoom
const LABEL_GAP = 4; // px between a node and its label pill
const LABEL_H = FONT_PX + 6; // px height of the label pill
const MAX_ZOOM = 1.8;
// What the layout is planned for: labels are fixed px while forces work in graph units, and narrow canvases get shorter labels.
type Plan = { current: { zoom: number; chars: number } };

const radius = (n: GNode) => (ENTITY.has(n.kind) ? 7 : 4.5);
function labelOf(n: GNode, chars: number) {
  const text = ENTITY.has(n.kind) ? n.label : `${KIND_LABEL[n.kind] ?? n.kind}: ${n.label}`;
  return text.length > chars ? `${text.slice(0, chars - 2)}…` : text;
}
const labelPx = (n: GNode, chars: number) => labelOf(n, chars).length * 6.4 + 10; // on-screen width of the label pill (estimate)

/** Keeps nodes (and the label under each) from overlapping: box collision, pushed apart on the cheaper axis. */
function labelCollide(plan: Plan, strength = 0.8) {
  let nodes: SimNode[] = [];
  const box = (n: SimNode) => ({
    hw: Math.max(radius(n), (labelPx(n, plan.current.chars) / 2 + 8) / plan.current.zoom),
    hh: radius(n) + (LABEL_GAP + LABEL_H + 8) / plan.current.zoom,
  });
  const force = () => {
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i];
        const b = nodes[j];
        const sa = box(a);
        const sb = box(b);
        const dx = (b.x ?? 0) - (a.x ?? 0);
        const dy = (b.y ?? 0) - (a.y ?? 0);
        const ox = sa.hw + sb.hw - Math.abs(dx);
        const oy = sa.hh + sb.hh - Math.abs(dy);
        if (ox <= 0 || oy <= 0) continue;
        if (ox < oy) {
          const s = (dx < 0 ? -1 : 1) * ox * 0.5 * strength;
          a.vx = (a.vx ?? 0) - s;
          b.vx = (b.vx ?? 0) + s;
        } else {
          const s = (dy < 0 ? -1 : 1) * oy * 0.5 * strength;
          a.vy = (a.vy ?? 0) - s;
          b.vy = (b.vy ?? 0) + s;
        }
      }
    }
  };
  force.initialize = (ns: SimNode[]) => {
    nodes = ns;
  };
  return force;
}

/** Does the segment (x1,y1)-(x2,y2) pass through the rectangle? (Liang-Barsky clipping) */
function segmentHitsRect(x1: number, y1: number, x2: number, y2: number, left: number, top: number, right: number, bottom: number) {
  const dx = x2 - x1;
  const dy = y2 - y1;
  let t0 = 0;
  let t1 = 1;
  for (const [p, q] of [[-dx, x1 - left], [dx, right - x1], [-dy, y1 - top], [dy, bottom - y1]]) {
    if (p === 0) {
      if (q < 0) return false;
      continue;
    }
    const r = q / p;
    if (p < 0) t0 = Math.max(t0, r);
    else t1 = Math.min(t1, r);
    if (t0 > t1) return false;
  }
  return true;
}

/** Pushes a node sideways off any link it is not part of while that line crosses the node or its label pill. */
function linkAvoid(links: SimLink[], plan: Plan, step = 3) {
  let nodes: SimNode[] = [];
  const force = () => {
    for (const l of links) {
      const s = l.source as SimNode;
      const t = l.target as SimNode;
      if (typeof s !== "object" || typeof t !== "object") continue;
      const [sx, sy, tx, ty] = [s.x ?? 0, s.y ?? 0, t.x ?? 0, t.y ?? 0];
      const len = Math.hypot(tx - sx, ty - sy) || 1;
      const [px, py] = [-(ty - sy) / len, (tx - sx) / len]; // unit normal of the link
      for (const n of nodes) {
        if (n === s || n === t) continue;
        const x = n.x ?? 0;
        const y = n.y ?? 0;
        const r = radius(n);
        const half = (labelPx(n, plan.current.chars) / 2 + 4) / plan.current.zoom;
        const bottom = y + r + (LABEL_GAP + LABEL_H + 4) / plan.current.zoom;
        if (!segmentHitsRect(sx, sy, tx, ty, x - half, y - r - 4, x + half, bottom)) continue;
        // move the node off the line, and the line a little the other way
        const side = (x - sx) * px + ((y + bottom) / 2 - sy) * py >= 0 ? 1 : -1;
        n.vx = (n.vx ?? 0) + side * px * step;
        n.vy = (n.vy ?? 0) + side * py * step;
        for (const end of [s, t]) {
          end.vx = (end.vx ?? 0) - side * px * step * 0.35;
          end.vy = (end.vy ?? 0) - side * py * step * 0.35;
        }
      }
    }
  };
  force.initialize = (ns: SimNode[]) => {
    nodes = ns;
  };
  return force;
}

export default function GraphCanvas({ nodes, edges, path, height, theme }: { nodes: GNode[]; edges: GEdge[]; path: string[]; height: number; theme: "light" | "dark" }) {
  const wrap = useRef<HTMLDivElement>(null);
  const fg = useRef<ForceGraphMethods<SimNode, SimLink> | undefined>(undefined);
  const plan = useRef({ zoom: 0, chars: 42 });
  const fitted = useRef(false);
  const refits = useRef(0);
  const [width, setWidth] = useState(0);
  const pal = GRAPH_PALETTE[theme];

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      // first measurement: plan the layout for the zoom this width will likely need
      if (!plan.current.zoom) {
        plan.current = { zoom: Math.min(MAX_ZOOM, Math.max(0.9, (el.clientWidth - 40) / 360)), chars: el.clientWidth < 420 ? 20 : el.clientWidth < 600 ? 28 : 42 };
      }
      setWidth(el.clientWidth);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Keyed on content, not array identity: a parent re-render or a background refresh must not restart the layout.
  const pathKey = path.join("|");
  const graphKey = `${nodes.map((n) => n.id).join("|")}#${edges.map((e) => `${e.source}>${e.target}`).join("|")}`;
  const onPath = useMemo(() => new Set(pathKey ? pathKey.split("|") : []), [pathKey]);
  const data = useMemo(() => {
    const links = edges.map((e) => ({ ...e, hot: onPath.has(e.source) && onPath.has(e.target) }));
    // suspicious links last so they paint over the others
    links.sort((a, b) => Number(a.hot) - Number(b.hot));
    return { nodes: nodes.map((n) => ({ ...n })), links };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- graphKey captures nodes/edges content
  }, [graphKey, onPath]);

  // Spread the graph out so labels have room.
  const ready = width > 0;
  useEffect(() => {
    const g = fg.current;
    if (!g) return;
    fitted.current = false;
    refits.current = 0;
    g.d3Force("charge")?.strength(-420);
    g.d3Force("link")?.distance(95);
    g.d3Force("collide", labelCollide(plan));
    g.d3Force("avoid", linkAvoid(data.links as SimLink[], plan));
    g.d3ReheatSimulation();
  }, [data, ready]);

  /** Fit nodes *and* label pills (fixed pixel size) exactly into the canvas; returns the zoom used. */
  const fit = useCallback((ms: number) => {
    const g = fg.current;
    const ns = data.nodes as SimNode[];
    if (!g || !ns.length || !width) return null;
    const [top, side, bottom] = [30, 12, 10]; // room for the hint line and the Fit button
    const extent = (k: number) => {
      let [l, r, t, b] = [Infinity, -Infinity, Infinity, -Infinity];
      for (const n of ns) {
        const x = (n.x ?? 0) * k;
        const y = (n.y ?? 0) * k;
        const half = Math.max(radius(n) * k, labelPx(n, plan.current.chars) / 2);
        l = Math.min(l, x - half);
        r = Math.max(r, x + half);
        t = Math.min(t, y - radius(n) * k);
        b = Math.max(b, y + radius(n) * k + LABEL_GAP + LABEL_H);
      }
      return { l, r, t, b };
    };
    const fits = (k: number) => {
      const e = extent(k);
      return e.r - e.l <= width - 2 * side && e.b - e.t <= height - top - bottom;
    };
    let [lo, hi] = [0.2, MAX_ZOOM];
    if (fits(hi)) lo = hi;
    else for (let i = 0; i < 24; i++) {
      const mid = (lo + hi) / 2;
      if (fits(mid)) lo = mid;
      else hi = mid;
    }
    const e = extent(lo);
    g.centerAt((e.l + e.r) / 2 / lo, ((e.t + e.b) / 2 - (top - bottom) / 2) / lo, ms);
    g.zoom(lo, ms);
    return lo;
  }, [data, width, height]);

  // keep the view fitted while the layout settles; if it needs a smaller zoom than planned, give labels more room once
  const onTick = () => {
    if (!fitted.current) fit(0);
  };
  const onStop = () => {
    if (fitted.current) return;
    const k = fit(400);
    if (k && k < plan.current.zoom * 0.9 && refits.current < 2) {
      plan.current = { ...plan.current, zoom: k };
      refits.current += 1;
      fg.current?.d3ReheatSimulation();
      return;
    }
    fitted.current = true;
  };
  useEffect(() => {
    if (fitted.current) fit(300);
  }, [fit]);

  const paintNode = useCallback((obj: SimNode, ctx: CanvasRenderingContext2D, scale: number) => {
    const x = obj.x ?? 0;
    const y = obj.y ?? 0;
    const hot = onPath.has(obj.id as string);
    const r = radius(obj);
    if (hot) {
      ctx.beginPath();
      ctx.arc(x, y, r + 5, 0, 2 * Math.PI);
      ctx.fillStyle = pal.glow;
      ctx.fill();
    }
    ctx.beginPath();
    ctx.arc(x, y, r, 0, 2 * Math.PI);
    ctx.globalAlpha = hot || ENTITY.has(obj.kind) || onPath.size === 0 ? 1 : 0.6;
    ctx.fillStyle = ENTITY.has(obj.kind) ? (pal[obj.kind as "vendor" | "employee" | "user"]) : pal.identifier;
    ctx.fill();
    ctx.globalAlpha = 1;
    ctx.lineWidth = (hot ? 2.2 : 1.5) / scale;
    ctx.strokeStyle = hot ? pal.hot : pal.ring;
    ctx.stroke();
  }, [onPath, pal]);

  // Labels are drawn after every link and node, on an opaque pill, so no line can cross them.
  const paintLabels = useCallback((ctx: CanvasRenderingContext2D, scale: number) => {
    const ordered = [...(data.nodes as SimNode[])].sort((a, b) => Number(onPath.has(a.id as string)) - Number(onPath.has(b.id as string)));
    const fs = FONT_PX / scale;
    const padX = 5 / scale;
    const padY = 3 / scale;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    for (const n of ordered) {
      const hot = onPath.has(n.id as string);
      const text = labelOf(n, plan.current.chars);
      ctx.font = `${hot || ENTITY.has(n.kind) ? 600 : 500} ${fs}px Inter, "Segoe UI", system-ui, sans-serif`;
      const w = ctx.measureText(text).width;
      const bx = (n.x ?? 0) - w / 2 - padX;
      const by = (n.y ?? 0) + radius(n) + 4 / scale;
      const bw = w + 2 * padX;
      const bh = fs + 2 * padY;
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(bx, by, bw, bh, 4 / scale);
      else ctx.rect(bx, by, bw, bh);
      ctx.fillStyle = pal.labelBg;
      ctx.fill();
      ctx.lineWidth = 1 / scale;
      ctx.strokeStyle = hot ? pal.hot : pal.labelBorder;
      ctx.stroke();
      ctx.fillStyle = hot ? pal.text : pal.textMuted;
      ctx.fillText(text, n.x ?? 0, by + bh / 2 + 0.5 / scale);
    }
  }, [data, onPath, pal]);

  return (
    <div ref={wrap} className="relative">
      {ready && <ForceGraph2D<GNode, { hot: boolean }>
        ref={fg}
        graphData={data}
        width={width}
        height={height}
        backgroundColor="rgba(0,0,0,0)"
        warmupTicks={30}
        cooldownTicks={140}
        maxZoom={MAX_ZOOM * 3}
        onEngineTick={onTick}
        onEngineStop={onStop}
        nodeRelSize={6}
        nodeLabel={(n) => `${ENTITY.has(n.kind) ? n.kind : KIND_LABEL[n.kind] ?? n.kind}: ${n.label}`}
        nodeCanvasObject={paintNode}
        linkColor={(l) => (l.hot ? pal.hot : pal.link)}
        linkWidth={(l) => (l.hot ? 2.5 : 1.2)}
        linkDirectionalParticles={(l) => (l.hot ? 3 : 0)}
        linkDirectionalParticleSpeed={0.006}
        linkDirectionalParticleWidth={3.5}
        linkDirectionalParticleColor={() => pal.hot}
        onRenderFramePost={paintLabels}
      />}
      <button type="button" onClick={() => fit(500)} aria-label="Fit graph to view"
        className="absolute right-2 top-2 flex items-center gap-1.5 rounded-md border border-border bg-card/90 px-2 py-1 text-[11px] font-medium text-muted-foreground shadow-sm backdrop-blur transition-colors hover:text-foreground">
        <Maximize2 aria-hidden className="size-3" />Fit
      </button>
    </div>
  );
}
