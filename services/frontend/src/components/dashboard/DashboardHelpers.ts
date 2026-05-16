import { Zone, ZoneStatus } from "./DashboardTypes";

export function clamp(v: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, v));
}

export function deriveStatus(occ: number, temp: number): ZoneStatus {
  if (occ > 86 || temp > 34) return "critical";
  if (occ > 65 || temp > 31) return "busy";
  return "normal";
}

export function updateZone(zone: Zone): Zone {
  const e = clamp(zone.energyKw + (Math.random() * 4 - 2), 15, 140);
  const o = clamp(zone.occupancy + (Math.random() * 2 - 1), 5, 98);
  const t = clamp(zone.temperatureC + (Math.random() * 0.4 - 0.2), 22, 38);
  return {
    ...zone,
    energyKw: +e.toFixed(1),
    occupancy: Math.round(o),
    temperatureC: +t.toFixed(1),
    status: deriveStatus(o, t),
    hasData: zone.hasData,
  };
}
