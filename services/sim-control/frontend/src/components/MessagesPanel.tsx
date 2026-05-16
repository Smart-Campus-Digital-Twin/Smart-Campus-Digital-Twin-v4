'use client';
import React, { useEffect, useState, useCallback, useRef } from 'react';
import { ArrowUp, ArrowDown, AlertCircle, Pause, Play, Trash2, Filter } from 'lucide-react';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

type Direction = 'sent' | 'received' | 'dropped';

interface Msg {
  seq: number;
  direction: Direction;
  topic: string;
  payload: any;
  timestamp: string;
}

interface Stats { sent: number; received: number; dropped: number; buffered: number }

const DIR_COLOR: Record<Direction, string> = {
  sent: 'text-emerald-400',
  received: 'text-blue-400',
  dropped: 'text-red-400',
};
const DIR_BG: Record<Direction, string> = {
  sent: 'bg-emerald-900/30 border-emerald-800',
  received: 'bg-blue-900/30 border-blue-800',
  dropped: 'bg-red-900/30 border-red-800',
};

function fmt(ts: string): string {
  const d = new Date(ts);
  if (isNaN(d.getTime())) return ts;
  return d.toLocaleTimeString() + '.' + String(d.getMilliseconds()).padStart(3, '0');
}

export default function MessagesPanel() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [stats, setStats] = useState<Stats>({ sent: 0, received: 0, dropped: 0, buffered: 0 });
  const [paused, setPaused] = useState(false);
  const [filter, setFilter] = useState<'' | Direction>('');
  const [topicFilter, setTopicFilter] = useState('');
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const [err, setErr] = useState('');
  const timer = useRef<any>(null);

  const fetchM = useCallback(async () => {
    if (paused) return;
    try {
      const q = filter ? '?direction=' + filter + '&limit=200' : '?limit=200';
      const r = await fetch(API + '/api/mqtt/messages' + q);
      const d = await r.json();
      setMsgs(d.messages || []);
      setStats(d.stats || { sent: 0, received: 0, dropped: 0, buffered: 0 });
      setErr('');
    } catch {
      setErr('Backend offline.');
    }
  }, [paused, filter]);

  useEffect(() => {
    fetchM();
    timer.current = setInterval(fetchM, 1000);
    return () => clearInterval(timer.current);
  }, [fetchM]);

  const clearAll = async () => {
    await fetch(API + '/api/mqtt/messages', { method: 'DELETE' });
    fetchM();
  };

  const filtered = msgs.filter(m => !topicFilter || m.topic.toLowerCase().includes(topicFilter.toLowerCase()));

  return React.createElement('div', null,
    React.createElement('div', { className: 'flex flex-wrap items-center gap-3 mb-4' },
      React.createElement('h2', { className: 'text-lg font-semibold' }, 'MQTT Broker Messages'),
      React.createElement('div', { className: 'flex items-center gap-2 text-xs' },
        React.createElement('span', { className: 'px-2 py-0.5 rounded bg-emerald-900/40 text-emerald-300 border border-emerald-800' }, 'sent ' + stats.sent),
        React.createElement('span', { className: 'px-2 py-0.5 rounded bg-blue-900/40 text-blue-300 border border-blue-800' }, 'recv ' + stats.received),
        React.createElement('span', { className: 'px-2 py-0.5 rounded bg-red-900/40 text-red-300 border border-red-800' }, 'dropped ' + stats.dropped),
        React.createElement('span', { className: 'px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700' }, 'buf ' + stats.buffered)
      ),
      React.createElement('div', { className: 'flex-1' }),
      React.createElement('select', {
        value: filter, onChange: (e: any) => setFilter(e.target.value),
        className: 'bg-slate-800 border border-slate-700 rounded px-2 py-1 text-sm'
      },
        React.createElement('option', { value: '' }, 'All directions'),
        React.createElement('option', { value: 'sent' }, 'Sent'),
        React.createElement('option', { value: 'received' }, 'Received'),
        React.createElement('option', { value: 'dropped' }, 'Dropped')
      ),
      React.createElement('input', {
        placeholder: 'Topic filter...', value: topicFilter, onChange: (e: any) => setTopicFilter(e.target.value),
        className: 'bg-slate-800 border border-slate-700 rounded px-3 py-1 text-sm w-48'
      }),
      React.createElement('button', {
        onClick: () => setPaused(p => !p),
        className: 'flex items-center gap-1 px-3 py-1 rounded text-sm border ' + (paused ? 'bg-amber-900/40 border-amber-700 text-amber-300' : 'bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700')
      },
        paused ? React.createElement(Play, { size: 14 }) : React.createElement(Pause, { size: 14 }),
        paused ? 'Resume' : 'Pause'
      ),
      React.createElement('button', { onClick: clearAll, className: 'flex items-center gap-1 px-3 py-1 rounded text-sm bg-slate-800 hover:bg-red-900/40 border border-slate-700 hover:border-red-700 text-slate-300 hover:text-red-300' },
        React.createElement(Trash2, { size: 14 }), 'Clear'
      )
    ),
    err && React.createElement('div', { className: 'bg-red-950 border border-red-800 text-red-200 rounded-xl p-4 text-sm mb-3' }, err),
    React.createElement('div', { className: 'bg-slate-900 border border-slate-800 rounded-xl divide-y divide-slate-800 max-h-[70vh] overflow-y-auto' },
      filtered.map((m: Msg) => {
        const isOpen = !!expanded[m.seq];
        const icon = m.direction === 'sent' ? React.createElement(ArrowUp, { size: 12 }) :
          m.direction === 'received' ? React.createElement(ArrowDown, { size: 12 }) :
            React.createElement(AlertCircle, { size: 12 });
        return React.createElement('div', { key: m.seq, className: 'px-4 py-2 text-sm font-mono hover:bg-slate-800/50' },
          React.createElement('div', { className: 'flex items-center gap-3 cursor-pointer', onClick: () => setExpanded(e => ({ ...e, [m.seq]: !e[m.seq] })) },
            React.createElement('span', { className: 'inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] border ' + DIR_BG[m.direction] + ' ' + DIR_COLOR[m.direction] },
              icon, m.direction
            ),
            React.createElement('span', { className: 'text-slate-300 truncate flex-1' }, m.topic),
            React.createElement('span', { className: 'text-xs text-slate-500 tabular-nums shrink-0' }, fmt(m.timestamp))
          ),
          isOpen && React.createElement('pre', { className: 'mt-2 bg-slate-950 border border-slate-800 rounded p-2 text-[11px] text-slate-300 overflow-x-auto whitespace-pre-wrap break-all' },
            typeof m.payload === 'string' ? m.payload : JSON.stringify(m.payload, null, 2)
          )
        );
      }),
      filtered.length === 0 && React.createElement('div', { className: 'text-center text-slate-500 py-12 text-sm' }, paused ? 'Paused.' : 'No messages yet.')
    )
  );
}
