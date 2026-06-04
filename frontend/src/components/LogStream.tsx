import { useCallback, useEffect, useRef, useState } from "react";
import { useSSE } from "../hooks/useSSE";

const MAX_LINES = 5000;

export function LogStream({ runId }: { runId: string }) {
  const [lines, setLines] = useState<string[]>([]);
  const containerRef = useRef<HTMLDivElement>(null);

  const onMessage = useCallback((data: string) => {
    setLines((prev) => {
      const next = prev.length >= MAX_LINES ? prev.slice(-MAX_LINES + 1) : prev.slice();
      next.push(data);
      return next;
    });
  }, []);

  useSSE(`/api/v1/runs/${runId}/logs`, onMessage);

  useEffect(() => {
    const el = containerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines]);

  return (
    <div
      ref={containerRef}
      className="bg-base-300 font-mono text-xs p-3 rounded h-96 overflow-y-auto"
    >
      {lines.map((l, i) => (
        <div key={i} className="whitespace-pre-wrap break-all">
          {l}
        </div>
      ))}
      {lines.length === 0 && (
        <div className="opacity-60">Waiting for log stream…</div>
      )}
    </div>
  );
}
