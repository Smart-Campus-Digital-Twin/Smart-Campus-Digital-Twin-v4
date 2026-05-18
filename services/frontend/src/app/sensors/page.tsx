"use client";

import React, { useEffect, useState } from "react";
import { useAuth } from "@/components/auth/KeycloakProvider";
import { SensorHealth, AnomalyEntry } from "@/components/dashboard/DashboardTypes";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
} from "recharts";
import { Activity, AlertTriangle, CheckCircle, Database, ServerCrash, XCircle } from "lucide-react";

export default function SensorsPage() {
  const { fetchWithAuth, isReady } = useAuth();
  const [sensors, setSensors] = useState<SensorHealth[]>([]);
  const [anomalies, setAnomalies] = useState<AnomalyEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!isReady) return;
    let cancelled = false;

    const fetchData = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || "/api";
        const [resSensors, resAnomalies] = await Promise.all([
          fetchWithAuth(`${apiUrl}/campus/sensors/health`),
          fetchWithAuth(`${apiUrl}/campus/anomalies/recent?limit=100`)
        ]);

        if (resSensors.ok && !cancelled) {
          const data: SensorHealth[] = await resSensors.json();
          setSensors(data);
        }
        
        if (resAnomalies.ok && !cancelled) {
          const data: AnomalyEntry[] = await resAnomalies.json();
          setAnomalies(data);
        }
      } catch (_e) {
        // ignore
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    fetchData();
    const t = setInterval(fetchData, 10000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [fetchWithAuth, isReady]);

  if (loading) {
    return <div className="flex h-screen items-center justify-center text-slate-400 bg-slate-950">Loading sensor data...</div>;
  }

  // Derived metrics
  const totalSensors = sensors.length;
  const workingSensors = sensors.filter((s) => !s.broken && !s.anomalous).length;
  const downSensors = sensors.filter((s) => s.broken).length;
  const anomalousSensors = sensors.filter((s) => s.anomalous && !s.broken).length;
  const workingPercentage = totalSensors > 0 ? Math.round((workingSensors / totalSensors) * 100) : 0;

  // Types distribution
  const typesMap: Record<string, number> = {};
  sensors.forEach(s => {
    typesMap[s.sensor_type] = (typesMap[s.sensor_type] || 0) + 1;
  });
  const typeData = Object.keys(typesMap).map(key => ({
    name: key,
    count: typesMap[key]
  }));

  // Status Pie Chart Data
  const statusData = [
    { name: "Working", value: workingSensors, color: "#10b981" },
    { name: "Anomalous", value: anomalousSensors, color: "#f59e0b" },
    { name: "Down", value: downSensors, color: "#ef4444" },
  ];

  // Per-type status data
  const typesList = Object.keys(typesMap);
  const typeStatusData = typesList.map(type => {
    const typeSensors = sensors.filter(s => s.sensor_type === type);
    const w = typeSensors.filter((s) => !s.broken && !s.anomalous).length;
    const a = typeSensors.filter((s) => s.anomalous && !s.broken).length;
    const d = typeSensors.filter((s) => s.broken).length;
    return {
      type,
      total: typeSensors.length,
      data: [
        { name: "Working", value: w, color: "#10b981" },
        { name: "Anomalous", value: a, color: "#f59e0b" },
        { name: "Down", value: d, color: "#ef4444" },
      ]
    };
  });

  // Status by Building (Top 10)
  const buildingMap: Record<string, { ok: number, anom: number, down: number }> = {};
  sensors.forEach(s => {
    const bId = s.building_id || "Unknown";
    if (!buildingMap[bId]) buildingMap[bId] = { ok: 0, anom: 0, down: 0 };
    if (s.broken) buildingMap[bId].down++;
    else if (s.anomalous) buildingMap[bId].anom++;
    else buildingMap[bId].ok++;
  });
  
  const buildingData = Object.keys(buildingMap).map(bId => ({
    name: bId,
    OK: buildingMap[bId].ok,
    Anomalous: buildingMap[bId].anom,
    Down: buildingMap[bId].down,
  })).sort((a, b) => (b.OK + b.Anomalous + b.Down) - (a.OK + a.Anomalous + a.Down)).slice(0, 10);

  // Freshness Data
  let fresh = 0, lagging = 0, stale = 0;
  sensors.forEach(s => {
    const sec = s.seconds_since;
    if (sec === null || s.broken) stale++;
    else if (sec < 15) fresh++;
    else if (sec < 60) lagging++;
    else stale++;
  });
  const freshnessData = [
    { name: "Live (<15s)", value: fresh, color: "#10b981" },
    { name: "Lagging (15-60s)", value: lagging, color: "#f59e0b" },
    { name: "Stale/Down (>60s)", value: stale, color: "#ef4444" },
  ];

  return (
    <div className="min-h-screen bg-slate-950 p-6 pt-24 text-slate-100 font-sans">
      <div className="max-w-7xl mx-auto space-y-6">
        
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-4">
          <div>
            <h1 className="text-3xl font-bold text-white flex items-center gap-3">
              <Database className="h-8 w-8 text-blue-500" />
              All Sensors Details
            </h1>
            <p className="text-slate-400 mt-1">Comprehensive overview of campus sensor network health and statistics.</p>
          </div>
          <div className="text-right flex flex-col items-end">
             <a href="/" className="mb-2 text-sm text-blue-400 hover:text-blue-300 hover:underline">← Back to Home</a>
            <div className="text-4xl font-black text-blue-400">{workingPercentage}%</div>
            <div className="text-xs text-slate-500 uppercase tracking-widest mt-1">Network Health</div>
          </div>
        </div>

        {/* Top KPIs */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl flex items-center gap-4 hover:border-blue-500/50 transition-colors">
            <div className="p-3 bg-blue-500/20 text-blue-400 rounded-lg">
              <Activity className="h-6 w-6" />
            </div>
            <div>
              <div className="text-sm text-slate-400">Total Sensors</div>
              <div className="text-2xl font-bold">{totalSensors}</div>
            </div>
          </div>
          
          <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl flex items-center gap-4 hover:border-emerald-500/50 transition-colors">
            <div className="p-3 bg-emerald-500/20 text-emerald-400 rounded-lg">
              <CheckCircle className="h-6 w-6" />
            </div>
            <div>
              <div className="text-sm text-slate-400">Working OK</div>
              <div className="text-2xl font-bold">{workingSensors}</div>
            </div>
          </div>

          <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl flex items-center gap-4 hover:border-amber-500/50 transition-colors">
            <div className="p-3 bg-amber-500/20 text-amber-400 rounded-lg">
              <AlertTriangle className="h-6 w-6" />
            </div>
            <div>
              <div className="text-sm text-slate-400">Anomalous</div>
              <div className="text-2xl font-bold">{anomalousSensors}</div>
            </div>
          </div>

          <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl flex items-center gap-4 hover:border-red-500/50 transition-colors">
            <div className="p-3 bg-red-500/20 text-red-400 rounded-lg">
              <XCircle className="h-6 w-6" />
            </div>
            <div>
              <div className="text-sm text-slate-400">Offline / Down</div>
              <div className="text-2xl font-bold">{downSensors}</div>
            </div>
          </div>
        </div>

        {/* Charts Row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Sensor Types Bar Chart */}
          <div className="bg-slate-900/80 border border-slate-800 p-5 rounded-xl">
            <h3 className="text-lg font-semibold mb-4 text-slate-200">Sensors by Type</h3>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={typeData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis dataKey="name" stroke="#94a3b8" fontSize={12} />
                  <YAxis stroke="#94a3b8" fontSize={12} />
                  <Tooltip 
                    cursor={{ fill: '#1e293b' }}
                    contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', color: '#f8fafc', borderRadius: '8px' }}
                  />
                  <Bar dataKey="count" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Status Distribution Pie Chart */}
          <div className="bg-slate-900/80 border border-slate-800 p-5 rounded-xl">
            <h3 className="text-lg font-semibold mb-4 text-slate-200">Network Status Distribution</h3>
            <div className="h-64 flex justify-center">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={statusData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={80}
                    paddingAngle={5}
                    dataKey="value"
                    stroke="none"
                  >
                    {statusData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip 
                    contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', color: '#f8fafc', borderRadius: '8px' }}
                    itemStyle={{ color: '#f8fafc' }}
                  />
                  <Legend wrapperStyle={{ fontSize: '12px', color: '#94a3b8' }} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Type-Specific Visualizations */}
        <div>
          <h2 className="text-xl font-bold mb-4 text-white flex items-center gap-2">
            <Activity className="h-5 w-5 text-blue-500" />
            Analysis by Sensor Type
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {typeStatusData.map((ts, idx) => (
              <div key={idx} className="bg-slate-900/80 border border-slate-800 p-5 rounded-xl hover:border-slate-700 transition-colors">
                <div className="flex justify-between items-center mb-2">
                  <h3 className="text-md font-bold text-slate-100 capitalize">{ts.type} Sensors</h3>
                  <span className="text-xs bg-slate-800 text-slate-300 px-2 py-1 rounded-full border border-slate-700">{ts.total} Total</span>
                </div>
                <div className="h-40 flex justify-center">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={ts.data}
                        cx="50%"
                        cy="50%"
                        innerRadius={35}
                        outerRadius={55}
                        paddingAngle={5}
                        dataKey="value"
                        stroke="none"
                      >
                        {ts.data.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.color} />
                        ))}
                      </Pie>
                      <Tooltip 
                        contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', color: '#f8fafc', borderRadius: '8px' }}
                        itemStyle={{ color: '#f8fafc', fontSize: '12px' }}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                {/* Custom Legend */}
                <div className="flex justify-between text-[11px] mt-2 bg-slate-950/50 p-2 rounded-lg border border-slate-800/50">
                  <div className="flex flex-col items-center"><span className="text-emerald-400 font-bold">{ts.data[0].value}</span><span className="text-slate-500">OK</span></div>
                  <div className="flex flex-col items-center"><span className="text-amber-400 font-bold">{ts.data[1].value}</span><span className="text-slate-500">Anom</span></div>
                  <div className="flex flex-col items-center"><span className="text-red-400 font-bold">{ts.data[2].value}</span><span className="text-slate-500">Down</span></div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Extra Data Visualizations */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Building Distribution Stacked Bar Chart */}
          <div className="bg-slate-900/80 border border-slate-800 p-5 rounded-xl">
            <h3 className="text-lg font-semibold mb-4 text-slate-200">Sensor Status by Building (Top 10)</h3>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={buildingData} layout="vertical" margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" horizontal={false} />
                  <XAxis type="number" stroke="#94a3b8" fontSize={12} />
                  <YAxis dataKey="name" type="category" stroke="#94a3b8" fontSize={11} width={100} />
                  <Tooltip 
                    cursor={{ fill: '#1e293b' }}
                    contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', color: '#f8fafc', borderRadius: '8px' }}
                  />
                  <Legend wrapperStyle={{ fontSize: '12px', color: '#94a3b8' }} />
                  <Bar dataKey="OK" stackId="a" fill="#10b981" radius={[0, 0, 0, 0]} />
                  <Bar dataKey="Anomalous" stackId="a" fill="#f59e0b" radius={[0, 0, 0, 0]} />
                  <Bar dataKey="Down" stackId="a" fill="#ef4444" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Freshness/Latency Pie/Donut Chart */}
          <div className="bg-slate-900/80 border border-slate-800 p-5 rounded-xl">
            <h3 className="text-lg font-semibold mb-4 text-slate-200">Data Freshness (Latency)</h3>
            <div className="h-64 flex justify-center">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={freshnessData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={80}
                    paddingAngle={5}
                    dataKey="value"
                    stroke="none"
                  >
                    {freshnessData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip 
                    contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', color: '#f8fafc', borderRadius: '8px' }}
                    itemStyle={{ color: '#f8fafc' }}
                  />
                  <Legend wrapperStyle={{ fontSize: '12px', color: '#94a3b8' }} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Detailed Logs & Tables */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Offline Sensors Table */}
          <div className="bg-slate-900/80 border border-slate-800 p-5 rounded-xl flex flex-col h-[400px]">
            <h3 className="text-lg font-semibold mb-4 text-red-400 flex items-center gap-2">
              <ServerCrash className="h-5 w-5" /> Offline & Anomalous Sensors
            </h3>
            <div className="overflow-y-auto flex-1 pr-2">
              <table className="w-full text-sm text-left">
                <thead className="text-xs text-slate-400 uppercase bg-slate-800/50 sticky top-0">
                  <tr>
                    <th className="px-4 py-3 rounded-tl-lg">Sensor ID</th>
                    <th className="px-4 py-3">Type</th>
                    <th className="px-4 py-3">Location</th>
                    <th className="px-4 py-3 rounded-tr-lg">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {sensors.filter(s => s.broken || s.anomalous).map((s) => (
                    <tr key={s.sensor_id} className="border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors">
                      <td className="px-4 py-3 font-medium text-slate-200">{s.sensor_id}</td>
                      <td className="px-4 py-3 text-slate-400">{s.sensor_type}</td>
                      <td className="px-4 py-3 text-slate-400">{s.building_id} - {s.room_id}</td>
                      <td className="px-4 py-3">
                        {s.broken ? (
                          <span className="bg-red-500/10 text-red-400 px-2 py-1 rounded text-xs font-semibold">DOWN</span>
                        ) : (
                          <span className="bg-amber-500/10 text-amber-400 px-2 py-1 rounded text-xs font-semibold">ANOMALY</span>
                        )}
                      </td>
                    </tr>
                  ))}
                  {sensors.filter(s => s.broken || s.anomalous).length === 0 && (
                    <tr>
                      <td colSpan={4} className="px-4 py-8 text-center text-slate-500">
                        No offline or anomalous sensors detected.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Anomaly Logs */}
          <div className="bg-slate-900/80 border border-slate-800 p-5 rounded-xl flex flex-col h-[400px]">
            <h3 className="text-lg font-semibold mb-4 text-amber-400 flex items-center gap-2">
              <AlertTriangle className="h-5 w-5" /> Recent Error Logs
            </h3>
            <div className="overflow-y-auto flex-1 pr-2 space-y-3">
              {anomalies.length > 0 ? (
                anomalies.map((a, i) => (
                  <div key={`${a.detected_at}-${i}`} className="p-3 bg-slate-800/40 rounded-lg border border-slate-700/50">
                    <div className="flex justify-between items-start mb-1">
                      <span className={`text-sm font-semibold ${a.severity === 'critical' ? 'text-red-400' : 'text-amber-400'}`}>
                        {a.rule}
                      </span>
                      <span className="text-xs text-slate-500">
                        {new Date(a.detected_at).toLocaleString()}
                      </span>
                    </div>
                    <div className="text-xs text-slate-400 mb-1">
                      Sensor: <span className="text-slate-300">{a.sensor_id}</span> | Location: <span className="text-slate-300">{a.room_id}</span>
                    </div>
                    <div className="text-xs text-slate-500">
                      Value detected: {JSON.stringify(a.value)}
                    </div>
                  </div>
                ))
              ) : (
                <div className="flex h-full items-center justify-center text-slate-500">
                  No recent error logs.
                </div>
              )}
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
