'use client';
import React, { useEffect, useState, useCallback } from 'react';
import { Clock, AlertTriangle, Activity, Filter } from 'lucide-react';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface L {
  id: string;
  timestamp: string;
  sensor_id: string;
  sensor_name: string;
  action: string;
  details: string;
  value: number | null;
}

const ACT_COLORS: Record<string, string> = {
  created: 'text-emerald-400',
  deleted: 'text-red-400',
  toggled: 'text-amber-400',
  updated: 'text-blue-400',
  seeded: 'text-cyan-400',
  rule_created: 'text-purple-400',
  rule_deleted: 'text-red-400',
  rule_updated: 'text-blue-400',
};

function fmtTime(ts: string): string {
  if (!ts) return '—';
  const d = new Date(ts);
  if (isNaN(d.getTime())) return ts;
  return d.toLocaleTimeString() + ' · ' + d.toLocaleDateString();
}

export default function LogsPanel() {
  const [logs, setLogs] = useState<L[]>([]);
  const [total, setTotal] = useState(0);
  const [filter, setFilter] = useState('');
  const [err, setErr] = useState('');

  const fetchL = useCallback(async () => {
    try {
      const r = await fetch(API + '/api/logs?limit=200');
      const d = await r.json();
      setLogs(d.logs || []);
      setTotal(d.total || 0);
      setErr('');
    } catch {
      setErr('Backend offline.');
      setLogs([]);
      setTotal(0);
    }
  }, []);

  useEffect(() => { fetchL(); const i = setInterval(fetchL, 5000); return () => clearInterval(i); }, [fetchL]);

  const filtered = filter
    ? logs.filter(l => (l.action || '').includes(filter) || (l.sensor_name || '').toLowerCase().includes(filter.toLowerCase()) || (l.details || '').toLowerCase().includes(filter.toLowerCase()))
    : logs;

  return React.createElement('div', null,
    React.createElement('div', { className: 'flex items-center justify-between mb-4' },
      React.createElement('div', { className: 'flex items-center gap-3' },
        React.createElement('h2', { className: 'text-lg font-semibold' }, 'Activity Log'),
        React.createElement('span', { className: 'text-xs text-slate-500' }, total + ' entries')
      ),
      React.createElement('div', { className: 'flex items-center gap-2' },
        React.createElement(Filter, { size: 14, className: 'text-slate-500' }),
        React.createElement('input', {
          placeholder: 'Filter...', value: filter, onChange: (e: any) => setFilter(e.target.value),
          className: 'bg-slate-800 border border-slate-700 rounded px-3 py-1 text-sm w-48'
        })
      )
    ),
    err && React.createElement('div', { className: 'bg-red-950 border border-red-800 text-red-200 rounded-xl p-4 text-sm mb-3' }, err),
    React.createElement('div', { className: 'bg-slate-900 border border-slate-800 rounded-xl divide-y divide-slate-800' },
      filtered.map((l: L) =>
        React.createElement('div', { key: l.id, className: 'flex items-center gap-3 px-4 py-2 text-sm hover:bg-slate-800/50' },
          React.createElement('span', { className: ACT_COLORS[l.action] || 'text-slate-400' },
            l.action === 'created' || l.action === 'rule_created' ? React.createElement(Activity, { size: 14 }) :
              l.action === 'deleted' || l.action === 'rule_deleted' ? React.createElement(AlertTriangle, { size: 14 }) :
                React.createElement(Clock, { size: 14 })
          ),
          React.createElement('span', { className: 'font-medium text-slate-200 w-24 shrink-0' }, l.action),
          React.createElement('div', { className: 'flex-1 min-w-0 truncate' },
            l.sensor_name && React.createElement('span', { className: 'text-slate-300 mr-2' }, l.sensor_name),
            l.details && React.createElement('span', { className: 'text-slate-500' }, l.details)
          ),
          React.createElement('span', { className: 'text-xs text-slate-500 shrink-0 tabular-nums' }, fmtTime(l.timestamp))
        )
      ),
      filtered.length === 0 && React.createElement('div', { className: 'text-center text-slate-500 py-12' }, 'No log entries.')
    )
  );
}
