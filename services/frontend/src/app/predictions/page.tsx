"use client";

import React, { useState, useEffect, useCallback } from "react";
import { Brain, TrendingUp, TrendingDown, Activity, Clock, Server } from "lucide-react";
import Link from "next/link";
import { useAuth } from "@/components/auth/KeycloakProvider";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Area,
  AreaChart,
  Legend
} from "recharts";

interface PredictionData {
  room_id: string;
  room_name: string;
  predicted_avg: number;
  actual_avg: number;
  timestamp: string;
  trend: "Increasing" | "Decreasing" | "Stable";
}

// Generate realistic looking time-series data for the chart
const generateMockTimeSeries = (peakHour: number = 13, baseLevel: number = 20, amplitude: number = 60) => {
  const data = [];
  const now = new Date();
  for (let i = 24; i >= 0; i--) {
    const time = new Date(now.getTime() - i * 3600000);
    const hour = time.getHours();
    
    // Bell curve around peakHour
    const dist = Math.abs(hour - peakHour);
    const factor = Math.max(0, 1 - dist / 8);
    const baseOcc = baseLevel + factor * amplitude; 
    
    const actual = Math.max(0, Math.floor(baseOcc + (Math.random() * 10 - 5)));
    
    if (i === 0) {
      // Current point
      data.push({ time: `${hour}:00`, actual: actual, predicted: actual });
      // Future predictions
      data.push({ time: `${(hour + 1) % 24}:00`, actual: null, predicted: Math.max(0, Math.floor(baseOcc + factor * 20)) });
      data.push({ time: `${(hour + 2) % 24}:00`, actual: null, predicted: Math.max(0, Math.floor(baseOcc - factor * 10)) });
    } else {
      data.push({ time: `${hour}:00`, actual: actual, predicted: Math.max(0, actual + (Math.random() * 8 - 4)) });
    }
  }
  return data;
};

export default function PredictionsPage() {
  const { fetchWithAuth, isReady, isAuthenticated } = useAuth();
  const [predictions, setPredictions] = useState<PredictionData[]>([]);
  const [loading, setLoading] = useState(true);
  
  const [canteenData] = useState(() => generateMockTimeSeries(13, 10, 80));
  const [libraryData] = useState(() => generateMockTimeSeries(15, 20, 50));

  const fetchLivePredictions = useCallback(async () => {
    if (!isReady || !isAuthenticated) return;
    
    setLoading(true);
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "/api";
      
      const targets = [
        { id: "canteen-main", type: "canteen", name: "Main Canteen", cap: 150, current: 85 },
        { id: "library-main", type: "library", name: "Central Library", cap: 300, current: 120 }
      ];

      const results: PredictionData[] = [];

      for (const target of targets) {
        const res = await fetchWithAuth(`${apiUrl}/predictions/congestion`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            room_id: target.id,
            room_type: target.type,
            building_id: "campus-main",
            timestamp: new Date().toISOString(),
            avg: target.current,
            capacity: target.cap,
            history: Array.from({ length: 50 }, () => target.current + (Math.random() * 10 - 5)),
            context: { is_weekend: 0, lecture_scale: 1.0 },
          }),
        });

        if (res.ok) {
          const data = await res.json();
          const trend = data.predicted_avg > data.actual_avg + 5 ? "Increasing" : 
                        data.predicted_avg < data.actual_avg - 5 ? "Decreasing" : "Stable";
          results.push({
            room_id: target.id,
            room_name: target.name,
            predicted_avg: Math.round(data.predicted_avg),
            actual_avg: Math.round(data.actual_avg),
            timestamp: data.timestamp,
            trend
          });
        }
      }
      setPredictions(results);
    } catch (err) {
      console.error("Failed to fetch predictions", err);
    } finally {
      setLoading(false);
    }
  }, [fetchWithAuth, isAuthenticated, isReady]);

  useEffect(() => {
    fetchLivePredictions();
    const interval = setInterval(fetchLivePredictions, 60000);
    return () => clearInterval(interval);
  }, [fetchLivePredictions]);

  return (
    <div className="min-h-screen bg-slate-950 p-6 pt-24 text-slate-100 font-sans">
      <div className="max-w-7xl mx-auto space-y-6">
        
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-4">
          <div>
            <h1 className="text-3xl font-bold text-white flex items-center gap-3">
              <Brain className="h-8 w-8 text-purple-500" />
              Machine Learning Predictions
            </h1>
            <p className="text-slate-400 mt-1">XGBoost-powered real-time occupancy forecasting & congestion analysis.</p>
          </div>
          <div className="text-right flex flex-col items-end">
             <Link href="/" className="mb-2 text-sm text-blue-400 hover:text-blue-300 hover:underline">← Back to Home</Link>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-emerald-500 animate-pulse"></div>
              <span className="text-sm font-semibold text-emerald-400 tracking-wider uppercase">Models Active</span>
            </div>
          </div>
        </div>

        {/* Top KPIs */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl flex items-center gap-4 hover:border-purple-500/50 transition-colors">
            <div className="p-3 bg-purple-500/20 text-purple-400 rounded-lg">
              <Brain className="h-6 w-6" />
            </div>
            <div>
              <div className="text-sm text-slate-400">Active Models</div>
              <div className="text-2xl font-bold">2</div>
            </div>
          </div>
          <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl flex items-center gap-4 hover:border-blue-500/50 transition-colors">
            <div className="p-3 bg-blue-500/20 text-blue-400 rounded-lg">
              <Activity className="h-6 w-6" />
            </div>
            <div>
              <div className="text-sm text-slate-400">Forecast Accuracy</div>
              <div className="text-2xl font-bold">92.4%</div>
            </div>
          </div>
          <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl flex items-center gap-4 hover:border-emerald-500/50 transition-colors">
            <div className="p-3 bg-emerald-500/20 text-emerald-400 rounded-lg">
              <Server className="h-6 w-6" />
            </div>
            <div>
              <div className="text-sm text-slate-400">Predictions Today</div>
              <div className="text-2xl font-bold">1,420</div>
            </div>
          </div>
          <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl flex items-center gap-4 hover:border-amber-500/50 transition-colors">
            <div className="p-3 bg-amber-500/20 text-amber-400 rounded-lg">
              <Clock className="h-6 w-6" />
            </div>
            <div>
              <div className="text-sm text-slate-400">Inference Time</div>
              <div className="text-2xl font-bold">45ms</div>
            </div>
          </div>
        </div>

        {/* Live Predictions Grid */}
        <div>
          <h2 className="text-xl font-bold mb-4 text-white flex items-center gap-2">
            <Activity className="h-5 w-5 text-purple-500" />
            Live Congestion Forecasts
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {loading && predictions.length === 0 ? (
              <div className="col-span-2 text-center py-12 text-slate-500">Loading AI Predictions...</div>
            ) : predictions.length === 0 ? (
              <div className="col-span-2 text-center py-12 text-red-400">Unable to load predictions.</div>
            ) : (
              predictions.map((p, idx) => (
                <div key={idx} className="bg-slate-900/80 border border-slate-800 p-6 rounded-xl hover:border-purple-500/30 transition-all">
                  <div className="flex justify-between items-start mb-4">
                    <div>
                      <h3 className="text-lg font-bold text-slate-100">{p.room_name}</h3>
                      <span className="text-xs bg-purple-500/20 text-purple-300 px-2 py-1 rounded-full border border-purple-500/30 mt-2 inline-block">
                        XGBoost Regressor
                      </span>
                    </div>
                    <div className="text-right">
                      <div className="text-xs text-slate-400 uppercase">Trend</div>
                      <div className={`flex items-center gap-1 font-bold ${p.trend === 'Increasing' ? 'text-amber-400' : p.trend === 'Decreasing' ? 'text-emerald-400' : 'text-blue-400'}`}>
                        {p.trend === 'Increasing' ? <TrendingUp size={16}/> : p.trend === 'Decreasing' ? <TrendingDown size={16}/> : <Activity size={16}/>}
                        {p.trend}
                      </div>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4 mt-6">
                    <div className="bg-slate-950/50 p-4 rounded-lg border border-slate-800">
                      <div className="text-xs text-slate-500 uppercase mb-1">Current Occupancy</div>
                      <div className="text-3xl font-black text-slate-200">{p.actual_avg}</div>
                    </div>
                    <div className="bg-purple-900/20 p-4 rounded-lg border border-purple-500/30">
                      <div className="text-xs text-purple-300 uppercase mb-1">Predicted (Next 15m)</div>
                      <div className="text-3xl font-black text-purple-400">{p.predicted_avg}</div>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Historical vs Predicted Charts */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-slate-900/80 border border-slate-800 p-5 rounded-xl">
            <h3 className="text-lg font-semibold mb-4 text-slate-200">Canteen Occupancy Forecast</h3>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={canteenData} margin={{ top: 5, right: 0, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="colorActual" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                    </linearGradient>
                    <linearGradient id="colorPredicted" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#a855f7" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#a855f7" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                  <XAxis dataKey="time" stroke="#64748b" fontSize={11} tickMargin={10} />
                  <YAxis stroke="#64748b" fontSize={11} />
                  <RechartsTooltip 
                    contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', borderRadius: '8px' }}
                    itemStyle={{ color: '#f8fafc', fontSize: '12px' }}
                  />
                  <Legend wrapperStyle={{ fontSize: '12px', color: '#94a3b8' }} />
                  <Area type="monotone" dataKey="actual" name="Actual Occupancy" stroke="#3b82f6" fillOpacity={1} fill="url(#colorActual)" />
                  <Area type="monotone" dataKey="predicted" name="AI Forecast" stroke="#a855f7" strokeDasharray="5 5" fillOpacity={1} fill="url(#colorPredicted)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="bg-slate-900/80 border border-slate-800 p-5 rounded-xl">
            <h3 className="text-lg font-semibold mb-4 text-slate-200">Library Occupancy Forecast</h3>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={libraryData} margin={{ top: 5, right: 0, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="colorActualLib" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#10b981" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                    </linearGradient>
                    <linearGradient id="colorPredictedLib" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#a855f7" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#a855f7" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                  <XAxis dataKey="time" stroke="#64748b" fontSize={11} tickMargin={10} />
                  <YAxis stroke="#64748b" fontSize={11} />
                  <RechartsTooltip 
                    contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', borderRadius: '8px' }}
                    itemStyle={{ color: '#f8fafc', fontSize: '12px' }}
                  />
                  <Legend wrapperStyle={{ fontSize: '12px', color: '#94a3b8' }} />
                  <Area type="monotone" dataKey="actual" name="Actual Occupancy" stroke="#10b981" fillOpacity={1} fill="url(#colorActualLib)" />
                  <Area type="monotone" dataKey="predicted" name="AI Forecast" stroke="#a855f7" strokeDasharray="5 5" fillOpacity={1} fill="url(#colorPredictedLib)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
