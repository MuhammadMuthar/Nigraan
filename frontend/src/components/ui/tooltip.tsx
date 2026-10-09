"use client";
import * as React from "react";
import * as T from "@radix-ui/react-tooltip";
import { cn } from "@/lib/utils";

export const TooltipProvider = T.Provider;

export function Tooltip({ content, children, side = "top" }: { content: React.ReactNode; children: React.ReactNode; side?: "top" | "bottom" | "left" | "right" }) {
  return (
    <T.Root delayDuration={150}>
      <T.Trigger asChild>{children}</T.Trigger>
      <T.Portal>
        <T.Content side={side} sideOffset={6} className={cn("z-50 max-w-xs rounded-md bg-foreground px-2.5 py-1.5 text-xs text-white shadow-lg")}>
          {content}
          <T.Arrow className="fill-foreground" />
        </T.Content>
      </T.Portal>
    </T.Root>
  );
}
