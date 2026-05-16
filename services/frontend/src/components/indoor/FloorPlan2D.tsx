"use client";

import { useEffect, useState, useMemo } from "react";
import { Floor } from "./FloorData";
import { useAuth } from "@/components/auth/KeycloakProvider";

type Props = {
  buildingId?: string;
  floor: Floor;
  floorNumber: number;
  minFloor?: number;
  maxFloor: number;
  goUp: () => void;
  goDown: () => void;
  isMobile?: boolean;
};

type RoomStats = {
  temp: number;
  occ: number;
};

export default function FloorPlan2D({
  buildingId,
  floor,
  floorNumber,
  minFloor = 0,
  maxFloor,
  goUp,
  goDown,
  isMobile = false,
}: Props) {
  const { fetchWithAuth, isReady, isAuthenticated, token } = useAuth();
  const createInitialStats = () => {
    const initialStats: Record<string, RoomStats> = {};

    floor.rooms.forEach((room) => {
      if (room.type !== "stairs" && room.type !== "free") {
        initialStats[room.id] = {
          temp: 24 + Math.random() * 6,
          occ: 20 + Math.random() * 60,
        };
      }
    });

    return initialStats;
  };

  const [stats, setStats] = useState<Record<string, RoomStats>>(() => createInitialStats());
  const [hoveredRoom, setHoveredRoom] = useState<string | null>(null);
  const [isMobileView, setIsMobileView] = useState(isMobile);
  const [dynamicScale, setDynamicScale] = useState(isMobile ? 0.4 : 1.25);
  const [userZoom, setUserZoom] = useState(1);
  const [isPanning, setIsPanning] = useState(false);

  // Calculate the bounding box of all rooms to center them (memoized to prevent unnecessary recalculations)
  const bounds = useMemo(
    () => ({
      minX: Math.min(...floor.rooms.map((r) => r.x), 0),
      maxX: Math.max(...floor.rooms.map((r) => r.x + r.width), 800),
      minY: Math.min(...floor.rooms.map((r) => r.y), 0),
      maxY: Math.max(...floor.rooms.map((r) => r.y + r.height), 500),
    }),
    [floor.rooms],
  );

  useEffect(() => {
    const handleResize = () => {
      const isMobile = window.innerWidth < 1024;
      setIsMobileView(isMobile);

      const paddingW = isMobile ? 5 : 40;
      const paddingH = isMobile ? 5 : 60;
      const availableWidth = window.innerWidth - paddingW * 2;
      const availableHeight =
        (isMobile ? window.innerHeight * 0.7 : window.innerHeight * 0.8) -
        paddingH * 2;

      const contentWidth = bounds.maxX - bounds.minX;
      const contentHeight = bounds.maxY - bounds.minY;

      const scaleW = availableWidth / contentWidth;
      const scaleH = availableHeight / contentHeight;

      let scale = Math.min(scaleW, scaleH);
      if (!isMobile) scale = Math.min(scale, 1.25);

      setDynamicScale(scale);
    };

    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [bounds.maxX, bounds.minX, bounds.maxY, bounds.minY]);

  const SCALE = dynamicScale * userZoom;

  const planWidth = (bounds.maxX - bounds.minX) * SCALE;
  const planHeight = (bounds.maxY - bounds.minY) * SCALE;

  type RoomRow = {
    room_id: string;
    floor: number;
    temperature: number;
    occupancy: number;
  };

  useEffect(() => {
    if (!isReady || !isAuthenticated) return;

    const fetchRoomData = async () => {
      if (!buildingId) return;
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || "/api";
        const res = await fetchWithAuth(`${apiUrl}/campus/buildings/${buildingId}/rooms`);
        if (res.ok) {
          const data = await res.json();
          const newStats: Record<string, RoomStats> = {};
          data.forEach((room: RoomRow) => {
            if (room.floor === floorNumber) {
              newStats[room.room_id] = { temp: room.temperature, occ: room.occupancy };
            }
          });
          setStats((prev) => ({ ...prev, ...newStats }));
        }
      } catch (err) {
        console.error(`Failed to fetch room data for ${buildingId}:`, err);
      }
    };

    fetchRoomData();
    if (!buildingId) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsHost = process.env.NEXT_PUBLIC_WS_URL || `${protocol}//${window.location.host}`;
    const ws = new WebSocket(`${wsHost}/ws/buildings/${buildingId}?token=${token}`);
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "room_update" && data.floor === floorNumber) {
          setStats((prev) => ({
            ...prev,
            [data.room_id]: { temp: data.temperature, occ: data.occupancy },
          }));
        } else if (data.type === "ping") {
          ws.send(JSON.stringify({ type: "pong" }));
        }
      } catch {
        /* ignore parse errors */
      }
    };
    return () => ws.close();
  }, [buildingId, fetchWithAuth, floor, floorNumber, isAuthenticated, isReady, token]);

  return (
    <div
      style={{
        width: "100%",
        maxWidth: "100%",
        height: isMobileView ? "auto" : "auto",
        minHeight: isMobileView ? "40vh" : "auto",
        position: "relative",
        borderRadius: isMobileView ? "8px" : "24px",
        background: "rgba(11, 102, 106, 0.05)",
        backdropFilter: "blur(12px)",
        border: "1px solid rgba(151, 254, 237, 0.15)",
        boxShadow: "0 20px 40px -12px rgba(0, 0, 0, 0.5)",
        padding: isMobileView ? "5px" : "40px",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        alignItems: "center",
        transition: "all 0.3s ease",
        overflow: "hidden",
        touchAction: "pan-x pan-y",
      }}
    >
      {/* Zoom Controls */}
      <div
        style={{
          position: "absolute",
          top: isMobileView ? 10 : 20,
          right: isMobileView ? 10 : 20,
          zIndex: 100,
          display: "flex",
          gap: "8px",
        }}
      >
        <button
          onClick={() => setUserZoom((prev) => Math.min(prev + 0.2, 3))}
          style={{
            width: 32,
            height: 32,
            borderRadius: "6px",
            background: "rgba(7, 25, 82, 0.8)",
            color: "#97FEED",
            border: "1px solid #97FEED33",
            fontWeight: "bold",
            cursor: "pointer",
          }}
        >
          +
        </button>
        <button
          onClick={() => setUserZoom((prev) => Math.max(prev - 0.2, 0.5))}
          style={{
            width: 32,
            height: 32,
            borderRadius: "6px",
            background: "rgba(7, 25, 82, 0.8)",
            color: "#97FEED",
            border: "1px solid #97FEED33",
            fontWeight: "bold",
            cursor: "pointer",
          }}
        >
          -
        </button>
        <button
          onClick={() => setUserZoom(1)}
          style={{
            padding: "0 8px",
            height: 32,
            borderRadius: "6px",
            background: "rgba(7, 25, 82, 0.8)",
            color: "#97FEED",
            border: "1px solid #97FEED33",
            fontSize: "10px",
            fontWeight: "bold",
            cursor: "pointer",
          }}
        >
          RESET
        </button>
      </div>

      <div
        style={{
          width: "100%",
          height: isMobileView ? "75vh" : "100%",
          overflow: "auto",
          display: "flex",
          justifyContent: userZoom > 1 ? "flex-start" : "center",
          alignItems: userZoom > 1 ? "flex-start" : "center",
          cursor: isPanning ? "grabbing" : "grab",
          WebkitOverflowScrolling: "touch",
        }}
        onMouseDown={(e) => {
          const container = e.currentTarget;
          setIsPanning(true);
          container.dataset.panStartX = String(e.clientX);
          container.dataset.panStartY = String(e.clientY);
          container.dataset.panScrollLeft = String(container.scrollLeft);
          container.dataset.panScrollTop = String(container.scrollTop);
        }}
        onMouseMove={(e) => {
          if (!isPanning) return;

          const container = e.currentTarget;
          const panStartX = Number(container.dataset.panStartX);
          const panStartY = Number(container.dataset.panStartY);
          const panScrollLeft = Number(container.dataset.panScrollLeft);
          const panScrollTop = Number(container.dataset.panScrollTop);

          if (
            Number.isNaN(panStartX) ||
            Number.isNaN(panStartY) ||
            Number.isNaN(panScrollLeft) ||
            Number.isNaN(panScrollTop)
          ) {
            return;
          }

          container.scrollLeft = panScrollLeft - (e.clientX - panStartX);
          container.scrollTop = panScrollTop - (e.clientY - panStartY);
        }}
        onMouseUp={(e) => {
          const container = e.currentTarget;
          setIsPanning(false);
          delete container.dataset.panStartX;
          delete container.dataset.panStartY;
          delete container.dataset.panScrollLeft;
          delete container.dataset.panScrollTop;
        }}
        onMouseLeave={(e) => {
          const container = e.currentTarget;
          setIsPanning(false);
          delete container.dataset.panStartX;
          delete container.dataset.panStartY;
          delete container.dataset.panScrollLeft;
          delete container.dataset.panScrollTop;
        }}
      >
        <div
          style={{
            width: floor.planImage ? "100%" : Math.max(planWidth, 200),
            height: floor.planImage ? "100%" : Math.max(planHeight, 200),
            position: "relative",
            flexShrink: 0,
            margin: userZoom > 1 ? "20px" : "0",
          }}
        >
          {floor.planImage ? (
            <div
              style={{
                position: "relative",
                width: "100%",
                height: "100%",
                display: "flex",
                justifyContent: "center",
              }}
            >
              <img
                src={floor.planImage}
                alt={`Floor ${floorNumber} Plan`}
                style={{
                  maxWidth: userZoom > 1 ? "none" : "100%",
                  maxHeight:
                    userZoom > 1 ? "none" : isMobileView ? "60vh" : "70vh",
                  width: userZoom > 1 ? `${100 * userZoom}%` : "auto",
                  borderRadius: isMobileView ? "8px" : "16px",
                  objectFit: "contain",
                  boxShadow: "0 10px 30px rgba(0,0,0,0.5)",
                  border: "1px solid rgba(151, 254, 237, 0.2)",
                  transition: "width 0.3s ease",
                }}
              />
            </div>
          ) : (
            floor.rooms.map((room) => {
              const isHovered = hoveredRoom === room.id;
              const isStairs = room.type === "stairs";
              const isFree = room.type === "free";
              const isOpenArea = room.name === "Open Area";

              return (
                <div
                  key={room.id}
                  onMouseEnter={() => setHoveredRoom(room.id)}
                  onMouseLeave={() => setHoveredRoom(null)}
                  style={{
                    position: "absolute",
                    left: (room.x - bounds.minX) * SCALE,
                    top: (room.y - bounds.minY) * SCALE,
                    width: room.width * SCALE,
                    height: room.height * SCALE,
                    borderRadius: "0px",
                    border: isHovered
                      ? "2.5px solid #97FEED"
                      : "1.5px solid rgba(0, 0, 0, 0.8)",
                    background: isStairs
                      ? "linear-gradient(135deg, #FFD166 0%, #F5A623 100%)"
                      : isFree
                        ? "rgba(255, 255, 255, 0.05)"
                        : isOpenArea
                          ? "linear-gradient(135deg, rgba(144, 238, 144, 0.3) 0%, rgba(53, 162, 159, 0.4) 100%)"
                          : isHovered
                            ? "linear-gradient(135deg, rgba(151, 254, 237, 0.4) 0%, rgba(11, 102, 106, 0.8) 100%)"
                            : "linear-gradient(135deg, rgba(11, 102, 106, 0.75) 0%, rgba(7, 25, 82, 0.9) 100%)",
                    boxShadow: isHovered
                      ? "0 0 30px rgba(151, 254, 237, 0.5)"
                      : "0 6px 20px rgba(0,0,0,0.3)",
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "center",
                    alignItems: "center",
                    padding: "4px",
                    transition: "all 0.3s ease",
                    cursor: "pointer",
                    zIndex: isHovered ? 10 : 1,
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      textAlign: "center",
                      color: isHovered ? "#97FEED" : "#fff",
                      textShadow: "0 2px 4px rgba(0,0,0,0.3)",
                    }}
                  >
                    <div
                      style={{
                        fontWeight: 700,
                        fontSize: isMobileView
                          ? `${Math.min(9, Math.max(6, room.width * SCALE * 0.07))}px`
                          : `clamp(10px, ${room.width * SCALE * 0.12}px, 15px)`,
                        textTransform: "uppercase",
                        letterSpacing: "0.4px",
                        lineHeight: 1.0,
                        wordBreak: "break-word",
                        whiteSpace: "normal",
                        width: "100%",
                        padding: "0 1px",
                        display: room.width * SCALE < 15 ? "none" : "block",
                        textShadow: "0 1px 1px rgba(0,0,0,0.8)",
                      }}
                    >
                      {room.name || "UNNAMED"}
                    </div>

                    {!isStairs && !isOpenArea && !isFree && stats[room.id] && (
                      <div
                        style={{
                          fontSize: isMobileView
                            ? `${Math.min(8, Math.max(5, room.width * SCALE * 0.06))}px`
                            : `clamp(9px, ${room.width * SCALE * 0.1}px, 13px)`,
                          marginTop: isMobileView ? 1 : 6,
                          fontWeight: 600,
                          opacity: isHovered ? 1 : 0.8,
                          display: room.height * SCALE < 35 ? "none" : "block",
                          textShadow: "0 1px 2px rgba(0,0,0,0.8)",
                        }}
                      >
                        <div
                          style={{
                            color:
                              stats[room.id].temp > 30 ? "#FF4B2B" : "#97FEED",
                          }}
                        >
                          {stats[room.id].temp.toFixed(1)}°C
                        </div>
                        <div
                          style={{
                            color:
                              stats[room.id].occ > 70 ? "#F5A623" : "#97FEED",
                          }}
                        >
                          {Math.round(stats[room.id].occ)}%
                        </div>
                      </div>
                    )}

                    {isStairs && (
                      <div
                        style={{
                          display: "flex",
                          gap: isMobileView ? "4px" : "8px",
                          marginTop: isMobileView ? "4px" : "10px",
                        }}
                      >
                        {floorNumber < maxFloor && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              goUp();
                            }}
                            style={{
                              padding: isMobileView ? "6px 10px" : "6px 12px",
                              cursor: "pointer",
                              borderRadius: "4px",
                              border: "none",
                              background: "#071952",
                              color: "#97FEED",
                              fontWeight: "bold",
                              fontSize: isMobileView ? 9 : 10,
                            }}
                          >
                            UP
                          </button>
                        )}
                        {floorNumber > minFloor && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              goDown();
                            }}
                            style={{
                              padding: isMobileView ? "6px 10px" : "6px 12px",
                              cursor: "pointer",
                              borderRadius: "4px",
                              border: "none",
                              background: "#071952",
                              color: "#97FEED",
                              fontWeight: "bold",
                              fontSize: isMobileView ? 9 : 10,
                            }}
                          >
                            DN
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
