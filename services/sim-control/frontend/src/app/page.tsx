'use client';
import React, { useState } from 'react';
import { Activity, RefreshCw } from 'lucide-react';
import SensorPanel from '../components/SensorPanel';
import RulesPanel from '../components/RulesPanel';
import LogsPanel from '../components/LogsPanel';

export default function Home() {
  const [tab, setTab] = useState('sensors');
  const [rk, setRk] = useState(0);
  const refresh = () => setRk(k => k + 1);
  return React.createElement('div', {className: 'min-h-screen bg-slate-950 text-slate-200'},
    React.createElement('header', {className: 'border-b border-slate-800 bg-slate-900 px-6 py-4 flex items-center justify-between'},
      React.createElement('div', {className: 'flex items-center gap-3'},
        React.createElement(Activity, {size: 24, className: 'text-emerald-400'}),
        React.createElement('h1', {className: 'text-xl font-bold'}, 'Sim-Control')
      ),
      React.createElement('button', {onClick: refresh, className: 'p-2 hover:bg-slate-800 rounded-lg'},
        React.createElement(RefreshCw, {size: 16})
      )
    ),
    React.createElement('nav', {className: 'flex border-b border-slate-800 bg-slate-900 px-6'},
      ['sensors','rules','logs'].map((t: string) =>
        React.createElement('button', {key: t, onClick: () => setTab(t),
          className: 'px-4 py-3 text-sm font-medium border-b-2 capitalize transition-colors ' + (tab===t ? 'border-emerald-400 text-emerald-400' : 'border-transparent text-slate-400 hover:text-slate-200')
        }, t)
      )
    ),
    React.createElement('main', {className: 'p-6 max-w-7xl mx-auto'},
      tab==='sensors' && React.createElement(SensorPanel, {key: rk}),
      tab==='rules' && React.createElement(RulesPanel, {key: rk}),
      tab==='logs' && React.createElement(LogsPanel, {key: rk})
    )
  );
}
