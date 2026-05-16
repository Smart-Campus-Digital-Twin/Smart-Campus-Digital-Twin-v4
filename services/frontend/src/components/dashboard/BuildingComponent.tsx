import React, { useRef, useState } from "react";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import * as THREE from "three";
import { Zone, ZoneLayout, STATUS_COLORS, STATUS_GLOW } from "./DashboardTypes";

export default function Building({
  layout,
  zone,
  selected,
  onClick,
}: {
  layout: ZoneLayout;
  zone: Zone;
  selected: boolean;
  onClick: () => void;
}) {
  const meshRef = useRef<THREE.Group>(null!);
  const [hovered, setHovered] = useState(false);
  const wallMatRef  = useRef<THREE.MeshStandardMaterial>(null!);
  const orbMatRef   = useRef<THREE.MeshStandardMaterial>(null!);
  const currentEmissive = useRef(new THREE.Color(STATUS_COLORS[zone.status]));
  const currentOrb      = useRef(new THREE.Color(STATUS_COLORS[zone.status]));
  const [w, h, d] = layout.size;
  const [px, , pz] = layout.position;

  useFrame((_, delta) => {
    if (!meshRef.current) return;

    // Hover/select lift — unchanged
    const targetY = hovered || selected ? 0.1 : 0;
    meshRef.current.position.y = THREE.MathUtils.lerp(
      meshRef.current.position.y,
      targetY,
      delta * 5,
    );

    // Emissive color lerp — building wall
    if (wallMatRef.current) {
      const targetEmissive = new THREE.Color(STATUS_COLORS[zone.status]);
      currentEmissive.current.lerp(targetEmissive, delta * 3);
      wallMatRef.current.emissive.copy(currentEmissive.current);
    }

    // Color lerp — status orb
    if (orbMatRef.current) {
      const targetOrb = new THREE.Color(STATUS_COLORS[zone.status]);
      currentOrb.current.lerp(targetOrb, delta * 3);
      orbMatRef.current.color.copy(currentOrb.current);
      orbMatRef.current.emissive.copy(currentOrb.current);
    }
  });

  const wallColor = selected ? "#d8eeff" : layout.wallColor;
  const emissive = STATUS_COLORS[zone.status];
  const emissiveInt = selected ? 0.5 : hovered ? 0.3 : 0.08;

  let roofHeight = 0.18;
  if (layout.roofType === "gabled") roofHeight = Math.min(w, d) * 0.35;
  else if (layout.roofType === "hip") roofHeight = Math.min(w, d) * 0.45;

  const totalH = h + roofHeight;

  const Roof = () => {
    if (layout.roofType === "flat") {
      return (
        <mesh position={[0, h + 0.09, 0]}>
          <boxGeometry args={[w + 0.15, 0.18, d + 0.15]} />
          <meshStandardMaterial
            color={layout.roofColor}
            roughness={0.5}
            metalness={0.1}
          />
        </mesh>
      );
    }
    if (layout.roofType === "gabled") {
      const run = d / 2;
      const slopeLen = Math.hypot(run, roofHeight);
      const angle = Math.atan2(roofHeight, run);
      return (
        <group position={[0, h, 0]}>
          <mesh
            rotation={[angle, 0, 0]}
            position={[0, roofHeight / 2, run / 2]}
          >
            <boxGeometry args={[w + 0.3, 0.14, slopeLen + 0.1]} />
            <meshStandardMaterial color={layout.roofColor} roughness={0.6} />
          </mesh>
          <mesh
            rotation={[-angle, 0, 0]}
            position={[0, roofHeight / 2, -run / 2]}
          >
            <boxGeometry args={[w + 0.3, 0.14, slopeLen + 0.1]} />
            <meshStandardMaterial color={layout.roofColor} roughness={0.6} />
          </mesh>
        </group>
      );
    }
    if (layout.roofType === "hip") {
      return (
        <mesh
          position={[0, h + roofHeight / 2, 0]}
          rotation={[0, Math.PI / 4, 0]}
        >
          <coneGeometry args={[Math.max(w, d) * 0.75 + 0.15, roofHeight, 4]} />
          <meshStandardMaterial color={layout.roofColor} roughness={0.6} />
        </mesh>
      );
    }
    return (
      <mesh position={[0, h + 0.05, 0]} rotation={[0.12, 0, 0]}>
        <boxGeometry args={[w + 0.2, 0.18, d + 0.3]} />
        <meshStandardMaterial color={layout.roofColor} roughness={0.5} />
      </mesh>
    );
  };

  const Windows = () => {
    const rows = Math.max(1, Math.floor(h / 1.5));
    const cols = Math.max(2, Math.floor(w / 1.1));
    const wins = [];
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const wx = -w / 2 + 0.55 + c * ((w - 0.55) / cols);
        const wy = 0.55 + r * ((h - 0.5) / rows);
        wins.push(
          <mesh key={`${r}-${c}`} position={[wx, wy, d / 2 + 0.015]}>
            <boxGeometry args={[0.28, 0.32, 0.04]} />
            <meshStandardMaterial
              color={selected ? "#aaddff" : "#88bbee"}
              emissive={selected ? "#4488cc" : "#1a3366"}
              emissiveIntensity={0.5}
              roughness={0.1}
              metalness={0.4}
            />
          </mesh>,
        );
      }
    }
    return <>{wins}</>;
  };

  return (
    <group position={[px, 0, pz]}>
      <group
        ref={meshRef}
        onClick={(e) => {
          e.stopPropagation();
          onClick();
        }}
        onPointerOver={() => setHovered(true)}
        onPointerOut={() => setHovered(false)}
      >
        <mesh position={[0, h / 2, 0]} castShadow receiveShadow>
          <boxGeometry args={[w, h, d]} />
          <meshStandardMaterial
            ref={wallMatRef}
            color={wallColor}
            emissive={emissive}
            emissiveIntensity={emissiveInt}
            roughness={0.55}
            metalness={0.08}
          />
        </mesh>
        {layout.id !== "lagaan" && <Windows />}
        <Roof />
        <mesh position={[0, totalH + 0.4, 0]}>
          <sphereGeometry args={[0.16, 12, 12]} />
          <meshStandardMaterial
            ref={orbMatRef}
            color={STATUS_COLORS[zone.status]}
            emissive={STATUS_GLOW[zone.status]}
            emissiveIntensity={1.0}
          />
        </mesh>
        <Html center position={[0, totalH + 1.1, 0]} zIndexRange={[0, 1000]}>
          <div
            style={{
              background: "rgba(7,25,82,0.88)",
              border: `1px solid ${selected ? STATUS_COLORS[zone.status] : "#35A29F55"}`,
              color: "#fff",
              fontSize: "10px",
              fontWeight: 600,
              padding: "2px 7px",
              borderRadius: "5px",
              whiteSpace: "nowrap",
              pointerEvents: "none",
              boxShadow: selected
                ? `0 0 10px ${STATUS_COLORS[zone.status]}88`
                : "none",
            }}
          >
            {layout.label}
          </div>
        </Html>
      </group>
    </group>
  );
}
