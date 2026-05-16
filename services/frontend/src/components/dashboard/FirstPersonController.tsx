import { useEffect, useRef, useMemo } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import { WALK_BOUNDS } from "./DashboardTypes";
import { clamp } from "./DashboardHelpers";

export default function FirstPersonController({
  enabled,
  isMobile = false,
  runMode = false,
}: {
  enabled: boolean;
  isMobile?: boolean;
  runMode?: boolean;
}) {
  const { camera, gl } = useThree();
  const keys = useRef<Record<string, boolean>>({});
  const yaw = useRef(0);
  const pitch = useRef(-0.15);
  const pointerLocked = useRef(false);

  // Touch states
  const moveTouchId = useRef<number | null>(null);
  const lookTouchId = useRef<number | null>(null);
  const moveStart = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const lookStart = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const moveOffset = useRef<{ x: number; y: number }>({ x: 0, y: 0 });

  useEffect(() => {
    if (!enabled) return;

    // Set initial walk camera position at the entrance
    camera.position.set(0, 1.7, 18);

    const onKey = (e: KeyboardEvent, down: boolean) => {
      keys.current[e.code] = down;
    };
    const onMouseMove = (e: MouseEvent) => {
      if (!pointerLocked.current || isMobile) return;
      yaw.current -= e.movementX * 0.002;
      pitch.current -= e.movementY * 0.002;
      pitch.current = clamp(pitch.current, -1.2, 0.4);
    };
    const onPointerLockChange = () => {
      pointerLocked.current = document.pointerLockElement !== null;
    };
    const onClick = (e: MouseEvent) => {
      if (isMobile) return;
      const target = e.target as HTMLElement;
      const canvas = target?.closest("canvas") as HTMLCanvasElement | null;
      if (canvas) {
        canvas.requestPointerLock?.();
      }
    };

    const onKeyDown = (e: KeyboardEvent) => onKey(e, true);
    const onKeyUp = (e: KeyboardEvent) => onKey(e, false);

    // Touch handling
    const onTouchStart = (e: TouchEvent) => {
      for (let i = 0; i < e.changedTouches.length; i++) {
        const touch = e.changedTouches[i];
        const x = touch.clientX;
        const isLeft = x < window.innerWidth / 2;

        if (isLeft && moveTouchId.current === null) {
          moveTouchId.current = touch.identifier;
          moveStart.current = { x: touch.clientX, y: touch.clientY };
        } else if (!isLeft && lookTouchId.current === null) {
          lookTouchId.current = touch.identifier;
          lookStart.current = { x: touch.clientX, y: touch.clientY };
        }
      }
    };

    const onTouchMove = (e: TouchEvent) => {
      for (let i = 0; i < e.changedTouches.length; i++) {
        const touch = e.changedTouches[i];
        if (touch.identifier === moveTouchId.current) {
          moveOffset.current = {
            x: (touch.clientX - moveStart.current.x) / 50,
            y: (touch.clientY - moveStart.current.y) / 50,
          };
        } else if (touch.identifier === lookTouchId.current) {
          const dx = touch.clientX - lookStart.current.x;
          const dy = touch.clientY - lookStart.current.y;
          yaw.current -= dx * 0.005;
          pitch.current -= dy * 0.005;
          pitch.current = clamp(pitch.current, -1.2, 0.4);
          lookStart.current = { x: touch.clientX, y: touch.clientY };
        }
      }
    };

    const onTouchEnd = (e: TouchEvent) => {
      for (let i = 0; i < e.changedTouches.length; i++) {
        const touch = e.changedTouches[i];
        if (touch.identifier === moveTouchId.current) {
          moveTouchId.current = null;
          moveOffset.current = { x: 0, y: 0 };
        } else if (touch.identifier === lookTouchId.current) {
          lookTouchId.current = null;
        }
      }
    };

    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("pointerlockchange", onPointerLockChange);
    document.addEventListener("click", onClick);

    if (isMobile && gl?.domElement) {
      gl.domElement.addEventListener("touchstart", onTouchStart);
      gl.domElement.addEventListener("touchmove", onTouchMove);
      gl.domElement.addEventListener("touchend", onTouchEnd);
    }

    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("pointerlockchange", onPointerLockChange);
      document.removeEventListener("click", onClick);

      if (isMobile && gl?.domElement) {
        gl.domElement.removeEventListener("touchstart", onTouchStart);
        gl.domElement.removeEventListener("touchmove", onTouchMove);
        gl.domElement.removeEventListener("touchend", onTouchEnd);
      }

      // Reset touch state refs
      moveTouchId.current = null;
      lookTouchId.current = null;
      moveOffset.current = { x: 0, y: 0 };

      if (document.exitPointerLock) document.exitPointerLock();
    };
  }, [enabled, camera, isMobile, gl]);

  const euler = useMemo(() => new THREE.Euler(0, 0, 0, "YXZ"), []);
  const yawEuler = useMemo(() => new THREE.Euler(0, 0, 0), []);
  const forward = useMemo(() => new THREE.Vector3(), []);
  const right = useMemo(() => new THREE.Vector3(), []);

  useFrame((_, delta) => {
    if (!enabled) return;

    const speed =
      keys.current["ShiftLeft"] || keys.current["ShiftRight"] || runMode
        ? 12
        : 6;
    const dt = Math.min(delta, 0.05);

    euler.set(pitch.current, yaw.current, 0, "YXZ");
    camera.quaternion.setFromEuler(euler);

    yawEuler.set(0, yaw.current, 0);
    forward.set(0, 0, -1).applyEuler(yawEuler);
    right.set(1, 0, 0).applyEuler(yawEuler);

    // Keyboard movement
    if (keys.current["KeyW"] || keys.current["ArrowUp"])
      camera.position.addScaledVector(forward, speed * dt);
    if (keys.current["KeyS"] || keys.current["ArrowDown"])
      camera.position.addScaledVector(forward, -speed * dt);
    if (keys.current["KeyA"] || keys.current["ArrowLeft"])
      camera.position.addScaledVector(right, -speed * dt);
    if (keys.current["KeyD"] || keys.current["ArrowRight"])
      camera.position.addScaledVector(right, speed * dt);

    // Touch movement
    if (isMobile && moveTouchId.current !== null) {
      const moveX = clamp(moveOffset.current.x, -1, 1);
      const moveY = clamp(moveOffset.current.y, -1, 1);
      camera.position.addScaledVector(forward, -moveY * speed * dt);
      camera.position.addScaledVector(right, moveX * speed * dt);
    }

    // Handle vertical adjustment
    if (keys.current["KeyQ"]) {
      camera.position.y -= speed * dt;
    } else if (keys.current["KeyE"]) {
      camera.position.y += speed * dt;
    } else {
      // Return to eye level if no vertical keys are pressed
      camera.position.y = 1.7;
    }
    // Clamp to campus bounds
    camera.position.x = clamp(
      camera.position.x,
      WALK_BOUNDS.minX,
      WALK_BOUNDS.maxX,
    );
    camera.position.z = clamp(
      camera.position.z,
      WALK_BOUNDS.minZ,
      WALK_BOUNDS.maxZ,
    );
  });

  return null;
}
