"use client";
import * as React from "react";
import * as D from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useDismissGuard } from "@/components/ui/dismiss-guard";

export const Dialog = D.Root;
export const DialogTrigger = D.Trigger;
export const DialogClose = D.Close;

export function DialogContent({ className, children, onInteractOutside, ...props }: React.ComponentPropsWithoutRef<typeof D.Content>) {
  const [contentRef, guardedInteractOutside] = useDismissGuard<HTMLDivElement>(onInteractOutside);
  return (
    <D.Portal>
      <D.Overlay className="fixed inset-0 z-50 bg-black/40 backdrop-blur-[2px] data-[state=closed]:pointer-events-none! data-[state=closed]:animate-fade-out data-[state=open]:animate-fade-in dark:bg-black/60" />
      <D.Content
        className={cn(
          "fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border bg-card p-6 shadow-xl data-[state=closed]:pointer-events-none data-[state=closed]:animate-dialog-out data-[state=open]:animate-dialog-in",
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
export function DialogTitle({ className, ...props }: React.ComponentPropsWithoutRef<typeof D.Title>) {
  return <D.Title className={cn("text-base font-semibold", className)} {...props} />;
}
export function DialogDescription({ className, ...props }: React.ComponentPropsWithoutRef<typeof D.Description>) {
  return <D.Description className={cn("mt-1 text-sm text-muted-foreground", className)} {...props} />;
}
