"use client";

import React, { useState, useEffect, useCallback } from "react";
import { Brain, TrendingUp } from "lucide-react";
import { useAuth } from "@/components/auth/KeycloakProvider";
import { useRouter } from "next/navigation";

interface PredictionData {
  room_id: string;
  predicted_avg: number;
  actual_avg: number;
  timestamp: string;
  written_to_influx: boolean;
}

interface SeriesPoint {
  timestamp: string;
  predicted_avg: number;
}

function Sparkline({ points, capacity }: { points: SeriesPoint[]; capacity: number }) {
  if (points.length < 2) return null;
  const w = 280;
  const h = 80;
  const pad = 4;
  const ys = points.map((p) => p.predicted_avg);
  const maxY = Math.max(capacity, ...ys);
  const minY = 0;
  const range = maxY - minY || 1;
  const stepX = (w - pad * 2) / (points.length - 1);
  const path = points
    .map((p, i) => {
      const x = pad + i * stepX;
      const y = h - pad - ((p.predicted_avg - minY) / range) * (h - pad * 2);
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const area = path + ` L${(pad + (points.length - 1) * stepX).toFixed(1)},${h - pad} L${pad},${h - pad} Z`;
  const capY = h - pad - ((capacity - minY) / range) * (h - pad * 2);
  return (
    <svg width={w} height={h} style={{ display: "block" }}>
      <line x1={pad} y1={capY} x2={w - pad} y2={capY} stroke="rgba(248,113,113,0.5)" strokeDasharray="3 3" />
      <path d={area} fill="rgba(151,254,237,0.15)" />
      <path d={path} fill="none" stroke="#97FEED" strokeWidth="1.5" />
      {points.map((p, i) => {
        const x = pad + i * stepX;
        const y = h - pad - ((p.predicted_avg - minY) / range) * (h - pad * 2);
        return <circle key={i} cx={x} cy={y} r={1.5} fill="#97FEED" />;
      })}
    </svg>
  );
}

interface MLPredictionPanelProps {
  selectedZoneId: string;
  selectedZoneName: string;
  occupancy: number;
  buildingId?: string;
  totalCapacity?: number;
  currentOccupancy?: number;
}

export default function MLPredictionPanel({
  selectedZoneId,
  selectedZoneName,
  occupancy,
  buildingId,
  totalCapacity,
  currentOccupancy,
}: MLPredictionPanelProps) {
  const { fetchWithAuth, isReady, isAuthenticated } = useAuth();
  const [prediction, setPrediction] = useState<PredictionData | null>(null);
  const [series, setSeries] = useState<SeriesPoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  const fetchPrediction = useCallback(async () => {
    if (!isReady || !isAuthenticated) {
      return;
    }

    // Only predict for canteen and library as per the backend models
    const roomType = selectedZoneName.toLowerCase().includes("canteen") 
      ? "canteen" 
      : selectedZoneName.toLowerCase().includes("library") 
        ? "library" 
        : null;

    if (!roomType) {
      setPrediction(null);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "/api";
      const cap = totalCapacity && totalCapacity > 0 ? totalCapacity : 100;
      const actualPct = currentOccupancy ?? occupancy;
      const actualCount = Math.round((actualPct / 100) * cap);
      const res = await fetchWithAuth(`${apiUrl}/predictions/congestion`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          room_id: selectedZoneId,
          room_type: roomType,
          building_id: buildingId || selectedZoneId,
          timestamp: new Date().toISOString(),
          avg: actualCount,
          capacity: cap,
          history: Array.from({ length: 50 }, (_, i) =>
            i < 47 ? actualCount : [actualCount * 0.9, actualCount * 1.1, actualCount][i - 47]
          ),
          context: {
            is_weekend: new Date().getDay() === 0 || new Date().getDay() === 6 ? 1 : 0,
            lecture_scale: 1.0,
          },
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setPrediction(data);
        try {
          const seriesRes = await fetchWithAuth(`${apiUrl}/predictions/congestion/series`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              room_id: selectedZoneId,
              room_type: roomType,
              building_id: buildingId || selectedZoneId,
              timestamp: new Date().toISOString(),
              avg: actualCount,
              capacity: cap,
              history: Array.from({ length: 50 }, () => actualCount),
              steps: 24,
              step_minutes: 30,
              context: {
                is_weekend: new Date().getDay() === 0 || new Date().getDay() === 6 ? 1 : 0,
                lecture_scale: 1.0,
              },
            }),
          });
          if (seriesRes.ok) {
            const sd = await seriesRes.json();
            setSeries(sd.points || []);
          }
        } catch {
          // non-fatal
        }
      } else {
        const errData = await res.json().catch(() => ({}));
        setError(errData.detail || "Prediction failed");
      }
    } catch (err) {
      console.error("ML Prediction fetch error:", err);
      setError("Service unavailable");
    } finally {
      setLoading(false);
    }
  }, [fetchWithAuth, isAuthenticated, isReady, occupancy, selectedZoneId, selectedZoneName, buildingId, currentOccupancy, totalCapacity]);

  useEffect(() => {
    const initialTimer = window.setTimeout(() => {
      void fetchPrediction();
    }, 0);

    const interval = window.setInterval(() => {
      void fetchPrediction();
    }, 60000); // Update every minute
    return () => {
      window.clearTimeout(initialTimer);
      clearInterval(interval);
    };
  }, [fetchPrediction]);

  if (!selectedZoneName.toLowerCase().includes("canteen") && !selectedZoneName.toLowerCase().includes("library")) {
    return null;
  }

  return (
    <div
      style={{
        marginTop: "16px",
        borderRadius: "16px",
        border: "1px solid rgba(151, 254, 237, 0.25)",
        background: "rgba(7, 25, 82, 0.4)",
        padding: "16px",
        display: "flex",
        flexDirection: "column",
        gap: "12px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
        <Brain size={16} color="#97FEED" />
        <span
          style={{
            fontSize: "10px",
            fontWeight: 800,
            color: "#97FEED",
            textTransform: "uppercase",
            letterSpacing: "1px",
          }}
        >
          XGBoost Insights
        </span>
      </div>
      {loading && (
        <div style={{ fontSize: "8px", opacity: 0.6, color: "#fff", marginTop: "-8px" }}>
          ANALYZING...
        </div>
      )}

      {error ? (
        <div style={{ fontSize: "11px", color: "rgba(235, 9, 9, 0.8)" }}>
          {error}
        </div>
      ) : prediction ? (
        <>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ display: "flex", flexDirection: "column" }}>
              <span style={{ fontSize: "9px", color: "rgba(151, 254, 237, 0.6)" }}>PREDICTED OCCUPANCY</span>
              <span style={{ fontSize: "20px", fontWeight: 800, color: "#fff" }}>
                {Math.round(prediction.predicted_avg)} people
              </span>
            </div>
            <div
              style={{
                width: "40px",
                height: "40px",
                borderRadius: "50%",
                background: "rgba(151, 254, 237, 0.1)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                border: "1px solid rgba(151, 254, 237, 0.2)",
              }}
            >
              <TrendingUp size={20} color="#97FEED" />
            </div>
          </div>

          <div
            style={{
              fontSize: "10px",
              color: "rgba(151, 254, 237, 0.8)",
              background: "rgba(0,0,0,0.2)",
              padding: "8px",
              borderRadius: "8px",
              lineHeight: 1.4,
            }}
          >
            Trend: {prediction.predicted_avg > prediction.actual_avg ? "Increasing" : "Decreasing"}
            ({Math.abs(Math.round(prediction.predicted_avg - prediction.actual_avg))} people shift expected)
          </div>
          {series.length > 1 && (
            <div style={{ background: "rgba(0,0,0,0.25)", borderRadius: 8, padding: 8 }}>
              <div style={{ fontSize: 9, color: "rgba(151,254,237,0.7)", marginBottom: 4 }}>
                NEXT {series.length * 30 / 60}H FORECAST
              </div>
              <Sparkline points={series} capacity={totalCapacity ?? 100} />
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, color: "rgba(151,254,237,0.6)", marginTop: 2 }}>
                <span>now</span>
                <span>peak {Math.round(Math.max(...series.map((p) => p.predicted_avg)))}</span>
                <span>+{series.length * 30 / 60}h</span>
              </div>
            </div>
          )}
        </>
      ) : (
        <div style={{ fontSize: "11px", color: "rgba(151, 254, 237, 0.5)" }}>
          Waiting for sensor history...
        </div>
      )}
    </div>
  );
}
