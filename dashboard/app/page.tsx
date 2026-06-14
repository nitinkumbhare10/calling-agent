"use client";

import { useState, useEffect, useCallback } from 'react';
import { LayoutDashboard, Users, Phone, Settings, Upload, Sparkles, RefreshCw, Trash2, X, Clock } from 'lucide-react';
import StatsCards from '@/components/StatsCards';
import CSVUploader from '@/components/CSVUploader';
import LeadsTable from '@/components/LeadsTable';
import CallHistory from '@/components/CallHistory';
import CallDispatcher from '@/components/CallDispatcher';
import QuotaBar from '@/components/QuotaBar';

type Tab = 'overview' | 'leads' | 'calls' | 'quick-call';

interface Lead {
  id: string;
  businessName: string;
  phoneNumber: string;
  status: string;
  callDate: string | null;
  notes: string;
}

interface Stats {
  totalLeads: number;
  pending: number;
  calling: number;
  onCall: number;
  demoConfirmed: number;
  notConfirmed: number;
  noAnswer: number;
  callback: number;
  totalCalls: number;
}

const TABS = [
  { id: 'overview' as Tab, label: 'Overview', icon: LayoutDashboard },
  { id: 'leads' as Tab, label: 'Leads', icon: Users },
  { id: 'calls' as Tab, label: 'Call History', icon: Phone },
  { id: 'quick-call' as Tab, label: 'Quick Call', icon: Sparkles },
];

const DEFAULT_STATS: Stats = {
  totalLeads: 0, pending: 0, calling: 0, onCall: 0, demoConfirmed: 0,
  notConfirmed: 0, noAnswer: 0, callback: 0, totalCalls: 0,
};

export default function Home() {
  const [activeTab, setActiveTab] = useState<Tab>('overview');
  const [leads, setLeads] = useState<Lead[]>([]);
  const [stats, setStats] = useState<Stats>(DEFAULT_STATS);
  const [loading, setLoading] = useState(true);
  const [autoCallNextLead, setAutoCallNextLead] = useState(false);
  const [autoDialEndTime, setAutoDialEndTime] = useState<number | null>(null);
  const [showDurationModal, setShowDurationModal] = useState(false);
  const [customDuration, setCustomDuration] = useState("");

  const fetchLeads = useCallback(async () => {
    try {
      const res = await fetch('/api/leads');
      const data = await res.json();
      setLeads(data.leads || []);
      setStats(data.stats || DEFAULT_STATS);
    } catch (err) {
      console.error('Failed to fetch leads:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchSettings = useCallback(async () => {
    try {
      const res = await fetch('/api/settings');
      const data = await res.json();
      setAutoCallNextLead(data.autoCallNextLead || false);
      setAutoDialEndTime(data.autoDialEndTime || null);
    } catch (err) {
      console.error('Failed to fetch settings:', err);
    }
  }, []);

  const handleToggleAutoCall = async () => {
    if (!autoCallNextLead) {
      setShowDurationModal(true);
      return;
    }
    
    try {
      const targetState = false;
      setAutoCallNextLead(targetState);
      const res = await fetch('/api/settings', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ autoCallNextLead: targetState, autoDialEndTime: null }),
      });
      const data = await res.json();
      setAutoCallNextLead(data.autoCallNextLead || false);
      setAutoDialEndTime(null);
      fetchLeads();
    } catch (err) {
      console.error('Failed to update settings:', err);
    }
  };

  const handleStartAutoDial = async (durationMinutes: number | null) => {
    try {
      setShowDurationModal(false);
      const endTime = durationMinutes ? Date.now() + durationMinutes * 60000 : null;
      setAutoCallNextLead(true);
      setAutoDialEndTime(endTime);
      
      const res = await fetch('/api/settings', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ autoCallNextLead: true, autoDialEndTime: endTime }),
      });
      const data = await res.json();
      setAutoCallNextLead(data.autoCallNextLead || false);
      setAutoDialEndTime(data.autoDialEndTime || null);
      fetchLeads();
    } catch (err) {
      console.error('Failed to start auto-dialing:', err);
    }
  };

  const getAutoDialButtonText = () => {
    if (!autoCallNextLead) return 'OFF';
    if (!autoDialEndTime) return 'ON';
    const remainingMs = autoDialEndTime - Date.now();
    if (remainingMs <= 0) return 'OFF';
    const mins = Math.ceil(remainingMs / 60000);
    if (mins > 60) {
      const hrs = Math.floor(mins / 60);
      const m = mins % 60;
      return `ON (${hrs}h ${m}m)`;
    }
    return `ON (${mins}m)`;
  };

  useEffect(() => {
    fetchLeads();
    fetchSettings();
    // Auto-poll every 10 seconds to catch status updates from agent callbacks
    const interval = setInterval(async () => {
      // Also trigger sync-status to fix stale "calling" leads
      try { await fetch('/api/leads/sync-status', { method: 'POST' }); } catch {}
      fetchLeads();
      fetchSettings();
    }, 10000);
    return () => clearInterval(interval);
  }, [fetchLeads, fetchSettings]);

  const handleCallLead = async (lead: Lead) => {
    try {
      // Update status to calling
      await fetch(`/api/leads/${lead.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'calling', callDate: new Date().toISOString() }),
      });

      // Dispatch the call with leadId so agent can callback
      const dispatchRes = await fetch('/api/dispatch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          phoneNumber: lead.phoneNumber,
          leadId: lead.id,
          prompt: `You are calling ${lead.businessName}. Use their business name in the conversation.`,
        }),
      });
      const dispatchData = await dispatchRes.json();

      // Log the call
      await fetch('/api/calls', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          leadId: lead.id,
          phoneNumber: lead.phoneNumber,
          businessName: lead.businessName,
          status: 'in_progress',
          duration: 0,
          transcript: '',
        }),
      });

      fetchLeads();
    } catch (err) {
      console.error('Failed to call lead:', err);
    }
  };

  return (
    <main className="min-h-screen bg-[#050505] text-white">
      {/* Ambient Background */}
      <div className="fixed top-0 left-0 w-full h-full overflow-hidden pointer-events-none">
        <div className="absolute top-[-20vh] left-[10vw] w-[60vh] h-[60vh] bg-blue-600/15 rounded-full blur-[160px]"></div>
        <div className="absolute bottom-[-10vh] right-[15vw] w-[50vh] h-[50vh] bg-purple-600/10 rounded-full blur-[140px]"></div>
        <div className="absolute top-[40vh] right-[5vw] w-[30vh] h-[30vh] bg-emerald-600/8 rounded-full blur-[120px]"></div>
      </div>

      {/* Header */}
      <header className="relative z-10 border-b border-white/5 bg-black/40 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold">
                <span className="text-white">LeadVelocity</span>
                <span className="bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-purple-400"> AI</span>
              </h1>
              <p className="text-xs text-gray-500">Sales Agent Dashboard</p>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/5 border border-white/10 text-xs">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
              </span>
              <span className="text-green-400">Agent Online</span>
            </div>

            {/* Auto Calling Toggle */}
            <button
              onClick={handleToggleAutoCall}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs font-medium transition-all duration-300 ${
                autoCallNextLead
                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/25 shadow-[0_0_15px_rgba(16,185,129,0.15)]'
                  : 'bg-white/5 text-gray-400 border-white/10 hover:bg-white/10 hover:text-white'
              }`}
              title="Toggle automatic next-lead calling"
            >
              <span className="relative flex h-2 w-2">
                {autoCallNextLead && (
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                )}
                <span className={`relative inline-flex rounded-full h-2 w-2 ${autoCallNextLead ? 'bg-emerald-500' : 'bg-gray-500'}`}></span>
              </span>
              <span>Auto Dialing: {getAutoDialButtonText()}</span>
            </button>

            <button
              onClick={() => fetchLeads()}
              className="p-2 rounded-lg bg-white/5 hover:bg-white/10 transition-all text-gray-400 hover:text-white"
              title="Refresh data"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="max-w-7xl mx-auto px-6">
          <nav className="flex gap-1">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-4 py-3 text-sm font-medium rounded-t-lg transition-all duration-200 ${
                  activeTab === tab.id
                    ? 'bg-white/10 text-white border-b-2 border-blue-500'
                    : 'text-gray-500 hover:text-gray-300 hover:bg-white/5'
                }`}
              >
                <tab.icon className="w-4 h-4" />
                {tab.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      {/* Quota Health Bar */}
      <QuotaBar />

      {/* Content */}
      <div className="relative z-10 max-w-7xl mx-auto px-6 py-8">
        {/* OVERVIEW TAB */}
        {activeTab === 'overview' && (
          <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <StatsCards stats={stats} />

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* CSV Upload Section */}
              <div className="lg:col-span-1">
                <div className="p-6 rounded-2xl bg-white/[0.03] border border-white/10 backdrop-blur-sm">
                  <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                    <Upload className="w-5 h-5 text-blue-400" />
                    Quick Import
                  </h3>
                  <CSVUploader onUploadSuccess={fetchLeads} />
                </div>
              </div>

              {/* Recent Leads */}
              <div className="lg:col-span-2">
                <div className="p-6 rounded-2xl bg-white/[0.03] border border-white/10 backdrop-blur-sm">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                      <Users className="w-5 h-5 text-purple-400" />
                      Recent Leads
                    </h3>
                    <button
                      onClick={() => setActiveTab('leads')}
                      className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
                    >
                      View All →
                    </button>
                  </div>
                  {loading ? (
                    <div className="flex justify-center py-8">
                      <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                    </div>
                  ) : (
                    <LeadsTable
                      leads={leads.slice(0, 5)}
                      onRefresh={fetchLeads}
                      onCallLead={handleCallLead}
                    />
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* LEADS TAB */}
        {activeTab === 'leads' && (
          <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-2xl font-bold text-white">Lead Management</h2>
                <p className="text-sm text-gray-500 mt-1">Upload CSV, manage leads, and track call status</p>
              </div>
              {leads.length > 0 && (
                <ClearAllButton onClear={async () => {
                  await fetch('/api/leads', { method: 'DELETE' });
                  fetchLeads();
                }} />
              )}
            </div>

            {/* CSV Upload */}
            <div className="p-6 rounded-2xl bg-white/[0.03] border border-white/10 backdrop-blur-sm">
              <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <Upload className="w-5 h-5 text-blue-400" />
                Import Leads from CSV
              </h3>
              <CSVUploader onUploadSuccess={fetchLeads} />
            </div>

            {/* Stats */}
            <StatsCards stats={stats} />

            {/* Leads Table */}
            <div className="p-6 rounded-2xl bg-white/[0.03] border border-white/10 backdrop-blur-sm">
              <LeadsTable
                leads={leads}
                onRefresh={fetchLeads}
                onCallLead={handleCallLead}
              />
            </div>
          </div>
        )}

        {/* CALLS TAB */}
        {activeTab === 'calls' && (
          <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div>
              <h2 className="text-2xl font-bold text-white">Call History</h2>
              <p className="text-sm text-gray-500 mt-1">View all call logs and transcripts</p>
            </div>

            <div className="p-6 rounded-2xl bg-white/[0.03] border border-white/10 backdrop-blur-sm">
              <CallHistory />
            </div>
          </div>
        )}

        {/* QUICK CALL TAB */}
        {activeTab === 'quick-call' && (
          <div className="flex flex-col items-center gap-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="text-center">
              <h2 className="text-2xl font-bold text-white">Quick Call</h2>
              <p className="text-sm text-gray-500 mt-1">Deploy agent to a single number instantly</p>
            </div>
            <CallDispatcher />
          </div>
        )}
      </div>

      {/* Footer */}
      <footer className="relative z-10 border-t border-white/5 py-6 mt-12">
        <div className="max-w-7xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-center gap-4 text-center">
          <p className="text-sm text-gray-600">
            Powered by <span className="text-white font-semibold">LeadVelocity AI</span>
          </p>
        </div>
      </footer>
      {/* Duration Modal */}
      {showDurationModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-[#121212] border border-white/10 rounded-2xl p-6 w-full max-w-sm shadow-2xl">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                <Clock className="w-5 h-5 text-blue-400" />
                Auto-Dial Duration
              </h3>
              <button 
                onClick={() => setShowDurationModal(false)}
                className="text-gray-400 hover:text-white transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <p className="text-sm text-gray-400 mb-4">
              How long should the agent keep dialing leads?
            </p>
            
            <div className="grid grid-cols-2 gap-3">
              {[
                { label: '15 Mins', value: 15 },
                { label: '30 Mins', value: 30 },
                { label: '1 Hour', value: 60 },
                { label: '2 Hours', value: 120 },
                { label: '4 Hours', value: 240 },
                { label: 'Unlimited', value: null },
              ].map((option, idx) => (
                <button
                  key={idx}
                  onClick={() => handleStartAutoDial(option.value)}
                  className="px-4 py-3 rounded-xl border border-white/5 bg-white/5 hover:bg-blue-500/20 hover:border-blue-500/40 hover:text-blue-400 text-sm font-medium transition-all duration-200"
                >
                  {option.label}
                </button>
              ))}
            </div>

            <div className="mt-4 flex gap-2">
              <input
                type="number"
                min="1"
                placeholder="Custom (minutes)..."
                value={customDuration}
                onChange={(e) => setCustomDuration(e.target.value)}
                className="flex-1 px-4 py-2 rounded-xl bg-white/5 border border-white/10 text-white text-sm placeholder:text-gray-500 focus:outline-none focus:border-blue-500/50 transition-colors"
              />
              <button
                onClick={() => {
                  const val = parseInt(customDuration, 10);
                  if (!isNaN(val) && val > 0) {
                    handleStartAutoDial(val);
                  }
                }}
                disabled={!customDuration || isNaN(parseInt(customDuration, 10)) || parseInt(customDuration, 10) <= 0}
                className="px-4 py-2 rounded-xl bg-blue-500 text-white text-sm font-medium hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                Set
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

// Two-step confirmation delete button
function ClearAllButton({ onClear }: { onClear: () => Promise<void> }) {
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const handleClick = async () => {
    if (!confirming) {
      setConfirming(true);
      // Auto-reset after 3 seconds
      setTimeout(() => setConfirming(false), 3000);
      return;
    }
    setDeleting(true);
    await onClear();
    setDeleting(false);
    setConfirming(false);
  };

  return (
    <button
      onClick={handleClick}
      disabled={deleting}
      className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium rounded-xl border transition-all duration-300 ${
        confirming
          ? 'bg-red-600 hover:bg-red-500 text-white border-red-500 animate-pulse'
          : 'bg-red-500/10 hover:bg-red-500/20 text-red-400 hover:text-red-300 border-red-500/20'
      }`}
    >
      <Trash2 className="w-4 h-4" />
      {deleting ? 'Deleting...' : confirming ? '⚠ Confirm Delete?' : 'Clear All Leads'}
    </button>
  );
}
