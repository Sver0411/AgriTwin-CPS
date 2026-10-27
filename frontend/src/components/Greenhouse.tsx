import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { labels, type Device, type Frame } from "../types";

export function Greenhouse({
  frame,
  selected,
  onSelect,
}: {
  frame: Frame;
  selected: Device;
  onSelect: (device: Device) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const live = useRef({ frame, selected, onSelect });
  live.current = { frame, selected, onSelect };
  const [error, setError] = useState("");
  useEffect(() => {
    const container = host.current!;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      setError("此浏览器无法建立 WebGL 场景；状态面板和时间轴仍可使用。");
      return;
    }
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFShadowMap;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.setClearColor(0xf2f3f2, 1);
    container.appendChild(renderer.domElement);
    renderer.domElement.setAttribute(
      "aria-label",
      "三维温室：拖动旋转、滚轮缩放、点击设备",
    );
    const scene = new THREE.Scene();
    scene.fog = new THREE.Fog(0xf2f3f2, 32, 65);
    const camera = new THREE.PerspectiveCamera(39, 1, 0.1, 100);
    camera.position.set(15, 11, 17);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(0, 1, 0);
    controls.enableDamping = true;
    controls.minDistance = 6;
    controls.maxDistance = 34;
    controls.maxPolarAngle = Math.PI / 2 - 0.03;
    scene.add(new THREE.HemisphereLight(0xffffff, 0x829684, 2.2));
    const sun = new THREE.DirectionalLight(0xfffbf0, 3.5);
    sun.position.set(-9, 16, 8);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    Object.assign(sun.shadow.camera, {
      left: -14,
      right: 14,
      top: 14,
      bottom: -14,
    });
    scene.add(sun);
    const metal = new THREE.MeshStandardMaterial({
      color: 0xe3e8e5,
      metalness: 0.65,
      roughness: 0.3,
    });
    const dark = new THREE.MeshStandardMaterial({
      color: 0x333e3a,
      metalness: 0.3,
      roughness: 0.6,
    });
    const glass = new THREE.MeshPhysicalMaterial({
      color: 0xe3f0ed,
      transparent: true,
      opacity: 0.13,
      roughness: 0.1,
      metalness: 0,
      depthWrite: false,
      side: THREE.DoubleSide,
    });
    const soil = new THREE.MeshStandardMaterial({
      color: 0x51483d,
      roughness: 1,
    });
    const pipeMaterial = new THREE.MeshStandardMaterial({
      color: 0x3e5258,
      roughness: 0.5,
    });
    const cube = new THREE.BoxGeometry(1, 1, 1),
      beamGeo = new THREE.CylinderGeometry(1, 1, 1, 8);
    const box = (
      x: number,
      y: number,
      z: number,
      sx: number,
      sy: number,
      sz: number,
      material: THREE.Material,
    ) => {
      const m = new THREE.Mesh(cube, material);
      m.position.set(x, y, z);
      m.scale.set(sx, sy, sz);
      m.castShadow = true;
      m.receiveShadow = true;
      scene.add(m);
      return m;
    };
    const beam = (
      a: number[],
      b: number[],
      radius = 0.045,
      material: THREE.Material = metal,
    ) => {
      const start = new THREE.Vector3(...a),
        end = new THREE.Vector3(...b),
        delta = end.clone().sub(start);
      const m = new THREE.Mesh(beamGeo, material);
      m.position.copy(start.add(end).multiplyScalar(0.5));
      m.scale.set(radius, delta.length(), radius);
      m.quaternion.setFromUnitVectors(
        new THREE.Vector3(0, 1, 0),
        delta.normalize(),
      );
      m.castShadow = true;
      scene.add(m);
      return m;
    };
    box(
      0,
      -0.15,
      0,
      15,
      0.25,
      11,
      new THREE.MeshStandardMaterial({ color: 0xe4e7e0, roughness: 1 }),
    );
    box(
      0,
      -0.005,
      0,
      12.5,
      0.06,
      8.5,
      new THREE.MeshStandardMaterial({ color: 0xd1d6d0, roughness: 0.9 }),
    );
    const grid = new THREE.GridHelper(40, 40, 0xd7dcd7, 0xe5e8e5);
    grid.position.y = -0.27;
    scene.add(grid);
    // A gabled frame with repeated bays; coordinates are schematic, not spatial measurements.
    for (let x = -6; x <= 6; x += 2) {
      for (const z of [-4, 4]) {
        beam([x, 0, z], [x, 3.4, z]);
        beam([x, 3.4, z], [x, 5, 0]);
      }
      beam([x, 3.4, -4], [x, 3.4, 4], 0.028);
    }
    for (const [y, z] of [
      [0, -4],
      [0, 4],
      [3.4, -4],
      [3.4, 4],
      [5, 0],
    ])
      beam([-6, y, z], [6, y, z]);
    for (const z of [-4, 4]) box(0, 1.7, z, 12, 3.4, 0.015, glass);
    for (const x of [-6, 6]) {
      box(x, 1.7, 0, 0.015, 3.4, 8, glass);
      beam([x, 0, -1], [x, 3.4, -1]);
      beam([x, 0, 1], [x, 3.4, 1]);
    }
    for (const side of [-1, 1]) {
      const roof = box(
        0,
        4.2,
        side * 2,
        12,
        0.02,
        Math.sqrt(4 ** 2 + 1.6 ** 2),
        glass,
      );
      roof.rotation.x = side * Math.atan2(1.6, 4);
    }
    const leafGeo = new THREE.SphereGeometry(1, 8, 6),
      stemGeo = new THREE.CylinderGeometry(0.025, 0.04, 1, 5);
    const leaves = new THREE.InstancedMesh(
      leafGeo,
      new THREE.MeshStandardMaterial({ color: 0x4e7850, roughness: 0.85 }),
      5 * 12 * 6,
    );
    const stems = new THREE.InstancedMesh(
      stemGeo,
      new THREE.MeshStandardMaterial({ color: 0x62835b, roughness: 0.9 }),
      60,
    );
    leaves.castShadow = true;
    stems.castShadow = true;
    const dummy = new THREE.Object3D();
    let n = 0,
      p = 0;
    for (let row = 0; row < 5; row++) {
      const z = -3.1 + row * 1.55;
      box(0, 0.2, z, 10.6, 0.4, 0.9, dark);
      box(0, 0.41, z, 10.35, 0.05, 0.76, soil);
      beam([-5.4, 0.49, z], [5.4, 0.49, z], 0.025, pipeMaterial);
      for (let column = 0; column < 12; column++) {
        const x = -4.8 + column * 0.87;
        const height = 0.52 + (column % 3) * 0.08;
        dummy.position.set(x, 0.45 + height / 2, z);
        dummy.scale.set(1, height, 1);
        dummy.rotation.set(0, 0, 0);
        dummy.updateMatrix();
        stems.setMatrixAt(p++, dummy.matrix);
        for (let l = 0; l < 6; l++) {
          const angle = l * 2.4;
          dummy.position.set(
            x + Math.cos(angle) * 0.14,
            0.55 + l * 0.075,
            z + Math.sin(angle) * 0.14,
          );
          dummy.scale.set(0.23, 0.07, 0.14);
          dummy.rotation.set(0.2, angle, 0.25);
          dummy.updateMatrix();
          leaves.setMatrixAt(n++, dummy.matrix);
        }
      }
    }
    scene.add(leaves, stems);
    beam([-5.5, 0.48, -3.2], [-5.5, 0.48, 3.2], 0.065, pipeMaterial);
    const targets: THREE.Object3D[] = [];
    const markers = new Map<Device, THREE.Mesh>();
    const marker = (id: Device, x: number, y: number, z: number) => {
      const m = new THREE.Mesh(
        new THREE.SphereGeometry(0.16, 20, 16),
        new THREE.MeshStandardMaterial({
          color: 0x303937,
          emissive: 0x10231d,
          emissiveIntensity: 0.1,
        }),
      );
      m.position.set(x, y, z);
      m.userData.device = id;
      scene.add(m);
      targets.push(m);
      markers.set(id, m);
      return m;
    };
    for (const [id, x, y, z] of [
      ["temperature", -2, 2.7, -0.8],
      ["humidity", 2, 2.7, 0.8],
      ["moisture", 1, 0.72, -3.1],
    ] as const) {
      beam([x, y, z], [x, y + 0.5, z], 0.025);
      box(x, y + 0.05, z, 0.26, 0.42, 0.22, metal);
      marker(id, x, y + 0.32, z + 0.15);
    }
    const fan = new THREE.Group();
    fan.position.set(5.9, 2.5, 0);
    fan.rotation.y = Math.PI / 2;
    scene.add(fan);
    const fanRing = new THREE.Mesh(
      new THREE.TorusGeometry(0.65, 0.07, 12, 40),
      metal,
    );
    fan.add(fanRing);
    const rotor = new THREE.Group();
    fan.add(rotor);
    for (let i = 0; i < 4; i++) {
      const blade = new THREE.Mesh(
        new THREE.BoxGeometry(0.16, 0.85, 0.08),
        dark,
      );
      blade.position.y = 0.27;
      const arm = new THREE.Group();
      arm.rotation.z = (i * Math.PI) / 2;
      arm.add(blade);
      rotor.add(arm);
    }
    marker("ventilation", 5.9, 3.4, 0);
    box(-5.7, 0.75, 3.4, 0.55, 1.15, 0.55, metal);
    marker("irrigation", -5.7, 1.45, 3.4);
    const water = new THREE.Mesh(
      new THREE.SphereGeometry(0.08, 8, 6),
      new THREE.MeshStandardMaterial({ color: 0x5b99b1 }),
    );
    water.position.set(-5.5, 0.65, 2);
    scene.add(water);
    const raycaster = new THREE.Raycaster(),
      pointer = new THREE.Vector2();
    let down = [0, 0];
    const onDown = (e: PointerEvent) => {
      down = [e.clientX, e.clientY];
    };
    const onUp = (e: PointerEvent) => {
      if (Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 5) return;
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.set(
        ((e.clientX - rect.left) / rect.width) * 2 - 1,
        (-(e.clientY - rect.top) / rect.height) * 2 + 1,
      );
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster.intersectObjects(targets)[0];
      if (hit) live.current.onSelect(hit.object.userData.device as Device);
    };
    renderer.domElement.addEventListener("pointerdown", onDown);
    renderer.domElement.addEventListener("pointerup", onUp);
    const resize = new ResizeObserver(() => {
      const w = container.clientWidth,
        h = container.clientHeight;
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    });
    resize.observe(container);
    let animation = 0;
    let previousTime = performance.now();
    const render = () => {
      const now = performance.now();
      const delta = Math.min((now - previousTime) / 1000, 0.1),
        { frame: f, selected: choice } = live.current;
      rotor.rotation.z -= delta * 8 * (f.actual.ventilation ?? 0);
      previousTime = now;
      water.visible = (f.actual.irrigation ?? 0) > 0;
      for (const [id, m] of markers) {
        const channel =
          id === "temperature" || id === "humidity" || id === "moisture"
            ? f.channels[id]
            : null;
        const unknown = channel
          ? channel.state === "unknown" ||
            channel.state === null ||
            channel.trust === null
          : f.actual[id as "ventilation" | "irrigation"] === null;
        const bad = channel
          ? channel.state === "confirmed_anomaly"
          : f.actuatorStatus === "failed";
        const suspect = channel
          ? channel.state === "suspected"
          : f.actuatorStatus === "limited";
        (m.material as THREE.MeshStandardMaterial).color.set(
          unknown ? 0x919795 : bad ? 0xbc574d : suspect ? 0xc89b45 : 0x344d43,
        );
        m.scale.setScalar(choice === id ? 1.4 : 1);
      }
      controls.update();
      renderer.render(scene, camera);
      animation = requestAnimationFrame(render);
    };
    render();
    return () => {
      cancelAnimationFrame(animation);
      resize.disconnect();
      controls.dispose();
      renderer.domElement.removeEventListener("pointerdown", onDown);
      renderer.domElement.removeEventListener("pointerup", onUp);
      const geometries = new Set<THREE.BufferGeometry>(),
        materials = new Set<THREE.Material>();
      scene.traverse((o) => {
        if (o instanceof THREE.Mesh || o instanceof THREE.LineSegments) {
          geometries.add(o.geometry);
          for (const m of Array.isArray(o.material) ? o.material : [o.material])
            materials.add(m);
        }
        if (o instanceof THREE.InstancedMesh) o.dispose();
      });
      geometries.forEach((g) => g.dispose());
      materials.forEach((m) => m.dispose());
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, []);
  return (
    <section className="scene">
      <div className="scene-title">
        <h2>三维温室</h2>
        <p>拖动旋转 · 滚轮缩放 · 点击圆形设备标记</p>
      </div>
      <div ref={host} className="canvas-host" />
      {error && (
        <div role="alert" className="scene-error">
          {error}
        </div>
      )}
      <div className="scene-footer">
        <span>布局仅为示意，不表示空间温湿度分布</span>
        <span data-testid="scene-step">STEP {frame.step}</span>
      </div>
      <div className="device-tabs">
        {(Object.keys(labels) as Device[]).map((id) => (
          <button
            key={id}
            aria-pressed={selected === id}
            onClick={() => onSelect(id)}
          >
            {labels[id]}
          </button>
        ))}
      </div>
    </section>
  );
}
