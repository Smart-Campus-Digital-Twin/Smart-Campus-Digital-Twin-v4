import React, { useEffect, useState } from "react";
import { useAuth } from "@/components/auth/KeycloakProvider";
import { AnomalyEntry } from "./DashboardTypes";

export default function AnomalyPanel() {
  const { fetchWithAuth, isReady } = useAuth();
  const [items, setItems] = useState<AnomalyEntry[]>([]);

  useEffect(() => {
    if (!isReady) return;
    let cancelled = false;
    const fetchData = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || "/api";
        const res = await fetchWithAuth(`${apiUrl}/campus/anomalies/recent?limit=30`);
        if (!res.ok) return;
        const data: AnomalyEntry[] = await res.json();
        if (!cancelled) setItems(data);
      } catch (_e) {
        // ignore
      }
    };
    fetchData();
    const t = setInterval(fetchData, 10000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [fetchWithAuth, isReady]);

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/60 p-3 text-xs text-slate-100">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-semibold">RECENT ANOMALIES</span>
        <span className="text-slate-400">{items.length}</span>
      </div>
      <div className="max-h-48 overflow-y-auto">
        {items.length === 0 && (
          <div className="py-3 text-center text-slate-500">No anomalies</div>
        )}
        {items.map((a, i) => {
          const sevColor =
            a.severity === "critical"
              ? "text-red-400"
              : a.severity === "warning"
              ? "text-amber-400"
              : "text-slate-300";
          return (
            <div
              key={`${a.detected_at}-${i}`}
              className="border-b border-slate-800 py-1 last:border-0"
              title={a.sensor_id}
            >
              <div className={`text-[11px] font-semibold ${sevColor}`}>{a.rule}</div>
              <div className="text-[10px] text-slate-400">
                {new Date(a.detected_at).toLocaleTimeString()} · {a.room_id}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
