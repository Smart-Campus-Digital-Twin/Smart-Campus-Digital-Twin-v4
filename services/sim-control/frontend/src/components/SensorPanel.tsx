'use client';
import React, { useEffect, useState, useCallback } from 'react';
import { Power, Plus, Trash2, Thermometer, Users, Zap } from 'lucide-react';
const API = 'http://localhost:8000';
type BM = 'normal' | 'random' | 'pattern' | 'anomaly';
interface S { id: string; name: string; bid: string; floor: number; rid: string; stype: string; on: boolean; mode: BM; cfg: any; }
const ICO: Record<string, any> = {
  temperature: React.createElement(Thermometer, {size: 16}),
  occupancy: React.createElement(Users, {size: 16}),
  energy: React.createElement(Zap, {size: 16}),
};
const TCOL: Record<string, string> = { temperature: 'text-red-400', occupancy: 'text-blue-400', energy: 'text-yellow-400' };
const MCOL: Record<string, string> = { normal: 'bg-green-900 text-green-300', random: 'bg-purple-900 text-purple-300', pattern: 'bg-cyan-900 text-cyan-300', anomaly: 'bg-red-900 text-red-300' };

export default function SensorPanel() {
  const [sensors, setSensors] = useState<S[]>([]);
  const [ft, setFt] = useState('');
  const [show, setShow] = useState(false);
  const fetchS = useCallback(async () => {
    const q = ft ? '?type=' + ft : '';
    const r = await fetch(API + '/api/sensors' + q);
    const d = await r.json();
    setSensors(d.sensors || []);
  }, [ft]);
  useEffect(() => { fetchS(); }, [fetchS]);
  const tog = async (id: string) => { await fetch(API + '/api/sensors/' + id + '/toggle', { method: 'POST' }); fetchS(); };
  const del = async (id: string) => { await fetch(API + '/api/sensors/' + id, { method: 'DELETE' }); fetchS(); };
  const sm = async (id: string, m: BM) => {
    await fetch(API + '/api/sensors/' + id, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ behavior_mode: m }) });
    fetchS();
  };
  return React.createElement('div', null,
    React.createElement('div', {className: 'flex items-center justify-between mb-4'},
      React.createElement('div', {className: 'flex items-center gap-3'},
        React.createElement('h2', {className: 'text-lg font-semibold'}, 'Sensors'),
        React.createElement('select', {value: ft, onChange: (e: any) => setFt(e.target.value), className: 'bg-slate-800 border border-slate-700 rounded px-2 py-1 text-sm'},
          React.createElement('option', {value: ''}, 'All'),
          React.createElement('option', {value: 'temperature'}, 'Temperature'),
          React.createElement('option', {value: 'occupancy'}, 'Occupancy'),
          React.createElement('option', {value: 'energy'}, 'Energy')
        )
      ),
      React.createElement('button', {onClick: () => setShow(true), className: 'flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 px-4 py-2 rounded-lg text-sm font-medium'},
        React.createElement(Plus, {size: 16}), ' Add Sensor'
      )
    ),
    React.createElement('div', {className: 'grid gap-3'},
      sensors.map((s: S) =>
        React.createElement('div', {key: s.id, className: 'bg-slate-900 border rounded-xl p-4 ' + (s.on ? 'border-slate-700' : 'border-slate-800 opacity-60')},
          React.createElement('div', {className: 'flex items-center justify-between'},
            React.createElement('div', {className: 'flex items-center gap-3'},
              React.createElement('span', {className: TCOL[s.stype]}, ICO[s.stype]),
              React.createElement('div', null,
                React.createElement('div', {className: 'font-medium'}, s.name),
                React.createElement('div', {className: 'text-xs text-slate-500'}, s.bid + ' / ' + s.rid + ' | floor ' + s.floor)
              )
            ),
            React.createElement('div', {className: 'flex items-center gap-2'},
              React.createElement('select', {value: s.mode, onChange: (e: any) => sm(s.id, e.target.value), className: 'text-xs px-2 py-1 rounded ' + MCOL[s.mode]},
                React.createElement('option', {value: 'normal'}, 'Normal'),
                React.createElement('option', {value: 'random'}, 'Random'),
                React.createElement('option', {value: 'pattern'}, 'Pattern'),
                React.createElement('option', {value: 'anomaly'}, 'Anomaly')
              ),
              React.createElement('button', {onClick: () => tog(s.id), className: 'p-2 rounded-lg ' + (s.on ? 'bg-emerald-900 text-emerald-400' : 'bg-slate-800 text-slate-500')},
                React.createElement(Power, {size: 16})
              ),
              React.createElement('button', {onClick: () => del(s.id), className: 'p-2 hover:bg-red-900 rounded-lg text-slate-500 hover:text-red-400'},
                React.createElement(Trash2, {size: 16})
              )
            )
          )
        )
      ),
      sensors.length === 0 && React.createElement('div', {className: 'text-center text-slate-500 py-12'}, 'No sensors. Click Add Sensor.')
    ),
    show && React.createElement(AddForm, {onClose: () => { setShow(false); fetchS(); }})
  );
}

function AddForm({ onClose }: { onClose: () => void }) {
  const [f, setF] = useState({ name: '', bid: 'library', floor: 0, rid: 'L001', stype: 'temperature', mode: 'normal', cfg: { min_value: 20, max_value: 35, interval_ms: 5000, pattern: [], anomaly_prob: 0.05 } });
  const sub = async () => {
    await fetch(API + '/api/sensors', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: f.name, building_id: f.bid, floor: f.floor, room_id: f.rid, sensor_type: f.stype, behavior_mode: f.mode, config: f.cfg }) });
    onClose();
  };
  return React.createElement('div', {className: 'fixed inset-0 bg-black/60 flex items-center justify-center z-50', onClick: onClose},
    React.createElement('div', {className: 'bg-slate-900 border border-slate-700 rounded-xl p-6 w-full max-w-md', onClick: (e: any) => e.stopPropagation()},
      React.createElement('h3', {className: 'text-lg font-semibold mb-4'}, 'Add Sensor'),
      React.createElement('div', {className: 'space-y-3'},
        React.createElement('input', {placeholder: 'Name', value: f.name, onChange: (e: any) => setF({...f, name: e.target.value}), className: 'w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm'}),
        React.createElement('div', {className: 'grid grid-cols-2 gap-2'},
          React.createElement('input', {placeholder: 'Building ID', value: f.bid, onChange: (e: any) => setF({...f, bid: e.target.value}), className: 'bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm'}),
          React.createElement('input', {placeholder: 'Room ID', value: f.rid, onChange: (e: any) => setF({...f, rid: e.target.value}), className: 'bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm'})
        ),
        React.createElement('div', {className: 'grid grid-cols-2 gap-2'},
          React.createElement('input', {type: 'number', placeholder: 'Floor', value: f.floor, onChange: (e: any) => setF({...f, floor: +e.target.value}), className: 'bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm'}),
          React.createElement('select', {value: f.stype, onChange: (e: any) => setF({...f, stype: e.target.value}), className: 'bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm'},
            React.createElement('option', {value: 'temperature'}, 'Temperature'),
            React.createElement('option', {value: 'occupancy'}, 'Occupancy'),
            React.createElement('option', {value: 'energy'}, 'Energy')
          )
        ),
        React.createElement('div', {className: 'grid grid-cols-2 gap-2'},
          React.createElement('input', {type: 'number', placeholder: 'Min', value: f.cfg.min_value, onChange: (e: any) => setF({...f, cfg: {...f.cfg, min_value: +e.target.value}}), className: 'bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm'}),
          React.createElement('input', {type: 'number', placeholder: 'Max', value: f.cfg.max_value, onChange: (e: any) => setF({...f, cfg: {...f.cfg, max_value: +e.target.value}}), className: 'bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm'})
        ),
        React.createElement('select', {value: f.mode, onChange: (e: any) => setF({...f, mode: e.target.value}), className: 'w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm'},
          React.createElement('option', {value: 'normal'}, 'Normal'),
          React.createElement('option', {value: 'random'}, 'Random'),
          React.createElement('option', {value: 'pattern'}, 'Pattern'),
          React.createElement('option', {value: 'anomaly'}, 'Anomaly')
        )
      ),
      React.createElement('div', {className: 'flex gap-2 mt-4'},
        React.createElement('button', {onClick: sub, className: 'flex-1 bg-emerald-600 hover:bg-emerald-500 py-2 rounded-lg text-sm font-medium'}, 'Create'),
        React.createElement('button', {onClick: onClose, className: 'flex-1 bg-slate-800 hover:bg-slate-700 py-2 rounded-lg text-sm'}, 'Cancel')
      )
    )
  );
}
