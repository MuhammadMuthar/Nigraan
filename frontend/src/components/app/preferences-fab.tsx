"use client";
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import * as Popover from "@radix-ui/react-popover";
import { Toaster, toast } from "sonner";
import { EyeOff, Monitor, Moon, Move, RotateCcw, Settings2, Sun, X } from "lucide-react";
import { changeTheme, getPrefs, OPEN_PREFERENCES_EVENT, setPrefs, usePrefs, useResolvedTheme, type ThemePref } from "@/lib/preferences";
import { cn } from "@/lib/utils";

const SIZE = 48;
const MARGIN = 16;
const DEFAULT_SPOT = { fx: 1, fy: 1 }; // bottom-right
const THEMES: { value: ThemePref; label: string; Icon: typeof Sun }[] = [
  { value: "light", label: "Light", Icon: Sun },
  { value: "dark", label: "Dark", Icon: Moon },
  { value: "system", label: "System", Icon: Monitor },
];

type Pt = { x: number; y: number };
type Viewport = { w: number; h: number };

// The position is stored as a fraction of the free space, so the button keeps its place when the window resizes.
const room = (vp: Viewport) => ({ w: Math.max(1, vp.w - SIZE - 2 * MARGIN), h: Math.max(1, vp.h - SIZE - 2 * MARGIN) });
const clamp01 = (n: number) => Math.min(1, Math.max(0, n));
const toPx = (f: { fx: number; fy: number }, vp: Viewport): Pt => ({ x: MARGIN + f.fx * room(vp).w, y: MARGIN + f.fy * room(vp).h });
const toFrac = (p: Pt, vp: Viewport) => ({ fx: clamp01((p.x - MARGIN) / room(vp).w), fy: clamp01((p.y - MARGIN) / room(vp).h) });
const clampPt = (p: Pt, vp: Viewport): Pt => toPx(toFrac(p, vp), vp);

function subscribeResize(cb: () => void) {
  window.addEventListener("resize", cb);
  return () => window.removeEventListener("resize", cb);
}
function useViewport(): Viewport | null {
  const key = useSyncExternalStore(subscribeResize, () => `${window.innerWidth}x${window.innerHeight}`, () => null);
  if (!key) return null;
  const [w, h] = key.split("x").map(Number);
  return { w, h };
}

function centerOf(el: Element) {
  const r = el.getBoundingClientRect();
  return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
}

/** Floating preferences button: drag it anywhere, click it for theme and motion settings, or hide it. */
export function PreferencesFab() {
  const prefs = usePrefs();
  const vp = useViewport();
  const [open, setOpen] = useState(false);
  const [dragPos, setDragPos] = useState<Pt | null>(null);
  const button = useRef<HTMLButtonElement>(null);
  const drag = useRef<{ id: number; sx: number; sy: number; origin: Pt; moved: boolean } | null>(null);
  const swallowClick = useRef(false);

  const show = useCallback((openPanel: boolean) => {
    const wasHidden = getPrefs().fabHidden;
    setPrefs({ fabHidden: false });
    if (openPanel) setOpen(true);
    else if (wasHidden) toast.success("Preferences button is back", { description: "Drag it anywhere on the screen." });
  }, []);

  // Shift + P brings a hidden button back (or toggles the panel); the profile menu can open it too.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (!e.shiftKey || e.ctrlKey || e.metaKey || e.altKey || e.code !== "KeyP") return;
      const t = e.target as HTMLElement | null;
      if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return;
      e.preventDefault();
      if (getPrefs().fabHidden) show(false);
      else setOpen((o) => !o);
    }
    const onOpen = () => show(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener(OPEN_PREFERENCES_EVENT, onOpen);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener(OPEN_PREFERENCES_EVENT, onOpen);
    };
  }, [show]);

  if (!vp || prefs.fabHidden) return null;
  const rest = toPx(prefs.fabPos ?? DEFAULT_SPOT, vp);
  const pos = dragPos ?? rest;
  const dragging = dragPos !== null;
  const lower = pos.y > vp.h / 2;
  const right = pos.x > vp.w / 2;

  function onPointerDown(e: React.PointerEvent<HTMLButtonElement>) {
    if (e.button !== 0) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { id: e.pointerId, sx: e.clientX, sy: e.clientY, origin: rest, moved: false };
  }
  function onPointerMove(e: React.PointerEvent<HTMLButtonElement>) {
    const d = drag.current;
    if (!d || d.id !== e.pointerId || !vp) return;
    const dx = e.clientX - d.sx;
    const dy = e.clientY - d.sy;
    if (!d.moved) {
      if (Math.hypot(dx, dy) < 5) return; // a small wobble is still a click
      d.moved = true;
      setOpen(false);
    }
    setDragPos(clampPt({ x: d.origin.x + dx, y: d.origin.y + dy }, vp));
  }
  function onPointerUp(e: React.PointerEvent<HTMLButtonElement>) {
    const d = drag.current;
    if (!d || d.id !== e.pointerId || !vp) return;
    drag.current = null;
    if (!d.moved) return;
    swallowClick.current = true;
    setPrefs({ fabPos: toFrac({ x: d.origin.x + e.clientX - d.sx, y: d.origin.y + e.clientY - d.sy }, vp) });
    setDragPos(null);
  }
  function onKeyDown(e: React.KeyboardEvent<HTMLButtonElement>) {
    const step = e.shiftKey ? 64 : 16;
    const delta: Record<string, Pt> = { ArrowLeft: { x: -step, y: 0 }, ArrowRight: { x: step, y: 0 }, ArrowUp: { x: 0, y: -step }, ArrowDown: { x: 0, y: step } };
    const d = delta[e.key];
    if (!d || !vp) return;
    e.preventDefault();
    setPrefs({ fabPos: toFrac({ x: rest.x + d.x, y: rest.y + d.y }, vp) });
  }

  function hide() {
    setOpen(false);
    setPrefs({ fabHidden: true });
    toast("Preferences button hidden", {
      description: "To bring it back, press Shift + P, or open your profile menu (top right) and choose “Show preferences button”.",
      icon: <EyeOff className="size-4" />,
      duration: 10000,
      action: { label: "Undo", onClick: () => setPrefs({ fabHidden: false }) },
    });
  }

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Anchor asChild>
        <button
          ref={button}
          type="button"
          aria-label="Preferences (drag to move, arrow keys to nudge)"
          aria-haspopup="dialog"
          aria-expanded={open}
          title="Preferences · drag me anywhere"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          onKeyDown={onKeyDown}
          onClick={() => {
            if (swallowClick.current) {
              swallowClick.current = false;
              return;
            }
            setOpen((o) => !o);
          }}
          style={{ width: SIZE, height: SIZE, transform: `translate3d(${pos.x}px, ${pos.y}px, 0)` }}
          className={cn(
            "group fixed left-0 top-0 z-40 flex animate-pop-badge touch-none select-none items-center justify-center rounded-full border border-border bg-card/90 text-muted-foreground shadow-[var(--shadow-lift)] backdrop-blur-md hover:border-accent/50 hover:text-accent",
            dragging ? "scale-110 cursor-grabbing border-accent/60 text-accent ring-4 ring-accent/15 transition-[scale,box-shadow]" : "cursor-grab transition-[transform,scale,color,border-color,box-shadow] duration-300 ease-out",
            open && "border-accent/60 text-accent ring-4 ring-accent/15",
          )}
        >
          <Settings2 aria-hidden className={cn("size-5 transition-transform duration-500", open ? "rotate-90" : "group-hover:rotate-45")} />
          <Move aria-hidden className="absolute -right-0.5 -top-0.5 size-4 rounded-full border border-border bg-card p-0.5 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
        </button>
      </Popover.Anchor>
      <Popover.Portal>
        <Popover.Content
          side={lower ? "top" : "bottom"}
          align={right ? "end" : "start"}
          sideOffset={12}
          collisionPadding={12}
          aria-label="Preferences"
          // clicking the button itself toggles; don't let it also count as an outside click
          onInteractOutside={(e) => {
            if (button.current?.contains(e.target as Node)) e.preventDefault();
          }}
          className="z-50 w-[19rem] origin-[var(--radix-popover-content-transform-origin)] rounded-2xl border border-border bg-card p-4 shadow-[var(--shadow-lift)] data-[state=closed]:animate-pop-out data-[state=open]:animate-pop-in"
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold">Preferences</div>
              <div className="mt-0.5 text-xs text-muted-foreground">Drag the button anywhere on the screen.</div>
            </div>
            <Popover.Close aria-label="Close preferences" className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"><X className="size-4" /></Popover.Close>
          </div>

          <div className="mt-4 text-xs font-medium text-muted-foreground" id="pref-theme">Appearance</div>
          <div role="radiogroup" aria-labelledby="pref-theme" className="mt-2 grid grid-cols-3 gap-1 rounded-xl bg-muted p-1">
            {THEMES.map(({ value, label, Icon }) => (
              <button key={value} type="button" role="radio" aria-checked={prefs.theme === value}
                onClick={(e) => changeTheme(value, centerOf(e.currentTarget))}
                className={cn("flex flex-col items-center gap-1 rounded-lg px-2 py-2 text-xs font-medium transition-all duration-200",
                  prefs.theme === value ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground")}>
                <Icon aria-hidden className={cn("size-4 transition-transform duration-300", prefs.theme === value && "scale-110 text-accent")} />{label}
              </button>
            ))}
          </div>

          <div className="mt-4 flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-medium" id="pref-motion">Animations</div>
              <div className="text-xs text-muted-foreground">Page, chart and number motion</div>
            </div>
            <button type="button" role="switch" aria-checked={prefs.animations} aria-labelledby="pref-motion"
              onClick={() => setPrefs({ animations: !prefs.animations })}
              className={cn("relative h-6 w-11 shrink-0 rounded-full transition-colors duration-200", prefs.animations ? "bg-primary" : "bg-border")}>
              <span className={cn("absolute left-0.5 top-0.5 size-5 rounded-full bg-white shadow transition-transform duration-200", prefs.animations && "translate-x-5")} />
            </button>
          </div>

          <button type="button" onClick={() => setPrefs({ fabPos: null })} disabled={!prefs.fabPos}
            className="mt-4 flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm transition-colors hover:bg-muted disabled:opacity-50 disabled:hover:bg-transparent">
            <RotateCcw aria-hidden className="size-4 text-muted-foreground" />Move button back to the corner
          </button>

          <div className="mt-2 border-t border-border pt-2">
            <button type="button" onClick={hide} className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm transition-colors hover:bg-muted">
              <EyeOff aria-hidden className="size-4 text-muted-foreground" />Hide this button
            </button>
            <p className="px-2 text-[11px] leading-relaxed text-muted-foreground">
              Bring it back any time with <kbd className="rounded border border-border bg-muted px-1 font-sans">Shift</kbd> + <kbd className="rounded border border-border bg-muted px-1 font-sans">P</kbd>, or from your profile menu.
            </p>
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

export function ThemedToaster() {
  const theme = useResolvedTheme();
  return <Toaster position="bottom-center" theme={theme} richColors closeButton />;
}
