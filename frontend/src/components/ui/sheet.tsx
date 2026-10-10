"use client";
import * as React from "react";
import * as D from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useDismissGuard } from "@/components/ui/dismiss-guard";

export const Sheet = D.Root;
export const SheetTrigger = D.Trigger;

const SIDE = {
  right: "right-0 border-l data-[state=open]:animate-sheet-in-right data-[state=closed]:pointer-events-none data-[state=closed]:animate-sheet-out-right",
  left: "left-0 border-r data-[state=open]:animate-sheet-in-left data-[state=closed]:pointer-events-none data-[state=closed]:animate-sheet-out-left",
};

export function SheetContent({ className, children, side = "right", onInteractOutside, ...props }: React.ComponentPropsWithoutRef<typeof D.Content> & { side?: "left" | "right" }) {
  const [contentRef, guardedInteractOutside] = useDismissGuard<HTMLDivElement>(onInteractOutside);
  return (
    <D.Portal>
      {/* while closing, the overlay and panel still animate but let clicks through to the page (important: Radix sets an inline pointer-events on the overlay) */}
      <D.Overlay className="fixed inset-0 z-50 bg-black/30 data-[state=closed]:pointer-events-none! data-[state=closed]:animate-fade-out data-[state=open]:animate-fade-in dark:bg-black/55" />
      <D.Content
        className={cn(
          "fixed top-0 z-50 flex h-full w-full max-w-xl flex-col overflow-y-auto border-border bg-card shadow-2xl",
          SIDE[side],
          className,
        )}
        {...props}
        ref={contentRef}
        onInteractOutside={guardedInteractOutside}
      >
        {children}
        <D.Close className="absolute right-4 top-4 rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground" aria-label="Close">
          <X className="size-4" />
        </D.Close>
      </D.Content>
    </D.Portal>
  );
}
export function SheetTitle({ className, ...props }: React.ComponentPropsWithoutRef<typeof D.Title>) {
  return <D.Title className={cn("text-base font-semibold", className)} {...props} />;
}
export function SheetDescription({ className, ...props }: React.ComponentPropsWithoutRef<typeof D.Description>) {
  return <D.Description className={cn("text-sm text-muted-foreground", className)} {...props} />;
}
