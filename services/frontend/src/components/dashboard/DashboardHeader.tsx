import React from "react";
import { usePrefersReducedMotion } from "@/app/hooks/usePrefersReducedMotion";

interface DashboardHeaderProps {
  campusLoad: number;
  campusOcc: number;
  activeZonesCount: number;
  criticalCount: number;
  isMobile?: boolean;
}

export default function DashboardHeader({
  campusLoad,
  campusOcc,
  activeZonesCount,
  criticalCount,
  isMobile = false,
}: DashboardHeaderProps) {
  const prefersReducedMotion = usePrefersReducedMotion();
  return (
    <header
      style={{
        display: "flex",
        flexDirection: isMobile ? "column" : "row",
        justifyContent: "space-between",
        alignItems: isMobile ? "flex-start" : "flex-end",
        background: "rgba(11, 102, 106, 0.15)",
        backdropFilter: "blur(10px)",
        padding: isMobile ? "10px 14px" : "24px 30px",
        borderRadius: isMobile ? 16 : 24,
        border: "1px solid rgba(151, 254, 237, 0.2)",
        boxShadow: "0 10px 30px rgba(0,0,0,0.2)",
        gap: isMobile ? 16 : 24,
      }}
    >
      <div>
        <p
          style={{
            fontSize: isMobile ? 9 : 11,
            color: "#97FEED",
            fontWeight: 800,
            letterSpacing: "2px",
            textTransform: "uppercase",
            opacity: 0.8,
          }}
        >
          University of Moratuwa
        </p>
        <h1
          style={{
            fontSize: isMobile ? 24 : 42,
            fontWeight: 900,
            color: "#fff",
            letterSpacing: "-1.5px",
            margin: "4px 0",
            textShadow: "0 4px 20px rgba(151, 254, 237, 0.3)",
          }}
        >
          Smart Campus <span style={{ color: "#97FEED" }}>Twin Control</span>
        </h1>
        {!isMobile && (
          <p
            style={{
              color: "rgba(151, 254, 237, 0.6)",
              fontSize: 13,
              fontWeight: 500,
            }}
          >
            Real-time 3D campus infrastructure monitoring · occupancy ·
            temperature · energy states
          </p>
        )}
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: isMobile ? "repeat(2, 1fr)" : "repeat(4, auto)",
          gap: isMobile ? 8 : 16,
          width: isMobile ? "100%" : "auto",
        }}
      >
        {[
          { label: "CAMPUS ENERGY", value: `${campusLoad.toFixed(1)} kW` },
          { label: "AVG OCCUPANCY", value: `${campusOcc}%` },
          { label: "ACTIVE ZONES", value: `${activeZonesCount}` },
        ].map((stat, i) => (
          <div
            key={i}
            role="region"
            aria-label={`${stat.label}: ${stat.value}`}
            style={{
              background: "rgba(7, 25, 82, 0.4)",
              border: "1px solid rgba(151, 254, 237, 0.2)",
              padding: isMobile ? "8px 12px" : "12px 20px",
              borderRadius: 16,
              minWidth: isMobile ? 0 : 140,
            }}
          >
            <p
              style={{
                fontSize: isMobile ? 8 : 9,
                fontWeight: 800,
                color: "rgba(151, 254, 237, 0.5)",
                marginBottom: 4,
              }}
            >
              {stat.label}
            </p>
            <p
              style={{
                fontSize: isMobile ? 14 : 18,
                fontWeight: 800,
                color: "#97FEED",
              }}
            >
              {stat.value}
            </p>
          </div>
        ))}

        <div
          style={{
            background:
              criticalCount > 0
                ? "rgba(232, 93, 36, 0.15)"
                : "rgba(7, 25, 82, 0.4)",
            border: `1px solid ${criticalCount > 0 ? "rgba(235, 9, 9, 0.6)" : "rgba(151, 254, 237, 0.2)"}`,
            padding: isMobile ? "8px 12px" : "12px 20px",
            borderRadius: 16,
            minWidth: isMobile ? 0 : 140,
            animation:
              criticalCount > 0 && !prefersReducedMotion
                ? "alertPulse 1.8s ease-in-out infinite"
                : "none",
            boxShadow:
              criticalCount > 0 ? "0 0 20px rgba(235, 9, 9, 0.15)" : "none",
            transition: prefersReducedMotion
              ? "none"
              : "background 0.4s, border 0.4s, box-shadow 0.4s",
          }}
        >
          <p
            style={{
              fontSize: isMobile ? 8 : 9,
              fontWeight: 800,
              color: "rgba(151, 254, 237, 0.5)",
              marginBottom: 4,
            }}
          >
            ALERTS
          </p>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {criticalCount > 0 && (
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: "#eb0909",
                  animation: !prefersReducedMotion
                    ? "dotFlash 0.9s ease-in-out infinite"
                    : "none",
                  flexShrink: 0,
                }}
              />
            )}
            <p
              style={{
                fontSize: isMobile ? 14 : 18,
                fontWeight: 800,
                color: criticalCount > 0 ? "#eb0909" : "#97FEED",
              }}
            >
              {criticalCount > 0 ? `${criticalCount} critical` : "None"}
            </p>
          </div>
        </div>
      </div>
      <style>{`
        @keyframes alertPulse {
          0%, 100% { opacity: 1; box-shadow: 0 0 20px rgba(235, 9, 9, 0.3); }
          50% { opacity: 0.7; box-shadow: 0 0 35px rgba(235, 9, 9, 0.7); }
        }
        @keyframes dotFlash {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.2; }
        } 
      `}</style>
    </header>
  );
}
