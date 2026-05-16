'use client';
import React, { useEffect, useState, useCallback } from 'react';
import { Clock, AlertTriangle, Activity, Filter } from 'lucide-react';
const API = 'http://localhost:8000';

interface L { id: string; ts: string; sid: string; sname: string; action: string; details: string; val: number | null; }

const ACT_COLORS: Record<string, string> = {
  created: 'text-green-400', deleted: 'text-red-400', toggled: 'text-yellow-400',
  updated: 'text-blue-400', rule_created: 'text-purple-400', rule_deleted: 'text-red-400', rule_updated: 'text-blue-400',
};

export default function LogsPanel() {
  const [logs, setLogs] = useState<L[]>([]);
  const [total, setTotal] = useState(0);
  const [filter, setFilter] = useState('');

  const fetchL = useCallback(async () => {
    const r = await fetch(API + '/api/logs?limit=200');
    const d = await r.json();
    setLogs(d.logs || []);
    setTotal(d.total || 0);
  }, []);

  useEffect(() => { fetchL(); const i = setInterval(fetchL, 5000); return () => clearInterval(i); }, [fetchL]);

  const filtered = filter ? logs.filter((l: L) => l.action.includes(filter) || l.sname.includes(filter) || l.details.includes(filter)) : logs;

  const fmtTime = (ts: string) => {
    const d = new Date(ts);
    return d.toLocaleTimeString();
  };

  return React.createElement('div', null,
    React.createElement('div', {className: 'flex items-center justify-between mb-4'},
      React.createElement('div', {className: 'flex items-center gap-3'},
        React.createElement('h2', {className: 'text-lg font-semibold'}, 'Activity Log'),
        React.createElement('span', {className: 'text-xs text-slate-500'}, total + ' entries')
      ),
      React.createElement('div', {className: 'flex items-center gap-2'},
        React.createElement(Filter, {size: 14, className: 'text-slate-500'}),
        React.createElement('input', {placeholder: 'Filter...', value: filter, onChange: (e: any) => setFilter(e.target.value),
          className: 'bg-slate-800 border border-slate-700 rounded px-3 py-1 text-sm w-48'})
      )
    ),
    React.createElement('div', {className: 'space-y-1'},
      filtered.map((l: L) =>
        React.createElement('div', {key: l.id, className: 'flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-slate-900 text-sm'},
          React.createElement('span', {className: ACT_COLORS[l.action] || 'text-slate-400'},
            l.action === 'created' || l.action === 'rule_created' ? React.createElement(Activity, {size: 14}) :
            l.action === 'deleted' || l.action === 'rule_deleted' ? React.createElement(AlertTriangle, {size: 14}) :
            React.createElement(Clock, {size: 14})
          ),
          React.createElement('div', {className: 'flex-1 min-w-0'},
            React.createElement('span', {className: 'text-slate-300'}, l.sname || l.action),
            l.details && React.createElement('span', {className: 'text-slate-500 ml-2'}, l.details)
          ),
          React.createElement('span', {className: 'text-xs text-slate-600 shrink-0'}, fmtTime(l.ts))
        )
      ),
      filtered.length === 0 && React.createElement('div', {className: 'text-center text-slate-500 py-12'}, 'No log entries.')
    )
  );
}
