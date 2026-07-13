// meta: U7 in-panel live page preview (spec: apps/api docs/superpowers/specs/
// 2026-07-10-flag-preview-design.md). Renders API /flags/{id}/preview in a
// sandboxed iframe (no allow-top-navigation: frame-busting cannot hijack the
// tab). The proxied document self-highlights the evidence quote (mark.js,
// injected server-side) and reports {type:'shiboleth-preview', found} via
// postMessage; found=false -> amber "page changed" banner. Loading skeleton
// until iframe load; 15s timeout or load error -> unavailable banner.

"use client";

import { useEffect, useRef, useState } from "react";
import { TriangleAlert } from "lucide-react";
import { API_BASE } from "@/lib/api";

const LOAD_TIMEOUT_MS = 15_000;

type PreviewStatus = "loading" | "ready" | "error";

export function PagePreview({ flagId }: { flagId: string }) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [status, setStatus] = useState<PreviewStatus>("loading");
  const [quoteFound, setQuoteFound] = useState<boolean | null>(null);

  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      if (e.source !== iframeRef.current?.contentWindow) return;
      const data = e.data as { type?: string; found?: boolean };
      if (data?.type === "shiboleth-preview") setQuoteFound(data.found === true);
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, []);

  useEffect(() => {
    if (status !== "loading") return;
    const t = setTimeout(() => setStatus("error"), LOAD_TIMEOUT_MS);
    return () => clearTimeout(t);
  }, [status]);

  if (status === "error") {
    return (
      <div className="flex items-start gap-2.5 px-6 py-8">
        <TriangleAlert className="mt-0.5 size-3.5 flex-none text-warning" />
        <span className="text-xs text-muted-foreground">
          Live page preview unavailable. The source may be blocking automated
          access; use View original source instead.
        </span>
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      {quoteFound === false ? (
        <div className="flex items-start gap-2.5 border-b border-warning/30 bg-warning-bg px-4.5 py-2.5">
          <TriangleAlert className="mt-0.5 size-3.5 flex-none text-warning" />
          <span className="text-xs text-foreground/70">
            The flagged line was not found on the live page. The page has
            likely changed since this run; the Text tab shows the content as
            checked.
          </span>
        </div>
      ) : null}
      <div className="relative">
        {status === "loading" ? (
          <div className="absolute inset-0 animate-pulse bg-surface" />
        ) : null}
        <iframe
          ref={iframeRef}
          src={`${API_BASE}/flags/${flagId}/preview`}
          sandbox="allow-scripts allow-same-origin"
          className="h-[560px] w-full border-0"
          title="Original page preview with the flagged line highlighted"
          onLoad={() => setStatus("ready")}
          onError={() => setStatus("error")}
        />
      </div>
    </div>
  );
}
