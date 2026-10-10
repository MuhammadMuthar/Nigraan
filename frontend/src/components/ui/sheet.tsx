"use client";
import * as React from "react";
import * as D from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

export const Sheet = D.Root;
export const SheetTrigger = D.Trigger;

export function SheetContent({ className, children, side = "right", ...props }: React.ComponentPropsWithoutRef<typeof D.Content> & { side?: "left" | "right" }) {
  return (
    <D.Portal>
      <D.Overlay className="sheet-overlay fixed inset-0 z-50 bg-black/30" />
      <D.Content
        data-side={side}
        className={cn(
          "sheet-content fixed top-0 z-50 flex h-full w-full max-w-xl flex-col overflow-y-auto border-border bg-card shadow-2xl",
          side === "left" ? "left-0 border-r" : "right-0 border-l",
          className,
        )}
        {...props}
      >
        {children}
        <D.Close className="absolute right-4 top-4 rounded p-1 text-muted-foreground hover:bg-muted" aria-label="Close">
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
