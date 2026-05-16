'use client';
import React, { useEffect, useState, useCallback } from 'react';
import { Plus, Trash2, Power } from 'lucide-react';
const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface R { id: string; name: string; on: boolean; cond: { sid: string; op: string; thr: number }; act: { type: string; tsid: string; val: number; en: boolean | null }; }

export default function RulesPanel() {
  const [rules, setRules] = useState<R[]>([]);
  const [show, setShow] = useState(false);
  const [err, setErr] = useState('');
  const fetchR = useCallback(async () => {
    try {
      const r = await fetch(API + '/api/rules');
      const d = await r.json();
      setRules(d.rules || []);
      setErr('');
    } catch {
      setErr('Backend offline. Start sim-control backend on port 8000.');
      setRules([]);
    }
  }, []);
  useEffect(() => { fetchR(); }, [fetchR]);
  const del = async (id: string) => { await fetch(API + '/api/rules/' + id, { method: 'DELETE' }); fetchR(); };
  return React.createElement('div', null,
    React.createElement('div', {className: 'flex items-center justify-between mb-4'},
      React.createElement('h2', {className: 'text-lg font-semibold'}, 'Rules'),
      React.createElement('button', {onClick: () => setShow(true), className: 'flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 px-4 py-2 rounded-lg text-sm font-medium'},
        React.createElement(Plus, {size: 16}), ' Add Rule'
      )
    ),
    React.createElement('div', {className: 'grid gap-3'},
      err && React.createElement('div', {className: 'bg-red-950 border border-red-800 text-red-200 rounded-xl p-4 text-sm'}, err),
      rules.map((r: R) =>
        React.createElement('div', {key: r.id, className: 'bg-slate-900 border border-slate-700 rounded-xl p-4'},
          React.createElement('div', {className: 'flex items-center justify-between'},
            React.createElement('div', null,
              React.createElement('div', {className: 'font-medium'}, r.name),
              React.createElement('div', {className: 'text-xs text-slate-500 mt-1'},
                'IF sensor ' + r.cond.sid + ' ' + r.cond.op + ' ' + r.cond.thr + ' THEN ' + r.act.type + '=' + r.act.val
              )
            ),
            React.createElement('div', {className: 'flex items-center gap-2'},
              React.createElement('span', {className: 'text-xs px-2 py-1 rounded ' + (r.on ? 'bg-green-900 text-green-300' : 'bg-slate-800 text-slate-500')}, r.on ? 'ON' : 'OFF'),
              React.createElement('button', {onClick: () => del(r.id), className: 'p-2 hover:bg-red-900 rounded-lg text-slate-500 hover:text-red-400'},
                React.createElement(Trash2, {size: 16})
              )
            )
          )
        )
      ),
      rules.length === 0 && React.createElement('div', {className: 'text-center text-slate-500 py-12'}, 'No rules. Click Add Rule.')
    ),
    show && React.createElement(AddRuleForm, {onClose: () => { setShow(false); fetchR(); }})
  );
}

function AddRuleForm({ onClose }: { onClose: () => void }) {
  const [f, setF] = useState({ name: '', cond_sid: '', cond_op: 'gt', cond_thr: 50, act_type: 'set_value', act_tsid: '', act_val: 0 });
  const sub = async () => {
    await fetch(API + '/api/rules', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: f.name, enabled: true, condition: { sensor_id: f.cond_sid, operator: f.cond_op, threshold: f.cond_thr }, action: { type: f.act_type, target_sensor_id: f.act_tsid, value: f.act_val } }) });
    onClose();
  };
  return React.createElement('div', {className: 'fixed inset-0 bg-black/60 flex items-center justify-center z-50', onClick: onClose},
    React.createElement('div', {className: 'bg-slate-900 border border-slate-700 rounded-xl p-6 w-full max-w-md', onClick: (e: any) => e.stopPropagation()},
      React.createElement('h3', {className: 'text-lg font-semibold mb-4'}, 'Add Rule'),
      React.createElement('div', {className: 'space-y-3'},
        React.createElement('input', {placeholder: 'Rule Name', value: f.name, onChange: (e: any) => setF({...f, name: e.target.value}), className: 'w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm'}),
        React.createElement('div', {className: 'text-xs text-slate-400'}, 'Condition'),
        React.createElement('div', {className: 'grid grid-cols-3 gap-2'},
          React.createElement('input', {placeholder: 'Sensor ID', value: f.cond_sid, onChange: (e: any) => setF({...f, cond_sid: e.target.value}), className: 'bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm'}),
          React.createElement('select', {value: f.cond_op, onChange: (e: any) => setF({...f, cond_op: e.target.value}), className: 'bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm'},
            React.createElement('option', {value: 'gt'}, 'greater than'), React.createElement('option', {value: 'lt'}, 'less than'),
            React.createElement('option', {value: 'gte'}, 'gte'), React.createElement('option', {value: 'lte'}, 'lte'), React.createElement('option', {value: 'eq'}, 'equals')
          ),
          React.createElement('input', {type: 'number', placeholder: 'Threshold', value: f.cond_thr, onChange: (e: any) => setF({...f, cond_thr: +e.target.value}), className: 'bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm'})
        ),
        React.createElement('div', {className: 'text-xs text-slate-400'}, 'Action'),
        React.createElement('div', {className: 'grid grid-cols-2 gap-2'},
          React.createElement('select', {value: f.act_type, onChange: (e: any) => setF({...f, act_type: e.target.value}), className: 'bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm'},
            React.createElement('option', {value: 'set_value'}, 'Set Value'), React.createElement('option', {value: 'toggle'}, 'Toggle Sensor')
          ),
          React.createElement('input', {type: 'number', placeholder: 'Value', value: f.act_val, onChange: (e: any) => setF({...f, act_val: +e.target.value}), className: 'bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm'})
        ),
        React.createElement('input', {placeholder: 'Target Sensor ID (for toggle)', value: f.act_tsid, onChange: (e: any) => setF({...f, act_tsid: e.target.value}), className: 'w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm'})
      ),
      React.createElement('div', {className: 'flex gap-2 mt-4'},
        React.createElement('button', {onClick: sub, className: 'flex-1 bg-emerald-600 hover:bg-emerald-500 py-2 rounded-lg text-sm font-medium'}, 'Create'),
        React.createElement('button', {onClick: onClose, className: 'flex-1 bg-slate-800 hover:bg-slate-700 py-2 rounded-lg text-sm'}, 'Cancel')
      )
    )
  );
}
