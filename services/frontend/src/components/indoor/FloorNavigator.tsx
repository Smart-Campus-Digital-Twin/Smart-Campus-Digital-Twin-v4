"use client";

import { useEffect } from "react";

type Props = {
  floor: number;
  minFloor?: number;
  maxFloor: number;
  goUp: () => void;
  goDown: () => void;
  isMobile?: boolean;
};

export default function FloorNavigator({
  floor,
  minFloor = 0,
  maxFloor,
  goUp,
  goDown,
  isMobile = false,
}: Props) {
  // Keyboard navigation support
  useEffect(() => {
    const handleKeyPress = (e: KeyboardEvent) => {
      // Ignore if typing in an input or textarea
      if (
        document.activeElement instanceof HTMLInputElement ||
        document.activeElement instanceof HTMLTextAreaElement
      ) {
        return;
      }

      if (e.key === "ArrowUp" && floor < maxFloor) {
        e.preventDefault();
        goUp();
      } else if (e.key === "ArrowDown" && floor > minFloor) {
        e.preventDefault();
        goDown();
      }
    };

    window.addEventListener("keydown", handleKeyPress);
    return () => window.removeEventListener("keydown", handleKeyPress);
  }, [floor, minFloor, maxFloor, goUp, goDown]);

  const buttonStyle = (active: boolean) => ({
    padding: isMobile ? "12px 0" : "20px 0",
    width: isMobile ? "70px" : "100px",
    borderRadius: isMobile ? "12px" : "16px",
    border: "1px solid rgba(151, 254, 237, 0.4)",
    background: active
      ? "linear-gradient(135deg, #0B666A 0%, #071952 100%)"
      : "rgba(255, 255, 255, 0.05)",
    color: "#97FEED",
    fontWeight: 700,
    fontSize: isMobile ? "0.6rem" : "0.8rem",
    cursor: "pointer",
    display: "flex",
    flexDirection: "column" as const,
    alignItems: "center",
    justifyContent: "center",
    gap: isMobile ? "4px" : "8px",
    transition: "all 0.3s ease",
    boxShadow: active ? "0 4px 15px rgba(151, 254, 237, 0.2)" : "none",
    backdropFilter: "blur(5px)",
  });

  return (
    <nav
      role="navigation"
      aria-label="Floor navigation"
      style={{
        display: "flex",
        flexDirection: isMobile ? "row" : "column",
        justifyContent: "center",
        gap: isMobile ? 12 : 20,
      }}
    >
      {floor < maxFloor && (
        <button
          onClick={goUp}
          aria-label={`Go to floor ${floor + 1}`}
          title="Go up (Arrow Up)"
          style={buttonStyle(true)}
          onMouseEnter={(e) => {
            e.currentTarget.style.transform = "translateY(-4px)";
            e.currentTarget.style.boxShadow =
              "0 10px 30px rgba(151, 254, 237, 0.4)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.transform = "translateY(0)";
            e.currentTarget.style.boxShadow =
              "0 4px 15px rgba(151, 254, 237, 0.2)";
          }}
        >
          <span style={{ fontSize: "1.5rem" }} aria-hidden="true">
            ↑
          </span>
          UP
        </button>
      )}

      {floor > minFloor && (
        <button
          onClick={goDown}
          aria-label={`Go to floor ${floor - 1}`}
          title="Go down (Arrow Down)"
          style={buttonStyle(true)}
          onMouseEnter={(e) => {
            e.currentTarget.style.transform = "translateY(4px)";
            e.currentTarget.style.boxShadow =
              "0 10px 30px rgba(151, 254, 237, 0.4)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.transform = "translateY(0)";
            e.currentTarget.style.boxShadow =
              "0 4px 15px rgba(151, 254, 237, 0.2)";
          }}
        >
          <span style={{ fontSize: "1.5rem" }} aria-hidden="true">
            ↓
          </span>
          DOWN
        </button>
      )}
    </nav>
  );
}
