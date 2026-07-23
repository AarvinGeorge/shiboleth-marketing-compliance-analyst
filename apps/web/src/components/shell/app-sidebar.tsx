// meta: U1 app shell sidebar (expanded only, desktop 1440). Customize
// scorecard button (links to the U4 scorecard studio at /scorecard), New
// check primary CTA (opens the U3 modal), PRODUCTS list with status dots
// (DESIGN.md tokens: clear = success, flagged = warning, checking = primary)
// + open-flag count, user chip at bottom. Product list from useProducts.

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Plus, SlidersHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { NewCheckModal } from "@/components/shell/new-check-modal";
import { useProducts } from "@/lib/data";
import { cn } from "@/lib/utils";

const DOT: Record<string, string> = {
  flagged: "bg-warning",
  clear: "bg-success",
  checking: "bg-primary",
  empty: "bg-border",
};

export function AppSidebar() {
  const pathname = usePathname();
  const { products } = useProducts();

  return (
    <aside className="flex w-64 flex-none flex-col border-r border-border bg-surface">
      <Link href="/" className="flex items-center gap-2.5 px-5 pb-3.5 pt-5">
        <span className="flex size-[26px] flex-none items-center justify-center rounded-[7px] bg-primary text-[13px] font-bold text-primary-foreground">
          A
        </span>
        <span className="text-[15px] font-semibold tracking-tight">
          Adlign
        </span>
      </Link>
      <div className="flex flex-col gap-1.5 px-4 pb-3.5">
        <Button
          variant="ghost"
          asChild
          className={cn(
            "h-[34px] justify-start gap-2 px-2.5 text-[13px] text-foreground/70",
            pathname === "/scorecard" && "bg-border/60 text-foreground"
          )}
        >
          <Link href="/scorecard">
            <SlidersHorizontal className="size-3.5" />
            Customize scorecard
          </Link>
        </Button>
        <NewCheckModal>
          <Button className="h-9 w-full gap-2 text-[13px]">
            <Plus className="size-3.5" />
            New check
          </Button>
        </NewCheckModal>
      </div>
      <div className="px-5 pb-1.5 pt-2 text-[10.5px] font-semibold tracking-[0.08em] text-muted-foreground/70">
        PRODUCTS
      </div>
      <nav className="flex flex-1 flex-col gap-0.5 px-3">
        {products.map((p) => {
          const href = `/products/${p.id}`;
          const active = pathname.startsWith(href);
          return (
            <Link
              key={p.id}
              href={href}
              className={cn(
                "flex h-[34px] items-center gap-2 rounded-md px-2.5 text-[13px] font-medium",
                active ? "bg-border/60" : "hover:bg-border/40"
              )}
            >
              <span
                className={cn(
                  "size-[7px] flex-none rounded-pill",
                  DOT[p.status]
                )}
                aria-hidden="true"
              />
              <span className="whitespace-nowrap">{p.name}</span>
              {p.openFlagCount > 0 ? (
                <span className="ml-auto font-mono text-[11px] font-medium text-muted-foreground">
                  {p.openFlagCount}
                </span>
              ) : null}
            </Link>
          );
        })}
      </nav>
      <div className="flex items-center gap-2.5 border-t border-border px-5 py-3.5">
        <span className="flex size-7 flex-none items-center justify-center rounded-pill bg-border text-[11px] font-semibold text-foreground/60">
          A
        </span>
        <span className="flex flex-col leading-tight">
          <span className="text-[13px] font-medium">Aarvin</span>
          <span className="text-[11px] text-muted-foreground">
            Compliance analyst
          </span>
        </span>
      </div>
    </aside>
  );
}
