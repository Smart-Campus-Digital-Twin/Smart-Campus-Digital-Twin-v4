"use client";

import { useState, use, useEffect } from "react";
import FloorPlan2D from "@/components/indoor/FloorPlan2D";
import FloorNavigator from "@/components/indoor/FloorNavigator";
import { BUILDING_DATA } from "@/components/indoor/FloorData";
import Link from "next/link";
import { ChevronLeft } from "lucide-react";
import { notFound } from "next/navigation";

export default function DynamicBuildingPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const building = BUILDING_DATA[id];
  const [isMobile, setIsMobile] = useState(false);
  const [floor, setFloor] = useState(building?.minFloor ?? 0);

  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 1024);
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);

  if (!building) {
    return notFound();
  }

  // Calculate index for floor array (offset by minFloor if necessary)
  const floorIndex = floor - building.minFloor;

  return (
    <div style={{ 
      padding: isMobile ? "120px 16px 40px" : "100px 30px 60px", 
      minHeight: "100vh",
      background: "radial-gradient(circle at center, #0B666A 0%, #071952 100%)", 
      color: "white", 
      display: "flex", 
      flexDirection: isMobile ? "column" : "row", 
      alignItems: isMobile ? "center" : "center", 
      justifyContent: isMobile ? "flex-start" : "center",
      position: "relative",
      gap: isMobile ? "20px" : "60px",
      overflowX: "hidden"
    }}>
      <Link 
        href="/" 
        onMouseEnter={(e) => (e.currentTarget.style.filter = "brightness(1.2)")}
        onMouseLeave={(e) => (e.currentTarget.style.filter = "none")}
        style={{
          position: "absolute",
          top: isMobile ? "85px" : "100px",
          left: isMobile ? "16px" : "30px",
          display: "flex",
          alignItems: "center",
          gap: 5,
          color: "#97FEED",
          textDecoration: "none",
          fontSize: isMobile ? 12 : 14,
          fontWeight: 600,
          zIndex: 1000,
          background: isMobile ? "rgba(7,25,82,0.9)" : "transparent",
          padding: isMobile ? "8px 16px" : "0",
          borderRadius: "100px",
          border: isMobile ? "1px solid rgba(151,254,237,0.3)" : "none",
          backdropFilter: isMobile ? "blur(5px)" : "none",
          transition: "filter 0.3s ease",
        }}
      >
        <span style={{ display: 'flex', alignItems: 'center' }}>
          <ChevronLeft size={isMobile ? 16 : 20} />
          <span style={{ marginLeft: "4px" }}>BACK</span>
        </span>
      </Link>

      {/* Left Sidebar: Controls & Info */}
      <div style={{ 
        display: "flex", 
        flexDirection: "column", 
        alignItems: isMobile ? "center" : "flex-start", 
        width: isMobile ? "100%" : "350px",
        marginTop: isMobile ? "10px" : 0,
        textAlign: isMobile ? "center" : "left"
      }}>
        <h1 style={{ 
          marginBottom: "0.5rem", 
          color: "#97FEED", 
          fontSize: isMobile ? "1.8rem" : "2.8rem", 
          fontWeight: 800, 
          letterSpacing: "-0.5px",
          textShadow: "0 4px 10px rgba(0,0,0,0.3)",
          lineHeight: 1.1
        }}>
          {building.name}
        </h1>
        <div style={{ 
          marginBottom: isMobile ? "1rem" : "2.5rem", 
          background: "rgba(151, 254, 237, 0.1)", 
          padding: "6px 20px", 
          borderRadius: "100px", 
          border: "1px solid rgba(151, 254, 237, 0.3)",
          color: "#97FEED",
          fontSize: isMobile ? "0.75rem" : "0.9rem",
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: "1.5px"
        }}>
          Level {floor === 0 ? "Ground" : floor < 0 ? "Basement" : floor}
        </div>

        {!isMobile && (
          <div style={{ width: '100%' }}>
            <div style={{ marginBottom: '15px', fontSize: '0.8rem', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '1px' }}>Select Floor</div>
            <FloorNavigator
              floor={floor}
              minFloor={building.minFloor}
              maxFloor={building.maxFloor}
              goUp={() => setFloor((f) => f + 1)}
              goDown={() => setFloor((f) => f - 1)}
            />
          </div>
        )}
      </div>

      {/* Right Area: Enlarged Map */}
      <div style={{ 
        width: '100%', 
        display: 'flex', 
        justifyContent: 'center', 
        alignItems: 'center',
        maxWidth: isMobile ? '100%' : '800px'
      }}>
        <FloorPlan2D
          key={`${id}-${floor}`}
          buildingId={id}
          floor={building.floors[floorIndex]}
          floorNumber={floor}
          minFloor={building.minFloor}
          maxFloor={building.maxFloor}
          goUp={() => setFloor((f) => f + 1)}
          goDown={() => setFloor((f) => f - 1)}
          isMobile={isMobile}
        />
      </div>
      
      {isMobile && (
        <div style={{ 
          width: "100%", 
          display: "flex", 
          flexDirection: "column",
          alignItems: "center", 
          marginTop: "20px",
          gap: "10px"
        }}>
          <div style={{ fontSize: '0.7rem', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '1px' }}>Select Floor</div>
          <FloorNavigator
            floor={floor}
            minFloor={building.minFloor}
            maxFloor={building.maxFloor}
            goUp={() => setFloor((f) => f + 1)}
            goDown={() => setFloor((f) => f - 1)}
            isMobile={isMobile}
          />
        </div>
      )}
    </div>
  );
}
