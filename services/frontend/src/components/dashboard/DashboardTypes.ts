export type ZoneStatus = "normal" | "busy" | "critical";

export type Zone = {
  id: string;
  name: string;
  buildingId?: string;
  totalCapacity?: number;
  currentOccupancy?: number;
  energyKw: number;
  occupancy: number;
  occupancyTheoretical?: number;
  temperatureC: number;
  anomalyCount?: number;
  status: ZoneStatus;
  hasData: boolean;
};

export type SensorHealth = {
  sensor_id: string;
  room_id: string;
  building_id: string;
  sensor_type: string;
  last_seen_ms: number | null;
  last_value: number | null;
  seconds_since: number | null;
  broken: boolean;
  anomalous: boolean;
};

export type AnomalyEntry = {
  detected_at: string;
  rule: string;
  severity: string;
  sensor_id: string;
  room_id: string;
  value: unknown;
};

export type ZoneLayout = {
  id: string;
  name: string;
  position: [number, number, number];
  size: [number, number, number];
  roofType: "flat" | "gabled" | "hip" | "shed";
  roofColor: string;
  wallColor: string;
  label: string;
};

export const STATUS_COLORS: Record<ZoneStatus, string> = {
  normal: "#35A29F",
  busy: "#F5A623",
  critical: "#E85D24",
};

export const STATUS_GLOW: Record<ZoneStatus, string> = {
  normal: "#97FEED",
  busy: "#FAC75A",
  critical: "#FF8B6E",
};

export const CAMPUS_LAYOUT: ZoneLayout[] = [
  {
    id: "lagaan",
    name: "Lagaan",
    position: [-2.5, 0, -2],
    size: [2.5, 0.25, 2.5],
    roofType: "shed",
    roofColor: "#3a5a40",
    wallColor: "#dad7cd",
    label: "Lagaan",
  },
  {
    id: "conference",
    name: "Multipurpose Hall",
    position: [-10.5, 0, 0.5],
    size: [4.2, 3.2, 2.2],
    roofType: "gabled",
    roofColor: "#8b3a3a",
    wallColor: "#f4f1ea",
    label: "Multipurpose Hall",
  },
  {
    id: "hostel_a",
    name: "Hostel A",
    position: [10.5, 0, -14.5],
    size: [6.2, 4.0, 1.8],
    roofType: "hip",
    roofColor: "#2c3e50",
    wallColor: "#e2e8f0",
    label: "Hostel A",
  },
  {
    id: "textile",
    name: "Dept of Textile & Clothing",
    position: [2.5, 0, -9.5],
    size: [2.8, 1.4, 2.6],
    roofType: "flat",
    roofColor: "#475569",
    wallColor: "#f8fafc",
    label: "Depart. of Textile",
  },
  {
    id: "transport",
    name: "Dept of Transport & Logistics",
    position: [12.5, 0, -4.0],
    size: [3.0, 2.0, 2.4],
    roofType: "flat",
    roofColor: "#52525b",
    wallColor: "#e4e4e7",
    label: "Transport & Logistics",
  },
  {
    id: "civil",
    name: "Dept of Civil Engineering",
    position: [17, 0, -9.5],
    size: [1.8, 2.6, 8.5],
    roofType: "flat",
    roofColor: "#3f3f46",
    wallColor: "#d4d4d8",
    label: "Civil Engineering",
  },
  {
    id: "cse",
    name: "Dept of Computer Science & Engineering",
    position: [-5.0, 0, 4.5],
    size: [8.0, 3.2, 2.2],
    roofType: "flat",
    roofColor: "#1e293b",
    wallColor: "#f1f5f9",
    label: "Sumanadasa Building",
  },
  {
    id: "Goda canteen",
    name: "Goda Canteen",
    position: [-5, 0, 7.7],
    size: [1.8, 1.5, 1.2],
    roofType: "hip",
    roofColor: "#9c2a2a",
    wallColor: "#fef3c7",
    label: "Goda Canteen",
  },
  {
    id: "Sentra",
    name: "Sentra Court",
    position: [-2.5, 0, 7.7],
    size: [3, 1.5, 1.2],
    roofType: "gabled",
    roofColor: "#1b4332",
    wallColor: "#d8f3dc",
    label: "Sentra Court",
  },
  {
    id: "canteen",
    name: "L Canteen",
    position: [1.7, 0, -0.5],
    size: [1.8, 1.5, 1.4],
    roofType: "hip",
    roofColor: "#c2410c",
    wallColor: "#ffedd5",
    label: "L Canteen",
  },
  {
    id: "it",
    name: "Faculty of Information Technology",
    position: [7.5, 0, 3],
    size: [1.4, 3.0, 2],
    roofType: "flat",
    roofColor: "#334155",
    wallColor: "#cbd5e1",
    label: "Faculty of IT",
  },
  {
    id: "hostel",
    name: "Hostel C",
    position: [11.0, 0, 3],
    size: [3.4, 1.6, 2.4],
    roofType: "gabled",
    roofColor: "#7f1d1d",
    wallColor: "#fee2e2",
    label: "Hostel",
  },
  {
    id: "buildeco",
    name: "Faculty of Business Science",
    position: [4.0, 0, -0.5],
    size: [2.2, 3.2, 1.2],
    roofType: "flat",
    roofColor: "#374151",
    wallColor: "#f3f4f6",
    label: "Faculty of Business Science",
  },
  {
    id: "maths",
    name: "Dept of Maths",
    position: [4.0, 0, -3.5],
    size: [2.2, 3.0, 2.0],
    roofType: "flat",
    roofColor: "#1f2937",
    wallColor: "#e5e7eb",
    label: "Dept of Maths",
  },
  {
    id: "medicine",
    name: "Faculty of Medicine",
    position: [17, 0, 0],
    size: [2.2, 4, 3.2],
    roofType: "hip",
    roofColor: "#581c87",
    wallColor: "#f3e8ff",
    label: "Faculty of Medicine",
  },
  {
    id: "electronics",
    name: "Dept of Electronics & Telecommunication Engineering",
    position: [3, 0, 5.3],
    size: [1.2, 4, 1.2],
    roofType: "flat",
    roofColor: "#0f172a",
    wallColor: "#e2e8f0",
    label: "Dept of Electronics & Telecommunication Engineering",
  },
  {
    id: "na1",
    name: "NA1&2",
    position: [18.5, 0, 6.0],
    size: [2.4, 2.0, 2.2],
    roofType: "flat",
    roofColor: "#4b5563",
    wallColor: "#f9fafb",
    label: "NA1&2",
  },
  {
    id: "wala_canteen",
    name: "Wala Canteen",
    position: [-10.0, 0, 5],
    size: [1, 0.8, 1],
    roofType: "shed",
    roofColor: "#831843",
    wallColor: "#fce7f3",
    label: "Wala Canteen",
  },
  {
    id: "material",
    name: "Dept of Material Science & Engineering",
    position: [-9.5, 0, 8.0],
    size: [2.0, 2.4, 2],
    roofType: "flat",
    roofColor: "#111827",
    wallColor: "#d1d5db",
    label: "Material Science",
  },
  {
    id: "chemical",
    name: "Dept of Chemical & Process Engineering",
    position: [-6.5, 0, 9.5],
    size: [3.0, 1.2, 2],
    roofType: "flat",
    roofColor: "#172554",
    wallColor: "#dbeafe",
    label: "Chemical & Process Eng",
  },
  {
    id: "mechanical",
    name: "Dept of Mechanical Engineering",
    position: [-11.5, 0, 12.5],
    size: [7.2, 2.4, 2.8],
    roofType: "shed",
    roofColor: "#27272a",
    wallColor: "#f4f4f5",
    label: "Mechanical Engineering",
  },
  {
    id: "registrar",
    name: "Registrar Office & Examination",
    position: [-4, 0, 14.2],
    size: [1.0, 1.5, 2],
    roofType: "gabled",
    roofColor: "#064e3b",
    wallColor: "#d1fae5",
    label: "Registrar Office",
  },
  {
    id: "admin",
    name: "Admin Building",
    position: [-2.0, 0, 14.5],
    size: [2.0, 2.2, 2.4],
    roofType: "hip",
    roofColor: "#7f1d1d",
    wallColor: "#fff1f2",
    label: "Admin",
  },
  {
    id: "intdesign",
    name: "Dept of Integrated Design",
    position: [5.5, 0, 7.5],
    size: [2.8, 2.2, 1],
    roofType: "flat",
    roofColor: "#14532d",
    wallColor: "#e8f5e9",
    label: "Integrated Design",
  },
  {
    id: "graduate",
    name: "Faculty of Graduate Studies",
    position: [3.5, 0, 10.5],
    size: [2.8, 2.2, 2.2],
    roofType: "flat",
    roofColor: "#312e81",
    wallColor: "#e0e7ff",
    label: "Graduate Studies",
  },
  {
    id: "library",
    name: "Library",
    position: [3.5, 0, 13.5],
    size: [2.8, 2.2, 1.8],
    roofType: "gabled",
    roofColor: "#a16207",
    wallColor: "#fefce8",
    label: "Library",
  },
];

export const WALK_BOUNDS = {
  minX: -22,
  maxX: 22,
  minZ: -18,
  maxZ: 20,
};

export const STABLE_INITIAL_ZONES: Zone[] = CAMPUS_LAYOUT.map((layout) => ({
  id: layout.id,
  name: layout.name,
  energyKw: 0,
  occupancy: 0,
  temperatureC: 0,
  status: "normal" as ZoneStatus,
  hasData: false,
}));

