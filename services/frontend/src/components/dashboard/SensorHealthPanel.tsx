import React, { useEffect, useState } from "react";
import { useAuth } from "@/components/auth/KeycloakProvider";
import { SensorHealth } from "./DashboardTypes";

type Props = {
  buildingId?: string;
};

export default function SensorHealthPanel({ buildingId }: Props) {
  const { fetchWithAuth, isReady } = useAuth();
  const [sensors, setSensors] = useState<SensorHealth[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!isReady) return;
    let cancelled = false;
    const fetchData = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || "/api";
        const res = await fetchWithAuth(`${apiUrl}/campus/sensors/health`);
        if (!res.ok) return;
        const data: SensorHealth[] = await res.json();
        if (!cancelled) setSensors(data);
      } catch (_e) {
        // ignore
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchData();
    const t = setInterval(fetchData, 10000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [fetchWithAuth, isReady]);

  const filtered = buildingId
    ? sensors.filter((s) => s.building_id === buildingId)
    : sensors;
  const broken = filtered.filter((s) => s.broken);
  const anomalous = filtered.filter((s) => s.anomalous && !s.broken);
  const ok = filtered.filter((s) => !s.broken && !s.anomalous);

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/60 p-3 text-xs text-slate-100">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="font-semibold">
            {buildingId ? `SENSOR HEALTH - ${buildingId.toUpperCase()}` : "SENSOR HEALTH"}
          </span>
        </div>
        <span className="text-slate-400">
          {loading
            ? "…"
            : `${ok.length} ok · ${anomalous.length} anom · ${broken.length} down`}
        </span>
      </div>
      <div className="max-h-48 overflow-y-auto">
        {[...broken, ...anomalous, ...ok.slice(0, 20)].map((s) => {
          const tag = s.broken
            ? { label: "DOWN", color: "bg-red-700" }
            : s.anomalous
            ? { label: "ANOM", color: "bg-amber-600" }
            : { label: "OK", color: "bg-emerald-700" };
          return (
            <div
              key={s.sensor_id}
              className="flex items-center justify-between border-b border-slate-800 py-1 last:border-0"
              title={s.sensor_id}
            >
              <div className="flex min-w-0 flex-1 flex-col">
                <span className="truncate">{s.sensor_id}</span>
                <span className="text-[10px] text-slate-400">
                  {s.sensor_type} · {s.last_value ?? "—"} ·{" "}
                  {s.seconds_since != null ? `${s.seconds_since}s ago` : "no data"}
                </span>
              </div>
              <span className={`ml-2 rounded px-1.5 py-0.5 text-[10px] ${tag.color}`}>
                {tag.label}
              </span>
            </div>
          );
        })}
        {filtered.length === 0 && !loading && (
          <div className="py-3 text-center text-slate-500">No sensors reporting</div>
        )}
      </div>
    </div>
  );
}
