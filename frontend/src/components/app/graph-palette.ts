// Shared by the lazy-loaded canvas and the legend (kept separate so the legend does not pull in the canvas library).
export type GNode = { id: string; kind: string; label: string };
export type GEdge = { source: string; target: string };

export const GRAPH_PALETTE = {
  light: {
    vendor: "#0f766e", employee: "#b91c1c", user: "#7c3aed", identifier: "#71717a", link: "#cbd5e1", hot: "#dc2626",
    glow: "rgba(220, 38, 38, 0.16)", labelBg: "rgba(255, 255, 255, 0.95)", labelBorder: "#e2e8f0", text: "#0f172a", textMuted: "#475569", ring: "#ffffff",
  },
  dark: {
    vendor: "#2dd4bf", employee: "#f87171", user: "#a78bfa", identifier: "#64748b", link: "#334155", hot: "#f87171",
    glow: "rgba(248, 113, 113, 0.22)", labelBg: "rgba(13, 22, 38, 0.95)", labelBorder: "#22314a", text: "#e2e8f0", textMuted: "#94a3b8", ring: "#0d1626",
  },
};
