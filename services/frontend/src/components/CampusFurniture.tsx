"use client";

import { useMemo, useRef, useEffect } from "react";
import * as THREE from "three";

// ─── Types ────────────────────────────────────────────────────────────────────

interface FurnitureItem {
  x: number;
  z: number;
  rotation?: number; // Y-axis rotation in radians
}

// ─── Lamp post component (non-instanced — low count, complex shape) ───────────
//
// Structure: base plate → pole → arm → lamp head
// Kept as individual meshes in a group so each lamp is one logical object.

function LampPost({ x, z, rotation = 0 }: { x: number; z: number; rotation?: number }) {
  const POLE_H   = 3.2;
  const ARM_LEN  = 0.6;
  const HEAD_Y   = POLE_H + 0.1;

  return (
    <group position={[x, 0, z]} rotation={[0, rotation, 0]}>
      {/* Base plate */}
      <mesh position={[0, 0.06, 0]} castShadow receiveShadow>
        <cylinderGeometry args={[0.18, 0.20, 0.12, 8]} />
        <meshStandardMaterial color="#2a2a2a" roughness={0.6} metalness={0.5} />
      </mesh>

      {/* Pole */}
      <mesh position={[0, POLE_H / 2 + 0.12, 0]} castShadow>
        <cylinderGeometry args={[0.045, 0.065, POLE_H, 7]} />
        <meshStandardMaterial color="#1f1f1f" roughness={0.5} metalness={0.7} />
      </mesh>

      {/* Horizontal arm */}
      <mesh position={[ARM_LEN / 2, HEAD_Y, 0]} rotation={[0, 0, Math.PI / 2]} castShadow>
        <cylinderGeometry args={[0.03, 0.03, ARM_LEN, 6]} />
        <meshStandardMaterial color="#1f1f1f" roughness={0.5} metalness={0.7} />
      </mesh>

      {/* Lamp head housing */}
      <mesh position={[ARM_LEN, HEAD_Y - 0.12, 0]} castShadow>
        <cylinderGeometry args={[0.14, 0.10, 0.22, 8]} />
        <meshStandardMaterial color="#2d2d2d" roughness={0.4} metalness={0.6} />
      </mesh>

      {/* Lamp lens — emissive warm yellow */}
      <mesh position={[ARM_LEN, HEAD_Y - 0.26, 0]}>
        <circleGeometry args={[0.09, 8]} />
        <meshStandardMaterial
          color="#ffe87a"
          emissive="#ffcc44"
          emissiveIntensity={1.8}
          roughness={0.1}
          metalness={0}
          side={THREE.DoubleSide}
        />
      </mesh>

      {/* Point light — small radius so it only lights nearby ground */}
      <pointLight
        position={[ARM_LEN, HEAD_Y - 0.3, 0]}
        intensity={4}
        distance={5}
        decay={2}
        color="#ffe099"
      />
    </group>
  );
}

// ─── Bench (instanced — potentially many) ─────────────────────────────────────
//
// Two meshes instanced separately: seat slab + two legs.
// Bench length runs along X; rotation rotates the whole group on Y.

interface BenchData extends FurnitureItem {
  rotation: number;
}

function Benches({ items }: { items: BenchData[] }) {
  const seatRef = useRef<THREE.InstancedMesh>(null);
  const legRef  = useRef<THREE.InstancedMesh>(null);

  useEffect(() => {
    const dummy = new THREE.Object3D();

    items.forEach(({ x, z, rotation }, i) => {
      // Seat slab
      dummy.position.set(x, 0.44, z);
      dummy.rotation.set(0, rotation, 0);
      dummy.scale.setScalar(1);
      dummy.updateMatrix();
      seatRef.current?.setMatrixAt(i, dummy.matrix);

      // Legs — encode both legs as 2 instances interleaved
      // We use a single InstancedMesh for ALL leg instances (2 per bench)
      // leg index = i*2 and i*2+1
    });

    // Legs: placed relative to bench seat ends
    items.forEach(({ x, z, rotation }, i) => {
      const cos = Math.cos(rotation);
      const sin = Math.sin(rotation);
      const offset = 0.55; // half bench length

      [1, -1].forEach((side, j) => {
        const lx = x + cos * offset * side;
        const lz = z + sin * offset * side;  // note: rotation is around Y
        dummy.position.set(lx, 0.22, lz);
        dummy.rotation.set(0, rotation, 0);
        dummy.scale.setScalar(1);
        dummy.updateMatrix();
        legRef.current?.setMatrixAt(i * 2 + j, dummy.matrix);
      });
    });

    if (seatRef.current) {
        seatRef.current.instanceMatrix.needsUpdate = true;
        seatRef.current.computeBoundingSphere();
    }
    if (legRef.current) {
        legRef.current.instanceMatrix.needsUpdate = true;
        legRef.current.computeBoundingSphere();
    }
  }, [items]);

  return (
    <>
      {/* Seat slabs */}
      <instancedMesh ref={seatRef} args={[undefined, undefined, items.length]} castShadow receiveShadow>
        <boxGeometry args={[1.2, 0.08, 0.42]} />
        <meshStandardMaterial color="#7a5c3a" roughness={0.85} metalness={0} />
      </instancedMesh>

      {/* Legs (2 per bench) */}
      <instancedMesh ref={legRef} args={[undefined, undefined, items.length * 2]} castShadow receiveShadow>
        <boxGeometry args={[0.08, 0.44, 0.38]} />
        <meshStandardMaterial color="#4a3825" roughness={0.9} metalness={0} />
      </instancedMesh>
    </>
  );
}

// ─── Waste bin (instanced) ────────────────────────────────────────────────────

function WasteBins({ items }: { items: FurnitureItem[] }) {
  const bodyRef = useRef<THREE.InstancedMesh>(null);
  const lidRef  = useRef<THREE.InstancedMesh>(null);

  useEffect(() => {
    const dummy = new THREE.Object3D();

    items.forEach(({ x, z }, i) => {
      dummy.position.set(x, 0.38, z);
      dummy.scale.setScalar(1);
      dummy.rotation.set(0, 0, 0);
      dummy.updateMatrix();
      bodyRef.current?.setMatrixAt(i, dummy.matrix);

      dummy.position.set(x, 0.80, z);
      dummy.updateMatrix();
      lidRef.current?.setMatrixAt(i, dummy.matrix);
    });

    if (bodyRef.current) {
      bodyRef.current.instanceMatrix.needsUpdate = true;
      bodyRef.current.computeBoundingSphere();
    }
    if (lidRef.current) {
      lidRef.current.instanceMatrix.needsUpdate = true;
      lidRef.current.computeBoundingSphere();
    }
  }, [items]);

  return (
    <>
      <instancedMesh ref={bodyRef} args={[undefined, undefined, items.length]} castShadow receiveShadow>
        <cylinderGeometry args={[0.18, 0.15, 0.75, 9]} />
        <meshStandardMaterial color="#2e4a1e" roughness={0.7} metalness={0.2} />
      </instancedMesh>
      <instancedMesh ref={lidRef} args={[undefined, undefined, items.length]} castShadow receiveShadow>
        <cylinderGeometry args={[0.20, 0.18, 0.08, 9]} />
        <meshStandardMaterial color="#1e3212" roughness={0.6} metalness={0.3} />
      </instancedMesh>
    </>
  );
}

// ─── Placement data ───────────────────────────────────────────────────────────
//
// All positions verified by simulation against:
//   - Road segments from Roads() in DigitalTwinDashboard.tsx
//   - Building exclusion radius 2.0 units from CAMPUS_LAYOUT positions
//
// Lamp positions: 1.8 units offset from main vertical street (x=0)
// Bench positions: confirmed open via grid scan
// Bin positions: paired near benches, 0.7 units offset

const LAMP_POSITIONS: FurnitureItem[] = [
  // Right side of main vertical street
  { x:  1.8, z: -6.0, rotation: Math.PI },
  { x:  1.8, z:  2.0, rotation: Math.PI },
  // Left side of main vertical street
  { x: -1.8, z: -8.0, rotation: 0 },
  { x: -1.8, z:  0.5, rotation: 0 },
  { x: -1.8, z: 12.0, rotation: 0 },
  // Along bottom campus road (south side, z=15.5)
  { x: -14.0, z: 15.5, rotation: -Math.PI / 2  },
  { x:  -9.0, z: 15.5, rotation: -Math.PI / 2  },
  { x:   1.0, z: 15.5, rotation: -Math.PI / 2  },
  { x:   6.0, z: 15.5, rotation: -Math.PI / 2  },
  { x:  11.0, z: 15.5, rotation: -Math.PI / 2  },
];

const BENCH_ITEMS: BenchData[] = [
  // Playground perimeter (north edge of sports field)
  { x: -5.5,  z: 1.5,  rotation: 0 },
  { x: -7.0,  z: 1.5,  rotation: 0 },
  { x: -4.0, z: 1.5,  rotation: 0 },
  { x: -2.5,  z: 1.5,  rotation: 0 },
  // Near mechanical engineering (confirmed open: x:-14 to -9, z:10.8)
  { x: -14.0, z: 10.8,  rotation: Math.PI / 2 },
  { x:  -9.0, z: 10.8,  rotation: Math.PI / 2 },
  // Near multipurpose hall (confirmed open: x:-13.5, -8.5, z:-1 to -1.5)
//   { x: -13.5, z: -1.0,  rotation: Math.PI / 2 },
  { x:  -7.5, z: 0.2,  rotation: Math.PI / 2 },
  // Library / graduate area (confirmed open via scan)
  { x:   1.5, z: 11.5,  rotation: 0 },
  { x:   6.0, z: 11.0,  rotation: 0 },
  // Admin area (confirmed open: x:-6 to -2, z:12)
  { x:  -6.0, z: 12.0,  rotation: Math.PI / 2 },
  { x:  -3.0, z: 12.0,  rotation: Math.PI / 2 },
];

const BIN_POSITIONS: FurnitureItem[] = [
  // Bins placed near selected seating areas and other high-traffic open spots
  { x: -5.0,  z: -3.5 },
  { x: -10.5, z: -3.5 },
  { x: -13.5, z: 11.3 },
  { x:  -8.5, z: 11.3 },
  { x: -13.0, z: -0.5 },
  { x:   1.5, z: 12.2 },
  { x:  -5.5, z: 12.8 },
  // Along main street (right side, near lamps)
  { x:   2.3, z: -6.0 },
  { x:   2.3, z:  2.0 },
];

// ─── Main export ──────────────────────────────────────────────────────────────

export default function CampusFurniture() {
  // Memoize so arrays are stable references between renders
  const benches = useMemo(() => BENCH_ITEMS, []);
  const bins    = useMemo(() => BIN_POSITIONS, []);

  return (
    <>
      {/* Street lamps — individual components (complex multi-mesh shape + light) */}
      {LAMP_POSITIONS.map((pos, i) => (
        <LampPost key={i} x={pos.x} z={pos.z} rotation={pos.rotation} />
      ))}

      {/* Benches */}
      <Benches items={benches} />

      {/* Waste bins */}
      <WasteBins items={bins} />
    </>
  );
}