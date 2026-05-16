import React from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useRouter } from "next/navigation";
import { Zone, STATUS_COLORS } from "./DashboardTypes";
import { BUILDING_DATA } from "../indoor/FloorData";
import { usePrefersReducedMotion } from "@/app/hooks/usePrefersReducedMotion";
import { useAnimatedValue } from "@/app/hooks/useAnimatedValue";
import MLPredictionPanel from "./MLPredictionPanel";
import SensorHealthPanel from "./SensorHealthPanel";
import AnomalyPanel from "./AnomalyPanel";

interface DashboardSidebarProps {
  zones: Zone[];
  filteredZones: Zone[];
  selectedId: string;
  setSelectedId: (id: string) => void;
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  expandedCategories: string[];
  toggleCategory: (category: string) => void;
  categories: Record<string, string[]>;
  isMobile?: boolean;
  sidebarOpen?: boolean;
  setSidebarOpen?: (open: boolean) => void;
  isLandscape?: boolean;
}

export default function DashboardSidebar({
  zones,
  filteredZones,
  selectedId,
  setSelectedId,
  searchQuery,
  setSearchQuery,
  expandedCategories,
  toggleCategory,
  categories,
  isMobile = false,
  sidebarOpen = true,
  setSidebarOpen,
  isLandscape = false,
}: DashboardSidebarProps) {
  const router = useRouter();
  const selectedZone = zones.find((z) => z.id === selectedId) ?? zones[0];

  const prefersReducedMotion = usePrefersReducedMotion();
  const animatedEnergyValue = useAnimatedValue(selectedZone.energyKw, 1);
  const animatedOccupancyValue = useAnimatedValue(selectedZone.occupancy, 0);
  const animatedTempValue = useAnimatedValue(selectedZone.temperatureC, 1);
  const animatedEnergy = prefersReducedMotion ? selectedZone.energyKw : animatedEnergyValue;
  const animatedOccupancy = prefersReducedMotion
    ? selectedZone.occupancy
    : animatedOccupancyValue;
  const animatedTemp = prefersReducedMotion ? selectedZone.temperatureC : animatedTempValue;

  const navStyle: React.CSSProperties = {
    width: isMobile ? "84%" : "320px",
    maxWidth: isMobile ? 360 : undefined,
    flexShrink: 0,
    background: "rgba(11, 102, 106, 0.12)",
    backdropFilter: "blur(15px)",
    borderRight: isMobile ? "none" : "1px solid rgba(151, 254, 237, 0.15)",
    display: "flex",
    flexDirection: "column",
    padding: isMobile ? "14px" : "20px 16px",
    gap: "16px",
    overflowY: "auto",
    boxShadow: isMobile
      ? "-4px 0 30px rgba(0,0,0,0.6)"
      : "10px 0 30px rgba(0,0,0,0.3)",
    position: isMobile ? "fixed" : "relative",
    top: isMobile ? (isLandscape ? 0 : 64) : undefined,
    left: isMobile ? (sidebarOpen ? 0 : "-120%") : undefined,
    height: isMobile
      ? isLandscape
        ? "100vh"
        : "calc(100vh - 64px)"
      : undefined,
    transition: isMobile ? "left 200ms ease" : undefined,
    zIndex: 11000,
  };

  return (
    <nav style={navStyle}>
      {isMobile && setSidebarOpen && (
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <button
            onClick={() => setSidebarOpen(false)}
            style={{
              padding: "8px 10px",
              borderRadius: 8,
              background: "rgba(7,25,82,0.6)",
              color: "#97FEED",
              border: "1px solid rgba(151,254,237,0.15)",
              fontSize: 14,
              fontWeight: 800,
              cursor: "pointer",
            }}
          >
            Close
          </button>
        </div>
      )}
      <style>{`
        @keyframes sidebarDotFlash {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.15; }
        }
      `}</style>
      {/* Search */}
      <input
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        aria-label="Search zones"
        placeholder="Search zones..."
        style={{
          background: "rgba(7,25,82,0.5)",
          border: "1px solid rgba(53,162,159,0.3)",
          borderRadius: 8,
          padding: isMobile ? "10px 12px" : "7px 10px",
          color: "#fff",
          fontSize: isMobile ? 14 : 11,
          outline: "none",
        }}
      />

      {/* Zone list */}
      <p
        style={{
          fontSize: 9,
          textTransform: "uppercase",
          letterSpacing: "0.18em",
          color: "#97FEED",
          fontWeight: 700,
          marginBottom: 4,
        }}
      >
        Zone Status Panel ({filteredZones.length})
      </p>

      <div
        style={{
          flex: 1,
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          gap: 10,
        }}
      >
        {Object.entries(categories).map(([category, zoneIds]) => {
          const zonesInCategory = filteredZones.filter((z) =>
            zoneIds.includes(z.id),
          );
          if (zonesInCategory.length === 0) return null;

          const isExpanded = expandedCategories.includes(category);

          const criticalZonesCount = zonesInCategory.reduce(
            (count, z) => (z.status === "critical" ? count + 1 : count),
            0,
          );

          return (
            <div
              key={category}
              style={{ display: "flex", flexDirection: "column", gap: 4 }}
            >
              <button
                onClick={() => toggleCategory(category)}
                style={{
                  background: "none",
                  border: "none",
                  color: "#97FEED",
                  fontSize: 10,
                  fontWeight: 700,
                  textTransform: "uppercase",
                  letterSpacing: "0.1em",
                  display: "flex",
                  alignItems: "center",
                  gap: 4,
                  padding: "4px 0",
                  cursor: "pointer",
                  textAlign: "left",
                }}
              >
                {isExpanded ? (
                  <ChevronDown size={12} />
                ) : (
                  <ChevronRight size={12} />
                )}
                {category} ({zonesInCategory.length})
                {criticalZonesCount > 0 && (
                  <span
                    style={{
                      marginLeft: "auto",
                      background: "#f50707",
                      color: "#fff",
                      fontSize: 8,
                      fontWeight: 800,
                      padding: "1px 5px",
                      borderRadius: 4,
                      letterSpacing: "0.05em",
                    }}
                  >
                    {criticalZonesCount} CRITICAL
                  </span>
                )}
              </button>

              {isExpanded && (
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
                    gap: 4,
                    paddingLeft: 4,
                  }}
                >
                  {zonesInCategory.map((zone) => {
                    const active = zone.id === selectedId;
                    return (
                      <button
                        key={zone.id}
                        onClick={() => setSelectedId(zone.id)}
                        style={{
                          background: active
                            ? "rgba(11,102,106,0.85)"
                            : "rgba(7,25,82,0.35)",
                          border: `1px solid ${active ? "#97FEED" : "rgba(53,162,159,0.18)"}`,
                          borderRadius: 8,
                          padding: isMobile ? "10px 12px" : "6px 8px",
                          cursor: "pointer",
                          display: "flex",
                          alignItems: "center",
                          gap: 4,
                          transition: "all 0.2s",
                          textAlign: "left",
                          minWidth: 0,
                        }}
                      >
                        <span
                          style={{
                            width: "6px",
                            height: "6px",
                            borderRadius: "50%",
                            background: zone.hasData ? STATUS_COLORS[zone.status] : "#555",
                            boxShadow: zone.hasData ? `0 0 ${zone.status === "critical" ? "6px" : "3px"} ${STATUS_COLORS[zone.status]}` : "none",
                            flexShrink: 0,
                            animation:
                              zone.hasData &&
                              zone.status === "critical" &&
                              !prefersReducedMotion
                                ? "sidebarDotFlash 0.9s ease-in-out infinite"
                                : "none",
                          }}
                        />
                        <span
                          style={{
                            fontSize: isMobile ? 14 : 8,
                            color: "#fff",
                            lineHeight: 1.2,
                            flex: 1,
                            minWidth: 0,
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                          }}
                        >
                          {zone.name}
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Zone detail HUD */}
      <div
        style={{
          borderRadius: "20px",
          border: "1px solid rgba(151, 254, 237, 0.4)",
          background:
            "linear-gradient(135deg, rgba(11, 102, 106, 0.4) 0%, rgba(7, 25, 82, 0.6) 100%)",
          backdropFilter: "blur(10px)",
          padding: "20px",
          flexShrink: 0,
          boxShadow:
            "0 10px 30px rgba(0,0,0,0.4), inset 0 0 20px rgba(151, 254, 237, 0.1)",
        }}
      >
        <p
          style={{
            fontSize: 10,
            color: "#97FEED",
            fontWeight: 800,
            textTransform: "uppercase",
            letterSpacing: "1.5px",
            marginBottom: 6,
            opacity: 0.8,
          }}
        >
          Selected Zone
        </p>
        <h2
          style={{
            fontSize: 22,
            fontWeight: 800,
            marginBottom: 16,
            lineHeight: 1.2,
            color: "#fff",
            letterSpacing: "-0.5px",
          }}
        >
          {selectedZone.name}
        </h2>
        <div
          style={{
            background: "rgba(0,0,0,0.3)",
            borderRadius: 12,
            border: "1px solid rgba(151, 254, 237, 0.15)",
            padding: 16,
            display: "flex",
            flexDirection: "column",
            gap: 10,
            fontSize: 13,
          }}
        >
          {[
            [
              "STATUS",
              selectedZone.hasData ? selectedZone.status.toUpperCase() : "NO DATA",
              selectedZone.hasData ? STATUS_COLORS[selectedZone.status] : "#888",
            ],
            ["Avg. Energy",    selectedZone.hasData ? `${animatedEnergy.toFixed(1)} kW` : "—",    "#97FEED"],
            [
              "Occupancy",
              selectedZone.hasData
                ? `${selectedZone.currentOccupancy ?? 0} / ${selectedZone.totalCapacity ?? 0} (${animatedOccupancy}% capped, ${selectedZone.occupancyTheoretical ?? animatedOccupancy}% raw)`
                : "—",
              "#97FEED",
            ],
            ["Avg. Temp",      selectedZone.hasData ? `${animatedTemp.toFixed(1)}°C` : "—",       "#97FEED"],
          ].map(([label, value, color], i) => (
            <div
              key={i}
              style={{
                display: "flex",
                justifyContent: "space-between",
                paddingBottom: i < 3 ? 8 : 0,
                borderBottom: i < 3 ? "1px solid rgba(53,162,159,0.2)" : "none",
              }}
            >
              <span style={{ color: "#97FEED" }}>{label}</span>
              <span style={{ color, fontWeight: 700 }}>{value}</span>
            </div>
          ))}
        </div>
        <div style={{ marginTop: 12 }}>
          <div
            style={{
              fontSize: 9,
              color: "#fff",
              fontWeight: 700,
              textTransform: "uppercase",
              letterSpacing: "0.1em",
              marginBottom: 5,
            }}
          >
            Capacity
          </div>
          <div
            style={{
              height: "10px",
              borderRadius: "5px",
              background: "rgba(7,25,82,0.8)",
              border: "1px solid rgba(53,162,159,0.35)",
              padding: "2px",
            }}
          >
            <div
              style={{
                height: "100%",
                borderRadius: "3px",
                background: STATUS_COLORS[selectedZone.status],
                width: selectedZone.hasData ? `${selectedZone.occupancy}%` : "0%",
                transition: "width 0.6s ease",
              }}
            />
          </div>
        </div>
        {Object.keys(BUILDING_DATA).includes(selectedId) && (
          <button
            onClick={() => {
              router.push(`/building/${selectedId}`);
            }}
            style={{
              marginTop: 14,
              width: "100%",
              padding: isMobile ? "14px" : "10px",
              borderRadius: 10,
              border: "none",
              cursor: "pointer",
              fontWeight: 800,
              background: "#97FEED",
              color: "#071952",
            }}
          >
            Go Inside
          </button>
        )}
        
        <MLPredictionPanel
          selectedZoneId={selectedId}
          selectedZoneName={selectedZone.name}
          occupancy={selectedZone.occupancy}
          buildingId={selectedZone.buildingId}
          totalCapacity={selectedZone.totalCapacity}
          currentOccupancy={selectedZone.currentOccupancy}
        />
      </div>
      <SensorHealthPanel buildingId={selectedZone.buildingId} />
      <AnomalyPanel />
    </nav>
  );
}
