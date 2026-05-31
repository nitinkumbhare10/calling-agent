"use client";

import { useState, useEffect, useCallback } from 'react';
import { Activity, RefreshCw, ChevronDown, ChevronUp, AlertTriangle, CheckCircle2, XCircle, Loader2 } from 'lucide-react';

interface ServiceStatus {
  name: string;
  status: 'ok' | 'error' | 'quota_exceeded' | 'checking';
  message: string;
  checkedAt: string;
}

interface QuotaResponse {
  services: ServiceStatus[];
  overall: 'healthy' | 'warning';
  checkedAt: string;
}

const SERVICE_ICONS: Record<string, string> = {
  'Cartesia TTS': '🔊',
  'Deepgram STT': '🎤',
  'Groq LLM': '🧠',
  'Sarvam TTS': '🗣️',
  'LiveKit Infra': '📡',
  'Vobiz SIP': '📞',
};

function StatusDot({ status }: { status: string }) {
  if (status === 'ok') {
    return (
      <span className="relative flex h-2 w-2">
        <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
      </span>
    );
  }
  if (status === 'quota_exceeded') {
    return (
      <span className="relative flex h-2 w-2">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
        <span className="relative inline-flex rounded-full h-2 w-2 bg-red-500"></span>
      </span>
    );
  }
  if (status === 'error') {
    return (
      <span className="relative flex h-2 w-2">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
        <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500"></span>
      </span>
    );
  }
  // checking
  return (
    <span className="relative flex h-2 w-2">
      <span className="animate-pulse relative inline-flex rounded-full h-2 w-2 bg-gray-400"></span>
    </span>
  );
}

function StatusIcon({ status }: { status: string }) {
  if (status === 'ok') return <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />;
  if (status === 'quota_exceeded') return <XCircle className="w-3.5 h-3.5 text-red-400" />;
  if (status === 'error') return <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />;
  return <Loader2 className="w-3.5 h-3.5 text-gray-400 animate-spin" />;
}

function getStatusColor(status: string) {
  switch (status) {
    case 'ok': return 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20';
    case 'quota_exceeded': return 'text-red-400 bg-red-500/10 border-red-500/20';
    case 'error': return 'text-amber-400 bg-amber-500/10 border-amber-500/20';
    default: return 'text-gray-400 bg-white/5 border-white/10';
  }
}

function getStatusLabel(status: string) {
  switch (status) {
    case 'ok': return 'OK';
    case 'quota_exceeded': return 'Quota Exceeded';
    case 'error': return 'Error';
    default: return 'Checking...';
  }
}

export default function QuotaBar() {
  const [quota, setQuota] = useState<QuotaResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const fetchQuota = useCallback(async (showRefresh = false) => {
    if (showRefresh) setRefreshing(true);
    try {
      const res = await fetch('/api/quota');
      const data: QuotaResponse = await res.json();
      setQuota(data);
      // Auto-expand if there's an issue
      if (data.overall === 'warning') setExpanded(true);
    } catch (err) {
      console.error('Failed to fetch quota:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchQuota();
    // Poll every 60 seconds
    const interval = setInterval(() => fetchQuota(), 60000);
    return () => clearInterval(interval);
  }, [fetchQuota]);

  const okCount = quota?.services.filter(s => s.status === 'ok').length ?? 0;
  const totalCount = quota?.services.length ?? 0;
  const hasIssue = quota?.overall === 'warning';

  return (
    <div className="relative z-10 max-w-7xl mx-auto px-6 pt-4">
      <div className={`rounded-2xl border backdrop-blur-sm transition-all duration-500 ${
        hasIssue
          ? 'bg-red-500/[0.03] border-red-500/20'
          : 'bg-white/[0.02] border-white/10'
      }`}>
        {/* Compact Bar */}
        <div
          className="flex items-center justify-between px-4 py-3 cursor-pointer select-none"
          onClick={() => setExpanded(!expanded)}
        >
          <div className="flex items-center gap-3">
            <div className={`p-1.5 rounded-lg ${hasIssue ? 'bg-red-500/10' : 'bg-emerald-500/10'}`}>
              <Activity className={`w-4 h-4 ${hasIssue ? 'text-red-400' : 'text-emerald-400'}`} />
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-gray-300 uppercase tracking-wider">API Health</span>
              {loading ? (
                <span className="text-xs text-gray-500 flex items-center gap-1">
                  <Loader2 className="w-3 h-3 animate-spin" /> Checking...
                </span>
              ) : (
                <span className={`text-xs font-medium ${hasIssue ? 'text-red-400' : 'text-emerald-400'}`}>
                  {okCount}/{totalCount} Services OK
                </span>
              )}
            </div>

            {/* Mini status pills */}
            {!loading && quota && (
              <div className="hidden sm:flex items-center gap-1.5 ml-2">
                {quota.services.map((service) => (
                  <div
                    key={service.name}
                    className={`flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-medium transition-all ${getStatusColor(service.status)}`}
                    title={`${service.name}: ${service.message}`}
                  >
                    <StatusDot status={service.status} />
                    <span>{SERVICE_ICONS[service.name] || '⚙️'}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="flex items-center gap-2">
            {quota?.checkedAt && (
              <span className="text-[10px] text-gray-600 hidden md:inline">
                Last check: {new Date(quota.checkedAt).toLocaleTimeString('en-IN')}
              </span>
            )}
            <button
              onClick={(e) => { e.stopPropagation(); fetchQuota(true); }}
              disabled={refreshing}
              className="p-1.5 rounded-lg bg-white/5 hover:bg-white/10 transition-all text-gray-400 hover:text-white disabled:opacity-50"
              title="Refresh quota status"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            </button>
            {expanded ? (
              <ChevronUp className="w-4 h-4 text-gray-500" />
            ) : (
              <ChevronDown className="w-4 h-4 text-gray-500" />
            )}
          </div>
        </div>

        {/* Expanded Details */}
        {expanded && quota && (
          <div className="border-t border-white/5 px-4 py-3 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 animate-in fade-in slide-in-from-top-2 duration-300">
            {quota.services.map((service) => (
              <div
                key={service.name}
                className={`flex items-start gap-3 p-3 rounded-xl border transition-all ${getStatusColor(service.status)}`}
              >
                <div className="mt-0.5">
                  <StatusIcon status={service.status} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="text-sm">{SERVICE_ICONS[service.name] || '⚙️'}</span>
                    <span className="text-xs font-semibold truncate">{service.name}</span>
                  </div>
                  <p className={`text-[11px] mt-0.5 ${
                    service.status === 'ok' ? 'text-emerald-400/70' :
                    service.status === 'quota_exceeded' ? 'text-red-400/70' :
                    'text-amber-400/70'
                  }`}>
                    {getStatusLabel(service.status)}
                  </p>
                  {service.status !== 'ok' && (
                    <p className="text-[10px] text-gray-500 mt-1 break-words">{service.message}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
