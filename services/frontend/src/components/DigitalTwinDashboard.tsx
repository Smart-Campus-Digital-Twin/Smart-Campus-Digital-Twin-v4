"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { Canvas } from "@react-three/fiber";
import * as THREE from "three";
import { Navigation, Eye } from "lucide-react";
import { STABLE_INITIAL_ZONES, Zone } from "./dashboard/DashboardTypes";
import DashboardSidebar from "./dashboard/DashboardSidebar";
import DashboardHeader from "./dashboard/DashboardHeader";
import DashboardScene, { type TimeOfDay } from "./dashboard/DashboardScene";
import { useAuth } from "@/components/auth/KeycloakProvider";

export default function DigitalTwinDashboard() {
  const { fetchWithAuth, isReady, isAuthenticated } = useAuth();
  const [zones, setZones] = useState<Zone[]>(STABLE_INITIAL_ZONES);
  const [selectedId, setSelectedId] = useState<string>("it");
  const [walkMode, setWalkMode] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [expandedCategories, setExpandedCategories] = useState<string[]>([
    "Departments",
  ]);
  const [runMode, setRunMode] = useState(false);
  const [isLandscape, setIsLandscape] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [timeOfDay, setTimeOfDay] = useState<TimeOfDay>("day");
  const sceneSectionRef = useRef<HTMLElement | null>(null);

  const toggleCategory = (category: string) => {
    setExpandedCategories((prev) =>
      prev.includes(category)
        ? prev.filter((c) => c !== category)
        : [...prev, category],
    );
  };

  const categories = {
    Departments: [
      "cse",
      "it",
      "civil",
      "textile",
      "transport",
      "electronics",
      "maths",
      "medicine",
      "material",
      "chemical",
      "mechanical",
      "intdesign",
      "graduate",
      "buildeco",
    ],
    Canteens: ["Goda canteen", "Sentra", "canteen", "wala_canteen"],
    Hostels: ["hostel_a", "hostel"],
    "Admin & Services": ["admin", "registrar", "library"],
    Facilities: ["lagaan", "conference", "na1"],
  };

  useEffect(() => {
    if (!isReady || !isAuthenticated) {
      return;
    }

    const fetchZones = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || "/api";
        const res = await fetchWithAuth(`${apiUrl}/campus/zones`);
        if (res.ok) {
          const data = await res.json();
          if (Array.isArray(data) && data.length > 0) {
            setZones(data);
          }
        }
      } catch (err) {
        console.error("Failed to fetch zones:", err);
      }
    };

    fetchZones();
    const t = setInterval(fetchZones, 2000);
    return () => clearInterval(t);
  }, [isAuthenticated, isReady]);

  useEffect(() => {
    const check = () => {
      const w = window.innerWidth;
      const h = window.innerHeight;
      const mobile = w < 1024;
      const landscape = mobile && w > h;

      setIsMobile(mobile);
      setIsLandscape(landscape);

      if (landscape) {
        setSidebarOpen(false);
      } else {
        setSidebarOpen(!mobile);
      }
    };
    check();
    window.addEventListener("resize", check);
    window.addEventListener("orientationchange", check);
    return () => {
      window.removeEventListener("resize", check);
      window.removeEventListener("orientationchange", check);
    };
  }, []);

  useEffect(() => {
    if (isLandscape) {
      document.body.classList.add("full-screen-landscape");
    } else {
      document.body.classList.remove("full-screen-landscape");
    }
    return () => {
      document.body.classList.remove("full-screen-landscape");
    };
  }, [isLandscape]);

  useEffect(() => {
    const onFullscreenChange = () => {
      setIsFullscreen(Boolean(document.fullscreenElement));
    };

    document.addEventListener("fullscreenchange", onFullscreenChange);
    return () => {
      document.removeEventListener("fullscreenchange", onFullscreenChange);
    };
  }, []);

  useEffect(() => {
    if (!isLandscape && document.fullscreenElement) {
      document.exitFullscreen().catch(() => {
        // Ignore exit errors when fullscreen is unavailable on device/browser.
      });
    }
  }, [isLandscape]);

  const toggleWalkMode = useCallback(() => {
    setWalkMode((v) => !v);
  }, []);

  const toggleFullscreen = useCallback(async () => {
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
        return;
      }

      const sceneEl = sceneSectionRef.current;
      if (sceneEl) {
        await sceneEl.requestFullscreen().catch((err) => {
          console.warn("Fullscreen request failed:", err);
          // Fullscreen API may be restricted on some mobile browsers or by user permissions
        });
      }
    } catch (error) {
      console.error("Fullscreen toggle error:", error);
    }
  }, []);

  const campusLoad = zones.reduce((a, z) => a + z.energyKw, 0);
  const campusOcc = Math.round(
    zones.reduce((a, z) => a + z.occupancy, 0) / zones.length,
  );
  const criticalCount = zones.filter((z) => z.status === "critical").length;

  const filteredZones = zones.filter((z) =>
    z.name.toLowerCase().includes(searchQuery.toLowerCase()),
  );

  const showToolbarMenu = isMobile && !isLandscape;

  const topInset = isLandscape ? 64 : isMobile ? 68 : 64;

  // Shared button style for landscape mode controls
  const landscapeButtonStyle = {
    position: "absolute" as const,
    zIndex: 11000,
    background: "rgba(11, 102, 106, 0.9)",
    border: "1px solid rgba(151, 254, 237, 0.3)",
    color: "#97FEED",
    padding: "8px 12px",
    borderRadius: "8px",
    fontSize: "12px",
    fontWeight: "bold",
    cursor: "pointer",
    backdropFilter: "blur(5px)",
    boxShadow: "0 4px 15px rgba(0,0,0,0.5)",
  } as const;

  return (
    <div
      style={{
        display: "flex",
        minHeight: "100dvh",
        width: "100%",
        background:
          "radial-gradient(circle at center, #0B666A 0%, #071952 100%)",
        overflowX: "hidden",
        overflowY: "auto",
        color: "#fff",
        fontFamily: "'Inter', 'Segoe UI', system-ui, sans-serif",
        paddingTop: `${topInset}px`,
        flexDirection: isMobile ? "column" : "row",
        position: "relative",
      }}
    >
      <style>{`
        body.full-screen-landscape nav,
        body.full-screen-landscape footer {
          display: none !important;
        }
        body.full-screen-landscape main {
          padding: 0 !important;
          margin: 0 !important;
        }
      `}</style>
      {!isLandscape && (
        <DashboardSidebar
          zones={zones}
          filteredZones={filteredZones}
          selectedId={selectedId}
          setSelectedId={setSelectedId}
          searchQuery={searchQuery}
          setSearchQuery={setSearchQuery}
          expandedCategories={expandedCategories}
          toggleCategory={toggleCategory}
          categories={categories}
          isMobile={isMobile}
          sidebarOpen={sidebarOpen}
          setSidebarOpen={setSidebarOpen}
          isLandscape={isLandscape}
        />
      )}

      {isLandscape && (
        <>
          <button
            onClick={() => setSidebarOpen(true)}
            style={{ ...landscapeButtonStyle, top: 12, left: 20 }}
          >
            MENU
          </button>

          <button
            onClick={() => {
              toggleFullscreen().catch(() => {
                // Fullscreen API may be restricted on some mobile browsers.
              });
            }}
            style={{ ...landscapeButtonStyle, top: 12, right: 20 }}
          >
            {isFullscreen ? "EXIT FULL" : "FULL SCREEN"}
          </button>
        </>
      )}

      {isLandscape && sidebarOpen && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            width: "100%",
            height: "100%",
            zIndex: 10500,
            background: "rgba(0,0,0,0.5)",
            backdropFilter: "blur(3px)",
          }}
          onClick={() => setSidebarOpen(false)}
        >
          <div
            style={{ width: "280px", height: "100%" }}
            onClick={(e) => e.stopPropagation()}
          >
            <DashboardSidebar
              zones={zones}
              filteredZones={filteredZones}
              selectedId={selectedId}
              setSelectedId={setSelectedId}
              searchQuery={searchQuery}
              setSearchQuery={setSearchQuery}
              expandedCategories={expandedCategories}
              toggleCategory={toggleCategory}
              categories={categories}
              isMobile={true}
              sidebarOpen={true}
              setSidebarOpen={setSidebarOpen}
              isLandscape={true}
            />
          </div>
        </div>
      )}

      <main
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          padding: isLandscape ? 0 : isMobile ? 8 : 24,
          gap: isLandscape ? 0 : isMobile ? 8 : 24,
          overflow: "hidden",
          height: "100dvh",
          position: "sticky",
          top: 0,
        }}
      >
        {!isLandscape && (
          <DashboardHeader
            campusLoad={campusLoad}
            campusOcc={campusOcc}
            activeZonesCount={zones.length}
            criticalCount={criticalCount}
            isMobile={isMobile}
          />
        )}

        <section
          ref={sceneSectionRef}
          style={{
            flex: 1,
            borderRadius: isLandscape ? 0 : isMobile ? 12 : 14,
            border: isLandscape ? "none" : "1px solid rgba(53,162,159,0.3)",
            overflow: "hidden",
            position: "relative",
            minHeight: 0,
          }}
        >
          {/* Toolbar */}
          <div
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              right: 0,
              zIndex: 5000,
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              background: "rgba(11,102,106,0.8)",
              borderBottom: "1px solid rgba(53,162,159,0.4)",
              padding: isMobile ? "10px 12px" : "7px 14px",
              fontSize: 10,
              textTransform: "uppercase",
              letterSpacing: "0.16em",
              color: "#97FEED",
              fontWeight: 700,
              gap: 8,
            }}
          >
            {showToolbarMenu && (
              <button
                onClick={() => setSidebarOpen((s) => !s)}
                style={{
                  marginRight: 8,
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
                Menu
              </button>
            )}
            <span style={{ flex: "1 1 180px", minWidth: 0, lineHeight: 1.3 }}>
              3D Campus Twin — University of Moratuwa
            </span>
            <div
              style={{
                display: "flex",
                gap: 8,
                alignItems: "center",
                flexWrap: "wrap",
                justifyContent: isMobile ? "flex-start" : "flex-end",
              }}
            >
              {walkMode && !isMobile && (
                <span style={{ fontSize: 9, color: "#FAC75A", opacity: 0.9 }}>
                  Click canvas → WASD/Arrow keys to move · Mouse to look · Shift
                  to run · Esc to exit
                </span>
              )}
              {walkMode && isMobile && (
                <button
                  onClick={() => setRunMode((v) => !v)}
                  style={{
                    padding: "4px 8px",
                    borderRadius: 4,
                    background: runMode ? "#FF4B2B" : "rgba(7,25,82,0.6)",
                    border: "1px solid rgba(255, 75, 43, 0.3)",
                    color: "#fff",
                    fontSize: 8,
                    fontWeight: 800,
                    cursor: "pointer",
                  }}
                >
                  RUN {runMode ? "ON" : "OFF"}
                </button>
              )}
              {(["day", "evening", "night"] as TimeOfDay[]).map((t) => (
                <button
                  key={t}
                  onClick={() => setTimeOfDay(t)}
                  style={{
                    padding: "4px 10px",
                    borderRadius: 6,
                    background: timeOfDay === t ? "#97FEED" : "rgba(7,25,82,0.6)",
                    border: "1px solid rgba(151,254,237,0.3)",
                    color: timeOfDay === t ? "#071952" : "#fff",
                    fontSize: 9,
                    fontWeight: 800,
                    cursor: "pointer",
                    textTransform: "uppercase",
                  }}
                >
                  {t}
                </button>
              ))}
              <button
                onClick={() => {
                  toggleFullscreen().catch(() => {});
                }}
                style={{
                  padding: "4px 10px",
                  borderRadius: 6,
                  background: isFullscreen ? "#FAC75A" : "rgba(7,25,82,0.6)",
                  border: "1px solid rgba(151,254,237,0.3)",
                  color: isFullscreen ? "#071952" : "#fff",
                  fontSize: 9,
                  fontWeight: 800,
                  cursor: "pointer",
                }}
              >
                {isFullscreen ? "EXIT FULL" : "FULL SCREEN"}
              </button>
              <button
                onClick={toggleWalkMode}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "4px 10px",
                  borderRadius: 6,
                  background: walkMode ? "#FAC75A" : "rgba(7,25,82,0.6)",
                  border: "1px solid rgba(151,254,237,0.3)",
                  color: walkMode ? "#071952" : "#fff",
                  fontSize: 9,
                  fontWeight: 800,
                  cursor: "pointer",
                }}
              >
                {walkMode ? <Navigation size={12} /> : <Eye size={12} />}
                {walkMode ? "EXIT WALK MODE" : "FIRST-PERSON VIEW"}
              </button>
            </div>
          </div>

          <Canvas
            shadows={{ type: THREE.PCFShadowMap }}
            style={{ width: "100%", height: "100%", touchAction: "none" }}
            dpr={isMobile ? [1, 1.5] : [1, 2]}
            camera={
              isMobile
                ? { position: [22, 22, 22], fov: 50 }
                : { position: [20, 20, 20], fov: 40 }
            }
          >
            <DashboardScene
              zones={zones}
              selectedId={selectedId}
              onSelect={setSelectedId}
              walkMode={walkMode}
              isMobile={isMobile}
              runMode={runMode}
              timeOfDay={timeOfDay}
            />
          </Canvas>

          {isMobile && walkMode && (
            <div
              style={{
                position: "absolute",
                bottom: 40,
                left: 0,
                right: 0,
                zIndex: 5000,
                display: "flex",
                justifyContent: "space-around",
                pointerEvents: "none",
                opacity: 0.6,
                padding: "0 20px",
              }}
            >
              <div style={{ textAlign: "center" }}>
                <div
                  style={{
                    width: 50,
                    height: 50,
                    borderRadius: "50%",
                    border: "2px dashed #97FEED",
                    margin: "0 auto 8px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  <div
                    style={{
                      width: 10,
                      height: 10,
                      borderRadius: "50%",
                      background: "#97FEED",
                    }}
                  />
                </div>
                <span
                  style={{ fontSize: 9, color: "#97FEED", fontWeight: 700 }}
                >
                  MOVE
                </span>
              </div>
              <div style={{ textAlign: "center" }}>
                <div
                  style={{
                    width: 50,
                    height: 50,
                    borderRadius: "50%",
                    border: "2px dashed #97FEED",
                    margin: "0 auto 8px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  <Eye size={16} color="#97FEED" />
                </div>
                <span
                  style={{ fontSize: 9, color: "#97FEED", fontWeight: 700 }}
                >
                  LOOK
                </span>
              </div>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
