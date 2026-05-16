'use client';
import React, { useEffect, useState, useCallback, useRef } from 'react';
import { Power, Plus, Trash2, Thermometer, Users, Zap, LineChart, X } from 'lucide-react';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

type BM = 'normal' | 'random' | 'pattern' | 'anomaly';

interface S {
  id: string;
  name: string;
  building_id: string;
  floor: number;
  room_id: string;
  sensor_type: string;
  enabled: boolean;
  behavior_mode: BM;
  config: { min_value: number; max_value: number; interval_ms: number; pattern: number[]; anomaly_prob: number };
}

interface ValueSnap { value: number; timestamp_ms: number | null }
interface HistPoint { t: number; v: number }

const ICON: Record<string, any> = {
  temperature: React.createElement(Thermometer, { size: 16 }),
  occupancy: React.createElement(Users, { size: 16 }),
  energy: React.createElement(Zap, { size: 16 }),
};
const TCOL: Record<string, string> = { temperature: 'text-red-400', occupancy: 'text-blue-400', energy: 'text-yellow-400' };
const UNIT: Record<string, string> = { temperature: '°C', occupancy: '', energy: 'W' };
const MCOL: Record<string, string> = {
  normal: 'bg-emerald-900/60 text-emerald-300 border-emerald-700',
  random: 'bg-purple-900/60 text-purple-300 border-purple-700',
  pattern: 'bg-cyan-900/60 text-cyan-300 border-cyan-700',
  anomaly: 'bg-red-900/60 text-red-300 border-red-700',
};

function Sparkline({ data, color }: { data: number[]; color: string }) {
  if (data.length < 2) return React.createElement('div', { className: 'w-24 h-8' });
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * 96;
    const y = 30 - ((v - min) / range) * 26 - 2;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  return React.createElement('svg', { width: 96, height: 32, className: 'block' },
    React.createElement('polyline', { points: pts, fill: 'none', stroke: color, strokeWidth: 1.5, strokeLinejoin: 'round', strokeLinecap: 'round' })
  );
}

export default function SensorPanel() {
  const [sensors, setSensors] = useState<S[]>([]);
  const [values, setValues] = useState<Record<string, ValueSnap>>({});
  const [history, setHistory] = useState<Record<string, number[]>>({});
  const [ft, setFt] = useState('');
  const [search, setSearch] = useState('');
  const [show, setShow] = useState(false);
  const [err, setErr] = useState('');
  const [detail, setDetail] = useState<S | null>(null);
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 30;

  const fetchS = useCallback(async () => {
    try {
      const q = ft ? '?type=' + ft : '';
      const r = await fetch(API + '/api/sensors' + q);
      const d = await r.json();
      setSensors(d.sensors || []);
      setErr('');
    } catch {
      setErr('Backend offline. Start sim-control backend on port 8000.');
      setSensors([]);
    }
  }, [ft]);

  const fetchValues = useCallback(async () => {
    try {
      const r = await fetch(API + '/api/readings');
      const d: Record<string, ValueSnap> = await r.json();
      setValues(d);
      setHistory(prev => {
        const next = { ...prev };
        for (const [id, snap] of Object.entries(d)) {
          const arr = next[id] || [];
          if (arr.length === 0 || arr[arr.length - 1] !== snap.value) {
            next[id] = [...arr.slice(-29), snap.value];
          }
        }
        return next;
      });
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { fetchS(); }, [fetchS]);
  useEffect(() => {
    fetchValues();
    const i = setInterval(fetchValues, 2000);
    return () => clearInterval(i);
  }, [fetchValues]);

  const tog = async (id: string) => { await fetch(API + '/api/sensors/' + id + '/toggle', { method: 'POST' }); fetchS(); };
  const del = async (id: string) => { await fetch(API + '/api/sensors/' + id, { method: 'DELETE' }); fetchS(); };
  const bulk = async (action: 'enable' | 'disable' | 'reset') => {
    await fetch(API + '/api/sensors/bulk/' + action, { method: 'POST' });
    fetchS();
  };
  const sm = async (id: string, m: BM) => {
    await fetch(API + '/api/sensors/' + id, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ behavior_mode: m })
    });
    fetchS();
  };

  const filtered = sensors.filter(s => !search || s.name.toLowerCase().includes(search.toLowerCase()) || s.room_id.toLowerCase().includes(search.toLowerCase()) || s.building_id.toLowerCase().includes(search.toLowerCase()));
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageItems = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  useEffect(() => { setPage(0); }, [ft, search]);

  return React.createElement('div', null,
    React.createElement('div', { className: 'flex flex-wrap items-center gap-3 mb-4' },
      React.createElement('h2', { className: 'text-lg font-semibold' }, 'Sensors'),
      React.createElement('span', { className: 'text-xs text-slate-500' }, filtered.length + ' / ' + sensors.length),
      React.createElement('select', { value: ft, onChange: (e: any) => setFt(e.target.value), className: 'bg-slate-800 border border-slate-700 rounded px-2 py-1 text-sm' },
        React.createElement('option', { value: '' }, 'All types'),
        React.createElement('option', { value: 'temperature' }, 'Temperature'),
        React.createElement('option', { value: 'occupancy' }, 'Occupancy'),
        React.createElement('option', { value: 'energy' }, 'Energy')
      ),
      React.createElement('input', { value: search, onChange: (e: any) => setSearch(e.target.value), placeholder: 'Search name/room/building...', className: 'flex-1 min-w-[200px] bg-slate-800 border border-slate-700 rounded px-3 py-1 text-sm' }),
      React.createElement('button', { onClick: () => setShow(true), className: 'flex items-center gap-2 bg-emerald-500 hover:bg-emerald-400 text-slate-900 px-4 py-2 rounded-lg text-sm font-semibold' },
        React.createElement(Plus, { size: 16 }), 'Add'
      ),
      React.createElement('button', { onClick: () => bulk('enable'), className: 'bg-slate-800 hover:bg-slate-700 border border-emerald-700 text-emerald-300 px-3 py-2 rounded-lg text-xs font-semibold' }, 'All On'),
      React.createElement('button', { onClick: () => bulk('disable'), className: 'bg-slate-800 hover:bg-slate-700 border border-rose-700 text-rose-300 px-3 py-2 rounded-lg text-xs font-semibold' }, 'All Off'),
      React.createElement('button', { onClick: () => bulk('reset'), className: 'bg-slate-800 hover:bg-slate-700 border border-amber-700 text-amber-300 px-3 py-2 rounded-lg text-xs font-semibold' }, 'Reset')
    ),
    err && React.createElement('div', { className: 'bg-red-950 border border-red-800 text-red-200 rounded-xl p-4 text-sm mb-3' }, err),
    React.createElement('div', { className: 'grid gap-2' },
      pageItems.map((s: S) => {
        const snap = values[s.id];
        const hist = history[s.id] || [];
        const unit = UNIT[s.sensor_type] || '';
        return React.createElement('div', {
          key: s.id,
          className: 'bg-slate-900 border rounded-lg px-4 py-3 flex items-center gap-4 ' + (s.enabled ? 'border-slate-800' : 'border-slate-800 opacity-50')
        },
          React.createElement('span', { className: TCOL[s.sensor_type] + ' shrink-0' }, ICON[s.sensor_type]),
          React.createElement('div', { className: 'min-w-0 flex-1' },
            React.createElement('div', { className: 'font-medium text-sm truncate' }, s.name),
            React.createElement('div', { className: 'text-xs text-slate-500 truncate' },
              s.building_id + ' · ' + s.room_id + ' · floor ' + s.floor
            )
          ),
          React.createElement('div', { className: 'flex items-center gap-3 shrink-0' },
            React.createElement('div', { className: 'text-right tabular-nums' },
              React.createElement('div', { className: 'text-base font-bold ' + (snap ? TCOL[s.sensor_type] : 'text-slate-600') },
                snap ? snap.value.toFixed(2) + (unit ? ' ' + unit : '') : '—'
              ),
              React.createElement('div', { className: 'text-[10px] text-slate-500' },
                'range ' + s.config.min_value + '–' + s.config.max_value
              )
            ),
            React.createElement(Sparkline, { data: hist, color: snap ? sparkColor(s.sensor_type) : '#475569' }),
            React.createElement('select', {
              value: s.behavior_mode, onChange: (e: any) => sm(s.id, e.target.value),
              className: 'text-xs px-2 py-1 rounded border ' + MCOL[s.behavior_mode]
            },
              React.createElement('option', { value: 'normal' }, 'Normal'),
              React.createElement('option', { value: 'random' }, 'Random'),
              React.createElement('option', { value: 'pattern' }, 'Pattern'),
              React.createElement('option', { value: 'anomaly' }, 'Anomaly')
            ),
            React.createElement('button', { onClick: () => setDetail(s), className: 'p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300', title: 'View signal' },
              React.createElement(LineChart, { size: 14 })
            ),
            React.createElement('button', { onClick: () => tog(s.id), title: s.enabled ? 'Disable' : 'Enable',
              className: 'p-2 rounded-lg ' + (s.enabled ? 'bg-emerald-900/60 text-emerald-400 hover:bg-emerald-800/60' : 'bg-slate-800 text-slate-500 hover:bg-slate-700')
            },
              React.createElement(Power, { size: 14 })
            ),
            React.createElement('button', { onClick: () => del(s.id), title: 'Delete',
              className: 'p-2 rounded-lg hover:bg-red-900/40 text-slate-500 hover:text-red-400'
            },
              React.createElement(Trash2, { size: 14 })
            )
          )
        );
      }),
      filtered.length === 0 && React.createElement('div', { className: 'text-center text-slate-500 py-12' }, 'No sensors match.')
    ),
    pageCount > 1 && React.createElement('div', { className: 'flex items-center justify-center gap-2 mt-4 text-sm' },
      React.createElement('button', { disabled: page === 0, onClick: () => setPage(p => p - 1), className: 'px-3 py-1 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-30' }, 'Prev'),
      React.createElement('span', { className: 'text-slate-500' }, 'Page ' + (page + 1) + ' / ' + pageCount),
      React.createElement('button', { disabled: page >= pageCount - 1, onClick: () => setPage(p => p + 1), className: 'px-3 py-1 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-30' }, 'Next')
    ),
    show && React.createElement(AddForm, { onClose: () => { setShow(false); fetchS(); } }),
    detail && React.createElement(SensorDetail, { sensor: detail, onClose: () => setDetail(null) })
  );
}

function sparkColor(t: string): string {
  if (t === 'temperature') return '#f87171';
  if (t === 'occupancy') return '#60a5fa';
  if (t === 'energy') return '#facc15';
  return '#94a3b8';
}

function SensorDetail({ sensor, onClose }: { sensor: S; onClose: () => void }) {
  const [pts, setPts] = useState<HistPoint[]>([]);
  const timer = useRef<any>(null);

  const load = useCallback(async () => {
    try {
      const r = await fetch(API + '/api/readings/' + sensor.id + '/history');
      const d = await r.json();
      setPts(d.points || []);
    } catch { /* ignore */ }
  }, [sensor.id]);

  useEffect(() => {
    load();
    timer.current = setInterval(load, 2000);
    return () => clearInterval(timer.current);
  }, [load]);

  const unit = UNIT[sensor.sensor_type] || '';
  const W = 700, H = 200;
  const xs = pts.map(p => p.t);
  const ys = pts.map(p => p.v);
  const minY = ys.length ? Math.min(...ys, sensor.config.min_value) : sensor.config.min_value;
  const maxY = ys.length ? Math.max(...ys, sensor.config.max_value) : sensor.config.max_value;
  const ry = maxY - minY || 1;
  const minX = xs.length ? xs[0] : 0;
  const maxX = xs.length ? xs[xs.length - 1] : 1;
  const rx = maxX - minX || 1;
  const poly = pts.map(p => {
    const x = ((p.t - minX) / rx) * (W - 40) + 30;
    const y = H - 20 - ((p.v - minY) / ry) * (H - 40);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  const last = pts[pts.length - 1];

  return React.createElement('div', { className: 'fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4', onClick: onClose },
    React.createElement('div', { className: 'bg-slate-900 border border-slate-700 rounded-xl p-6 w-full max-w-3xl', onClick: (e: any) => e.stopPropagation() },
      React.createElement('div', { className: 'flex items-start justify-between mb-4' },
        React.createElement('div', null,
          React.createElement('div', { className: 'flex items-center gap-2' },
            React.createElement('span', { className: TCOL[sensor.sensor_type] }, ICON[sensor.sensor_type]),
            React.createElement('h2', { className: 'text-lg font-semibold' }, sensor.name)
          ),
          React.createElement('div', { className: 'text-xs text-slate-500 mt-1' },
            sensor.building_id + ' · ' + sensor.room_id + ' · floor ' + sensor.floor + ' · ' + sensor.sensor_type + ' · ' + sensor.behavior_mode
          )
        ),
        React.createElement('button', { onClick: onClose, className: 'p-2 hover:bg-slate-800 rounded-lg' }, React.createElement(X, { size: 16 }))
      ),
      React.createElement('div', { className: 'grid grid-cols-3 gap-3 mb-4' },
        statCard('Current', last ? last.v.toFixed(2) + (unit ? ' ' + unit : '') : '—', sparkColor(sensor.sensor_type)),
        statCard('Min observed', ys.length ? Math.min(...ys).toFixed(2) : '—', '#94a3b8'),
        statCard('Max observed', ys.length ? Math.max(...ys).toFixed(2) : '—', '#94a3b8')
      ),
      React.createElement('div', { className: 'bg-slate-950 border border-slate-800 rounded-lg p-3' },
        pts.length < 2
          ? React.createElement('div', { className: 'text-center text-slate-500 py-12 text-sm' }, 'Waiting for samples...')
          : React.createElement('svg', { width: '100%', viewBox: `0 0 ${W} ${H}` },
            React.createElement('line', { x1: 30, x2: W - 10, y1: H - 20, y2: H - 20, stroke: '#334155', strokeWidth: 1 }),
            React.createElement('line', { x1: 30, x2: 30, y1: 10, y2: H - 20, stroke: '#334155', strokeWidth: 1 }),
            React.createElement('text', { x: 4, y: 14, fontSize: 10, fill: '#64748b' }, maxY.toFixed(1)),
            React.createElement('text', { x: 4, y: H - 22, fontSize: 10, fill: '#64748b' }, minY.toFixed(1)),
            React.createElement('polyline', {
              points: poly, fill: 'none', stroke: sparkColor(sensor.sensor_type),
              strokeWidth: 2, strokeLinejoin: 'round', strokeLinecap: 'round'
            })
          )
      ),
      last && React.createElement('div', { className: 'text-xs text-slate-500 mt-3 tabular-nums' },
        'Last sample: ' + new Date(last.t).toLocaleString() + ' · ' + pts.length + ' points (~' + (pts.length * 5) + 's window)'
      )
    )
  );
}

function statCard(label: string, value: string, color: string) {
  return React.createElement('div', { className: 'bg-slate-950 border border-slate-800 rounded-lg p-3' },
    React.createElement('div', { className: 'text-xs text-slate-500' }, label),
    React.createElement('div', { className: 'text-xl font-bold tabular-nums mt-1', style: { color } }, value)
  );
}

function AddForm({ onClose }: { onClose: () => void }) {
  const [f, setF] = useState({ name: '', bid: 'library', floor: 0, rid: 'L001', stype: 'temperature', mode: 'normal', cfg: { min_value: 20, max_value: 35, interval_ms: 5000, pattern: [] as number[], anomaly_prob: 0.05 } });
  const sub = async () => {
    await fetch(API + '/api/sensors', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: f.name, building_id: f.bid, floor: f.floor, room_id: f.rid, sensor_type: f.stype, behavior_mode: f.mode, config: f.cfg })
    });
    onClose();
  };
  return React.createElement('div', { className: 'fixed inset-0 bg-black/60 flex items-center justify-center z-50', onClick: onClose },
    React.createElement('div', { className: 'bg-slate-900 border border-slate-700 rounded-xl p-6 w-full max-w-md', onClick: (e: any) => e.stopPropagation() },
      React.createElement('h3', { className: 'text-lg font-semibold mb-4' }, 'Add Sensor'),
      React.createElement('div', { className: 'space-y-3' },
        React.createElement('input', { placeholder: 'Name', value: f.name, onChange: (e: any) => setF({ ...f, name: e.target.value }), className: 'w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm' }),
        React.createElement('div', { className: 'grid grid-cols-2 gap-2' },
          React.createElement('input', { placeholder: 'Building ID', value: f.bid, onChange: (e: any) => setF({ ...f, bid: e.target.value }), className: 'bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm' }),
          React.createElement('input', { placeholder: 'Room ID', value: f.rid, onChange: (e: any) => setF({ ...f, rid: e.target.value }), className: 'bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm' })
        ),
        React.createElement('div', { className: 'grid grid-cols-2 gap-2' },
          React.createElement('input', { type: 'number', placeholder: 'Floor', value: f.floor, onChange: (e: any) => setF({ ...f, floor: +e.target.value }), className: 'bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm' }),
          React.createElement('select', { value: f.stype, onChange: (e: any) => setF({ ...f, stype: e.target.value }), className: 'bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm' },
            React.createElement('option', { value: 'temperature' }, 'Temperature'),
            React.createElement('option', { value: 'occupancy' }, 'Occupancy'),
            React.createElement('option', { value: 'energy' }, 'Energy')
          )
        ),
        React.createElement('div', { className: 'grid grid-cols-2 gap-2' },
          React.createElement('input', { type: 'number', placeholder: 'Min', value: f.cfg.min_value, onChange: (e: any) => setF({ ...f, cfg: { ...f.cfg, min_value: +e.target.value } }), className: 'bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm' }),
          React.createElement('input', { type: 'number', placeholder: 'Max', value: f.cfg.max_value, onChange: (e: any) => setF({ ...f, cfg: { ...f.cfg, max_value: +e.target.value } }), className: 'bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm' })
        ),
        React.createElement('select', { value: f.mode, onChange: (e: any) => setF({ ...f, mode: e.target.value }), className: 'w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm' },
          React.createElement('option', { value: 'normal' }, 'Normal'),
          React.createElement('option', { value: 'random' }, 'Random'),
          React.createElement('option', { value: 'pattern' }, 'Pattern'),
          React.createElement('option', { value: 'anomaly' }, 'Anomaly')
        )
      ),
      React.createElement('div', { className: 'flex gap-2 mt-4' },
        React.createElement('button', { onClick: sub, className: 'flex-1 bg-emerald-500 hover:bg-emerald-400 text-slate-900 py-2 rounded-lg text-sm font-semibold' }, 'Create'),
        React.createElement('button', { onClick: onClose, className: 'flex-1 bg-slate-800 hover:bg-slate-700 py-2 rounded-lg text-sm' }, 'Cancel')
      )
    )
  );
}
