import { useCallback, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useSSE } from "../hooks/useSSE";

interface Point {
  step: number;
  [key: string]: number;
}

export function MetricsChart({ runId }: { runId: string }) {
  const [points, setPoints] = useState<Point[]>([]);
  const [keys, setKeys] = useState<Set<string>>(new Set());

  const onMessage = useCallback((data: string) => {
    try {
      const parsed = JSON.parse(data) as { name: string; value: number; step: number };
      setPoints((prev) => {
        const last = prev.length > 0 ? prev[prev.length - 1] : null;
        if (last && last.step === parsed.step) {
          const merged = { ...last, [parsed.name]: parsed.value };
          return [...prev.slice(0, -1), merged];
        }
        return [...prev, { step: parsed.step, [parsed.name]: parsed.value }];
      });
      setKeys((prev) => {
        if (prev.has(parsed.name)) return prev;
        const next = new Set(prev);
        next.add(parsed.name);
        return next;
      });
    } catch {
      // Ignore non-JSON heartbeats.
    }
  }, []);

  useSSE(`/api/v1/runs/${runId}/metrics`, onMessage);

  const colors = ["#60a5fa", "#f87171", "#34d399", "#fbbf24", "#a78bfa"];

  return (
    <div className="h-96 bg-base-200 rounded p-2">
      {points.length === 0 ? (
        <div className="flex items-center justify-center h-full opacity-60">
          Waiting for metrics…
        </div>
      ) : (
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="step" />
            <YAxis />
            <Tooltip />
            {Array.from(keys).map((k, i) => (
              <Line
                key={k}
                type="monotone"
                dataKey={k}
                stroke={colors[i % colors.length]}
                dot={false}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
