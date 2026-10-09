import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap", {
  variants: {
    variant: {
      default: "border-transparent bg-muted text-foreground",
      outline: "border-border text-muted-foreground",
      accent: "border-transparent bg-accent-soft text-accent",
      allow: "border-transparent bg-allow-soft text-allow",
      review: "border-transparent bg-review-soft text-review",
      blocked: "border-transparent bg-blocked-soft text-blocked",
    },
  },
  defaultVariants: { variant: "default" },
});

export function Badge({ className, variant, ...props }: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
