import React from "react";
import { Html } from "@react-three/drei";

export default function Ground() {
  return (
    <>
      {/* Main grass */}
      <mesh
        rotation={[-Math.PI / 2, 0, 0]}
        position={[0, -0.01, 0]}
        receiveShadow
      >
        <planeGeometry args={[40, 40]} />
        <meshStandardMaterial color="#4a8a38" roughness={0.96} />
      </mesh>
      {/* Sports field grass (brighter) */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[-8.5, 0.005, -7]}>
        <circleGeometry args={[5, 32]} />
        <meshStandardMaterial color="#3a9a30" roughness={0.9} />
      </mesh>
      <Html center position={[-8.5, 0.45, -7]} zIndexRange={[0, 1000]}>
        <div
          style={{
            background: "rgba(7,25,82,0.88)",
            border: "1px solid #35A29F55",
            color: "#fff",
            fontSize: "10px",
            fontWeight: 600,
            padding: "2px 7px",
            borderRadius: "5px",
            whiteSpace: "nowrap",
            pointerEvents: "none",
          }}
        >
          Play Ground
        </div>
      </Html>
      {/* Sports field lines */}
      {[-2, 0, 2].map((x) => (
        <mesh
          key={x}
          rotation={[-Math.PI / 2, 0, 0]}
          position={[x - 8.5, 0.007, -7]}
        >
          <planeGeometry args={[0.06, 4.5]} />
          <meshStandardMaterial color="#ffffff" opacity={0.4} transparent />
        </mesh>
      ))}
    </>
  );
}
