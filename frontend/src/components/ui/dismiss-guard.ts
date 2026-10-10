"use client";
import * as React from "react";
import type * as D from "@radix-ui/react-dialog";

type OnInteractOutside = NonNullable<React.ComponentPropsWithoutRef<typeof D.Content>["onInteractOutside"]>;
type OutsideEvent = Parameters<OnInteractOutside>[0];

/**
 * Radix decides a click was "outside" only after the click finishes. If the pointer went down while this
 * layer was playing its closing animation (e.g. opening the next invoice right after Esc), that late
 * dismissal would close the drawer the click just opened. Record the layer's state when each pointer/focus
 * event starts and ignore dismissals that began while it was closing.
 */
export function useDismissGuard<T extends HTMLElement>(onInteractOutside?: OnInteractOutside) {
  const ref = React.useRef<T>(null);
  const stateAt = React.useRef(new WeakMap<Event, string | undefined>());
  React.useEffect(() => {
    const record = (e: Event) => stateAt.current.set(e, ref.current?.dataset.state);
    document.addEventListener("pointerdown", record, true);
    document.addEventListener("focusin", record, true);
    return () => {
      document.removeEventListener("pointerdown", record, true);
      document.removeEventListener("focusin", record, true);
    };
  }, []);
  const guard = React.useCallback((event: OutsideEvent) => {
    if (stateAt.current.get(event.detail.originalEvent) === "closed") event.preventDefault();
    else onInteractOutside?.(event);
  }, [onInteractOutside]);
  return [ref, guard] as const;
}
