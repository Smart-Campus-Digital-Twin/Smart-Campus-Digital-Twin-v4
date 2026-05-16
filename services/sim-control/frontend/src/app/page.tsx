'use client';
import React, { useEffect, useState, useRef, useCallback } from 'react';
import { Activity, RefreshCw, Wifi, ShieldCheck, KeyRound, Settings } from 'lucide-react';
import SensorPanel from '../components/SensorPanel';
import RulesPanel from '../components/RulesPanel';
import LogsPanel from '../components/LogsPanel';
import MessagesPanel from '../components/MessagesPanel';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

type Config = {
  mqtt: {
    connected: boolean;
    host: string;
    port: number;
    username: string;
    username_configured: boolean;
    password_configured: boolean;
    password_length: number;
    tls_enabled: boolean;
    tls_ca_cert: string;
    tls_client_cert: string;
    tls_client_key: string;
  };
  publish_interval_s: number;
  topics: Record<string, string>;
};

type BrokerForm = { host: string; port: string; username: string; password: string };

type Toast = { kind: 'info' | 'ok' | 'err'; text: string } | null;

const TABS = ['sensors', 'rules', 'messages', 'logs'] as const;
type Tab = typeof TABS[number];

export default function Home() {
  const [tab, setTab] = useState<Tab>('sensors');
  const [cfg, setCfg] = useState<Config | null>(null);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<BrokerForm>({ host: '', port: '', username: '', password: '' });
  const [toast, setToast] = useState<Toast>(null);
  const pollTimer = useRef<any>(null);

  const fetchCfg = useCallback(async () => {
    try {
      const c: Config = await fetch(API + '/api/config').then(r => r.json());
      setCfg(c);
      return c;
    } catch { setCfg(null); return null; }
  }, []);

  useEffect(() => {
    fetchCfg();
    const i = setInterval(fetchCfg, 3000);
    return () => clearInterval(i);
  }, [fetchCfg]);

  const showToast = (t: Toast, ms = 3000) => {
    setToast(t);
    if (t) setTimeout(() => setToast(null), ms);
  };

  const openEdit = () => {
    if (!cfg) return;
    setForm({ host: cfg.mqtt.host, port: String(cfg.mqtt.port), username: cfg.mqtt.username || '', password: '' });
    setEditing(true);
  };

  const submitBroker = async (e: React.FormEvent) => {
    e.preventDefault();
    const body: Record<string, unknown> = {
      host: form.host.trim(),
      port: Number(form.port),
      username: form.username,
    };
    if (form.password.length > 0) body.password = form.password;
    setEditing(false);
    showToast({ kind: 'info', text: `Reconnecting to ${body.host}:${body.port}...` }, 6000);
    try {
      const res = await fetch(API + '/api/mqtt/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error('HTTP ' + res.status);
    } catch (err) {
      showToast({ kind: 'err', text: 'Save failed: ' + (err as Error).message });
      return;
    }
    if (pollTimer.current) clearInterval(pollTimer.current);
    let tries = 0;
    pollTimer.current = setInterval(async () => {
      tries++;
      const c = await fetchCfg();
      if (c && c.mqtt.connected && c.mqtt.host === body.host) {
        clearInterval(pollTimer.current);
        showToast({ kind: 'ok', text: `Connected to ${c.mqtt.host}:${c.mqtt.port}` });
      } else if (tries >= 15) {
        clearInterval(pollTimer.current);
        showToast({ kind: 'err', text: 'Broker did not connect within 15s. Check creds/network.' }, 6000);
      }
    }, 1000);
  };

  return React.createElement('div', { className: 'min-h-screen bg-slate-950 text-slate-200' },
    React.createElement('header', { className: 'border-b border-slate-800 bg-slate-900/80 backdrop-blur px-6 py-3 flex items-center justify-between sticky top-0 z-30' },
      React.createElement('div', { className: 'flex items-center gap-3' },
        React.createElement(Activity, { size: 22, className: 'text-emerald-400' }),
        React.createElement('div', null,
          React.createElement('h1', { className: 'text-lg font-bold leading-tight' }, 'Sim-Control'),
          React.createElement('p', { className: 'text-[11px] text-slate-500' }, 'MQTT sensor publisher + rule console')
        )
      ),
      cfg && React.createElement('div', { className: 'flex items-center gap-4 text-xs' },
        React.createElement('span', { className: 'flex items-center gap-2' },
          React.createElement('span', { className: 'inline-block w-2 h-2 rounded-full ' + (cfg.mqtt.connected ? 'bg-emerald-400 animate-pulse' : 'bg-red-500') }),
          React.createElement('span', { className: 'text-slate-300 font-mono' }, cfg.mqtt.host + ':' + cfg.mqtt.port)
        ),
        React.createElement('span', { className: 'text-slate-500' }, 'every ' + cfg.publish_interval_s + 's'),
        React.createElement('button', { onClick: openEdit, className: 'flex items-center gap-1 px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300' },
          React.createElement(Settings, { size: 12 }), 'Broker'
        ),
        React.createElement('button', { onClick: fetchCfg, className: 'p-1.5 hover:bg-slate-800 rounded text-slate-400' },
          React.createElement(RefreshCw, { size: 14 })
        )
      )
    ),
    cfg && React.createElement('section', { className: 'grid gap-3 md:grid-cols-3 px-6 pt-4 max-w-7xl mx-auto' },
      React.createElement('div', { className: 'bg-slate-900 border border-slate-800 rounded-xl p-4' },
        React.createElement('div', { className: 'flex items-center justify-between' },
          React.createElement('div', { className: 'flex items-center gap-2 text-sm font-semibold' },
            React.createElement(Wifi, { size: 14, className: cfg.mqtt.connected ? 'text-emerald-400' : 'text-red-400' }),
            'MQTT Broker'
          ),
          React.createElement('button', { onClick: openEdit, className: 'p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-slate-200', title: 'Edit' },
            React.createElement(Settings, { size: 12 })
          )
        ),
        React.createElement('div', { className: 'mt-1 text-xl font-bold font-mono' }, cfg.mqtt.host + ':' + cfg.mqtt.port),
        React.createElement('div', { className: 'text-xs ' + (cfg.mqtt.connected ? 'text-emerald-400' : 'text-red-400') }, cfg.mqtt.connected ? 'connected' : 'disconnected')
      ),
      React.createElement('div', { className: 'bg-slate-900 border border-slate-800 rounded-xl p-4' },
        React.createElement('div', { className: 'flex items-center gap-2 text-sm font-semibold' }, React.createElement(KeyRound, { size: 14, className: 'text-amber-400' }), 'Auth'),
        React.createElement('div', { className: 'mt-1 text-sm text-slate-300' }, 'user: ' + (cfg.mqtt.username || '(none)')),
        React.createElement('div', { className: 'text-sm text-slate-300' }, 'pass: ' + (cfg.mqtt.password_configured ? cfg.mqtt.password_length + ' chars' : 'none'))
      ),
      React.createElement('div', { className: 'bg-slate-900 border border-slate-800 rounded-xl p-4' },
        React.createElement('div', { className: 'flex items-center gap-2 text-sm font-semibold' }, React.createElement(ShieldCheck, { size: 14, className: 'text-blue-400' }), 'TLS'),
        React.createElement('div', { className: 'mt-1 text-xs text-slate-400' }, cfg.mqtt.tls_enabled ? 'enabled' : 'disabled'),
        Object.entries(cfg.topics).map(([k, v]) => React.createElement('div', { key: k, className: 'text-[10px] text-slate-500 truncate font-mono' }, k + ': ' + v))
      )
    ),
    React.createElement('nav', { className: 'flex border-b border-slate-800 bg-slate-900 px-6 mt-6 sticky top-[57px] z-20' },
      TABS.map(t =>
        React.createElement('button', {
          key: t, onClick: () => setTab(t),
          className: 'px-4 py-3 text-sm font-medium border-b-2 capitalize transition-colors ' + (tab === t ? 'border-emerald-400 text-emerald-400' : 'border-transparent text-slate-400 hover:text-slate-200')
        }, t)
      )
    ),
    React.createElement('main', { className: 'p-6 max-w-7xl mx-auto' },
      tab === 'sensors' && React.createElement(SensorPanel, null),
      tab === 'rules' && React.createElement(RulesPanel, null),
      tab === 'messages' && React.createElement(MessagesPanel, null),
      tab === 'logs' && React.createElement(LogsPanel, null)
    ),
    editing && React.createElement('div', { className: 'fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4', onClick: () => setEditing(false) },
      React.createElement('form', {
        onSubmit: submitBroker,
        onClick: (e: React.MouseEvent) => e.stopPropagation(),
        className: 'bg-slate-900 border border-slate-700 rounded-xl p-6 w-full max-w-md space-y-4'
      },
        React.createElement('div', { className: 'flex items-center gap-2' },
          React.createElement(Settings, { size: 18, className: 'text-emerald-400' }),
          React.createElement('h2', { className: 'text-lg font-semibold' }, 'Edit MQTT Broker')
        ),
        React.createElement('label', { className: 'block text-sm' },
          React.createElement('span', { className: 'text-slate-400' }, 'Host'),
          React.createElement('input', {
            type: 'text', value: form.host,
            onChange: (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, host: e.target.value }),
            className: 'mt-1 w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono', required: true
          })
        ),
        React.createElement('label', { className: 'block text-sm' },
          React.createElement('span', { className: 'text-slate-400' }, 'Port'),
          React.createElement('input', {
            type: 'number', value: form.port,
            onChange: (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, port: e.target.value }),
            className: 'mt-1 w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono', required: true
          })
        ),
        React.createElement('label', { className: 'block text-sm' },
          React.createElement('span', { className: 'text-slate-400' }, 'Username'),
          React.createElement('input', {
            type: 'text', value: form.username,
            onChange: (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, username: e.target.value }),
            className: 'mt-1 w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono'
          })
        ),
        React.createElement('label', { className: 'block text-sm' },
          React.createElement('span', { className: 'text-slate-400' }, 'Password (leave blank to keep current)'),
          React.createElement('input', {
            type: 'password', value: form.password,
            onChange: (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, password: e.target.value }),
            className: 'mt-1 w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm', placeholder: '••••••'
          })
        ),
        React.createElement('div', { className: 'flex justify-end gap-2 pt-2' },
          React.createElement('button', {
            type: 'button', onClick: () => setEditing(false),
            className: 'px-4 py-2 text-sm rounded-lg border border-slate-700 hover:bg-slate-800'
          }, 'Cancel'),
          React.createElement('button', {
            type: 'submit',
            className: 'px-4 py-2 text-sm rounded-lg bg-emerald-500 text-slate-900 font-semibold hover:bg-emerald-400'
          }, 'Save & Reconnect')
        )
      )
    ),
    toast && React.createElement('div', {
      className: 'fixed bottom-6 right-6 z-50 px-4 py-3 rounded-lg shadow-lg border text-sm max-w-sm ' +
        (toast.kind === 'ok' ? 'bg-emerald-900/90 border-emerald-700 text-emerald-100' :
          toast.kind === 'err' ? 'bg-red-900/90 border-red-700 text-red-100' :
            'bg-slate-800/95 border-slate-700 text-slate-100')
    }, toast.text)
  );
}
