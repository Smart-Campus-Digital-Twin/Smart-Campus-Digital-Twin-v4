import React from "react";

export default function Roads() {
  const road = { color: "#3d3b3b", roughness: 0.95 };
  const pave = { color: "#888888", roughness: 0.9 };
  const markings = { color: "#ffffff", roughness: 0.8 };

  const RoadPlane = ({
    x,
    z,
    w,
    d,
    rot = 0,
    type = "road",
  }: {
    x: number;
    z: number;
    w: number;
    d: number;
    rot?: number;
    type?: "road" | "pave";
  }) => (
    <mesh
      rotation={[-Math.PI / 2, 0, rot]}
      position={[x, 0.006, z]}
      receiveShadow
    >
      <planeGeometry args={[w, d]} />
      <meshStandardMaterial {...(type === "road" ? road : pave)} />
    </mesh>
  );

  // Centre-line dashes for main street
  const Dashes = () => {
    const dashes = [];
    for (let z = -11; z < 16; z += 1.4) {
      dashes.push(
        <mesh
          key={z}
          rotation={[-Math.PI / 2, 0, 0]}
          position={[0.0, 0.008, z]}
        >
          <planeGeometry args={[0.06, 0.7]} />
          <meshStandardMaterial {...markings} opacity={0.6} transparent />
        </mesh>,
      );
    }
    return <>{dashes}</>;
  };

  // Centre-line dashes for horizontal roads (X direction)
  const DashesHorizontal = () => {
    const dashes = [];
    for (let x = -19; x < 16; x += 1.4) {
      dashes.push(
        <mesh
          key={x}
          rotation={[-Math.PI / 2, 0, Math.PI / 2]} // rotate to align along X
          position={[2.0 + x, 0.008, 17.0]} // align with your south road
        >
          <planeGeometry args={[0.06, 0.7]} />
          <meshStandardMaterial {...markings} opacity={0.6} transparent />
        </mesh>,
      );
    }
    return <>{dashes}</>;
  };

  return (
    <group>
      {/* ── MAIN STREET — vertical */}
      <RoadPlane x={0} z={3.0} w={1.3} d={30} />
      <Dashes />

      {/* ── Main Road ── */}
      <RoadPlane x={0.0} z={17.0} w={36} d={2.4} />
      <DashesHorizontal />

      {/* ── CROSS ROAD D: Chemical */}
      <RoadPlane x={-3.1} z={9.5} w={5} d={0.6} type="pave" />

      {/* ── BOTTOM RIGHT — Integrated ── */}
      <RoadPlane x={4.5} z={8.5} w={9} d={1.0} />

      {/* ── MECHANICAL / SIDE ENTRANCE spur west ── */}
      <RoadPlane x={-11} z={14.5} w={10} d={0.9} />
      <RoadPlane x={-6.0} z={15.5} w={0.9} d={3} />
      <RoadPlane x={-16.0} z={8.45} w={1.0} d={13} />

      {/* Roads Sumandasa block ── */}
      <RoadPlane x={-6} z={6.5} w={12} d={1} />
      <RoadPlane x={-8} z={2.5} w={16} d={1} />
      <RoadPlane x={-12.0} z={4.5} w={1.0} d={5} />

      {/* Roads Civil and others ── */}
      <RoadPlane x={3.0} z={6.5} w={6} d={1} />
      <RoadPlane x={6.0} z={4} w={1} d={6} />
      <RoadPlane x={10.5} z={1} w={10} d={1} />
      <RoadPlane x={15} z={-8} w={1} d={18} />
      <RoadPlane x={3.0} z={-11.5} w={6} d={1} />
      <RoadPlane x={6.0} z={-14} w={1} d={6} />
      <RoadPlane x={10.0} z={-16.5} w={9} d={1} />

      {/* Roads L canteen and business ── */}
      <RoadPlane x={3.1} z={1} w={4.9} d={1} type="pave" />

      {/* Roads NA1 and NA2 ── */}
      <RoadPlane x={11.5} z={6} w={10} d={1} />

      {/* Roads Fac. of Medicine ── */}
      <RoadPlane x={16.5} z={4} w={1} d={5} />

      {/* Roads dept.of Maths ── */}
      <RoadPlane x={2.1} z={-3} w={3} d={1} type="pave" />
    </group>
  );
}
