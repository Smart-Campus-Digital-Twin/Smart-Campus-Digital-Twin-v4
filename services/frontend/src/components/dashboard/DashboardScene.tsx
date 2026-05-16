import React from "react";
import { OrbitControls } from "@react-three/drei";
import { Zone, CAMPUS_LAYOUT } from "./DashboardTypes";
import Ground from "./GroundComponent";
import Roads from "./RoadsComponent";
import CampusTrees from "../CampusTrees";
import CampusFurniture from "../CampusFurniture";
import Building from "./BuildingComponent";
import FirstPersonController from "./FirstPersonController";

export type TimeOfDay = "day" | "evening" | "night";

interface DashboardSceneProps {
  zones: Zone[];
  selectedId: string;
  onSelect: (id: string) => void;
  walkMode: boolean;
  isMobile?: boolean;
  runMode?: boolean;
  timeOfDay?: TimeOfDay;
}

const TIME_PRESETS: Record<TimeOfDay, {
  bg: string;
  ambient: number;
  sunIntensity: number;
  sunColor: string;
  fillColor: string;
  fillIntensity: number;
  hemiSky: string;
  hemiGround: string;
  hemiIntensity: number;
}> = {
  day: {
    bg: "#c0d4ee",
    ambient: 1.1,
    sunIntensity: 1.5,
    sunColor: "#ffffff",
    fillColor: "#ddeeff",
    fillIntensity: 0.35,
    hemiSky: "#c8daf0",
    hemiGround: "#3a7030",
    hemiIntensity: 0.5,
  },
  evening: {
    bg: "#f4a060",
    ambient: 0.55,
    sunIntensity: 1.0,
    sunColor: "#ff9a5a",
    fillColor: "#ffb47a",
    fillIntensity: 0.3,
    hemiSky: "#f4a060",
    hemiGround: "#3a4530",
    hemiIntensity: 0.4,
  },
  night: {
    bg: "#0a1428",
    ambient: 0.25,
    sunIntensity: 0.15,
    sunColor: "#9bb4ff",
    fillColor: "#5570aa",
    fillIntensity: 0.2,
    hemiSky: "#1a2548",
    hemiGround: "#0a1010",
    hemiIntensity: 0.25,
  },
};

export default function DashboardScene({
  zones,
  selectedId,
  onSelect,
  walkMode,
  isMobile = false,
  runMode = false,
  timeOfDay = "day",
}: DashboardSceneProps) {
  const p = TIME_PRESETS[timeOfDay];
  return (
    <>
      <color attach="background" args={[p.bg]} />
      <fog attach="fog" args={[p.bg, 30, 70]} />

      <ambientLight intensity={p.ambient} />
      <directionalLight
        position={[12, 20, 10]}
        intensity={p.sunIntensity}
        color={p.sunColor}
        castShadow
        shadow-mapSize={[2048, 2048]}
        shadow-bias={-0.0004}
        shadow-camera-near={0.5}
        shadow-camera-far={70}
        shadow-camera-left={-25}
        shadow-camera-right={25}
        shadow-camera-top={25}
        shadow-camera-bottom={-25}
      />
      <directionalLight
        position={[-10, 12, -8]}
        intensity={p.fillIntensity}
        color={p.fillColor}
      />
      <hemisphereLight args={[p.hemiSky, p.hemiGround, p.hemiIntensity]} />

      <Ground />
      <Roads />
      <CampusTrees />
      <CampusFurniture />

      {CAMPUS_LAYOUT.map((layout) => {
        const zone = zones.find((z) => z.id === layout.id);
        if (!zone) return null;
        return (
          <Building
            key={layout.id}
            layout={layout}
            zone={zone}
            selected={selectedId === layout.id}
            onClick={() => onSelect(layout.id)}
          />
        );
      })}

      {walkMode ? (
        <FirstPersonController
          enabled={walkMode}
          isMobile={isMobile}
          runMode={runMode}
        />
      ) : (
        <OrbitControls
          makeDefault
          enablePan
          enableRotate
          enableZoom
          panSpeed={isMobile ? 0.9 : 1.5}
          rotateSpeed={isMobile ? 0.6 : 1}
          zoomSpeed={isMobile ? 0.8 : 1}
          minDistance={isMobile ? 5 : 6}
          maxDistance={isMobile ? 50 : 38}
          maxPolarAngle={Math.PI / (isMobile ? 2.05 : 2.15)}
          autoRotate={false}
          target={[1, 0, 1]}
        />
      )}
    </>
  );
}
