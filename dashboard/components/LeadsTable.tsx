"use client";

import { useState } from 'react';
import { Phone, CheckCircle, XCircle, Clock, PhoneOff, Loader2, MoreHorizontal, Trash2, PhoneCall, Download, Search, PhoneIncoming } from 'lucide-react';

interface Lead {
  id: string;
  businessName: string;
  phoneNumber: string;
  status: string;
  callDate: string | null;
  notes: string;
}

interface LeadsTableProps {
  leads: Lead[];
  onRefresh: () => void;
  onCallLead: (lead: Lead) => void;
}

const STATUS_CONFIG: Record<string, { label: string; icon: any; color: string; bg: string; pulse?: boolean }> = {
  pending: { label: 'Pending', icon: Clock, color: 'text-yellow-400', bg: 'bg-yellow-500/10 border-yellow-500/20' },
  calling: { label: 'Calling...', icon: PhoneCall, color: 'text-blue-400', bg: 'bg-blue-500/10 border-blue-500/20' },
  on_call: { label: 'On Call', icon: PhoneIncoming, color: 'text-emerald-300', bg: 'bg-emerald-500/20 border-emerald-400/40', pulse: true },
  demo_confirmed: { label: 'Demo Confirmed', icon: CheckCircle, color: 'text-green-400', bg: 'bg-green-500/10 border-green-500/20' },
  not_confirmed: { label: 'Not Confirmed', icon: XCircle, color: 'text-red-400', bg: 'bg-red-500/10 border-red-500/20' },
  no_answer: { label: 'No Answer', icon: PhoneOff, color: 'text-gray-400', bg: 'bg-gray-500/10 border-gray-500/20' },
  callback: { label: 'Callback', icon: Phone, color: 'text-purple-400', bg: 'bg-purple-500/10 border-purple-500/20' },
};

export default function LeadsTable({ leads, onRefresh, onCallLead }: LeadsTableProps) {
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState<string | null>(null);

  const filtered = leads.filter(lead => {
    const matchesSearch = lead.businessName.toLowerCase().includes(search.toLowerCase()) ||
      lead.phoneNumber.includes(search);
    const matchesFilter = filter === 'all' || lead.status === filter;
    return matchesSearch && matchesFilter;
  });

  const updateStatus = async (id: string, status: string) => {
    setLoadingId(id);
    setMenuOpen(null);
    try {
      await fetch(`/api/leads/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
      });
      onRefresh();
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingId(null);
    }
  };

  const deleteLead = async (id: string) => {
    setMenuOpen(null);
    try {
      await fetch(`/api/leads/${id}`, { method: 'DELETE' });
      onRefresh();
    } catch (err) {
      console.error(err);
    }
  };

  const downloadCSV = () => {
    window.open('/api/leads/download', '_blank');
  };

  return (
    <div className="space-y-4">
      {/* Search & Filter Bar */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
          <input
            type="text"
            placeholder="Search by name or number..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 bg-white/5 border border-white/10 rounded-xl text-sm text-white placeholder-gray-500 outline-none focus:ring-2 focus:ring-blue-500/50 transition-all"
          />
        </div>
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="px-4 py-2.5 bg-white/5 border border-white/10 rounded-xl text-sm text-white outline-none focus:ring-2 focus:ring-blue-500/50"
        >
          <option value="all">All Status</option>
          <option value="pending">Pending</option>
          <option value="calling">Calling</option>
          <option value="on_call">On Call</option>
          <option value="demo_confirmed">Demo Confirmed</option>
          <option value="not_confirmed">Not Confirmed</option>
          <option value="no_answer">No Answer</option>
          <option value="callback">Callback</option>
        </select>
        <button
          onClick={downloadCSV}
          className="flex items-center gap-2 px-4 py-2.5 bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-500 hover:to-emerald-500 text-white text-sm font-medium rounded-xl transition-all duration-300 hover:shadow-lg hover:shadow-green-500/20"
        >
          <Download className="w-4 h-4" />
          Download CSV
        </button>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-white/10 bg-white/[0.02]">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/10 bg-white/[0.03]">
              <th className="text-left p-4 text-gray-400 font-medium">#</th>
              <th className="text-left p-4 text-gray-400 font-medium">Business Name</th>
              <th className="text-left p-4 text-gray-400 font-medium">Phone Number</th>
              <th className="text-left p-4 text-gray-400 font-medium">Status</th>
              <th className="text-left p-4 text-gray-400 font-medium">Call Date</th>
              <th className="text-center p-4 text-gray-400 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={6} className="p-8 text-center text-gray-500">
                  {leads.length === 0 ? 'No leads yet. Upload a CSV to get started!' : 'No leads match your filter.'}
                </td>
              </tr>
            ) : (
              filtered.map((lead, idx) => {
                const statusCfg = STATUS_CONFIG[lead.status] || STATUS_CONFIG.pending;
                const StatusIcon = statusCfg.icon;
                return (
                  <tr key={lead.id} className="border-b border-white/5 hover:bg-white/[0.03] transition-colors">
                    <td className="p-4 text-gray-500 font-mono">{idx + 1}</td>
                    <td className="p-4 text-white font-medium">{lead.businessName}</td>
                    <td className="p-4 text-gray-300 font-mono">{lead.phoneNumber}</td>
                    <td className="p-4">
                      <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${statusCfg.bg} ${statusCfg.color} ${
                        statusCfg.pulse ? 'animate-pulse shadow-[0_0_8px_2px_rgba(52,211,153,0.4)]' : ''
                      }`}>
                        <StatusIcon className={`w-3 h-3 ${statusCfg.pulse ? 'animate-bounce' : ''}`} />
                        {statusCfg.label}
                        {statusCfg.pulse && <span className="relative flex h-2 w-2 ml-0.5"><span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span><span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span></span>}
                      </span>
                    </td>
                    <td className="p-4 text-gray-400 text-xs">
                      {lead.callDate ? new Date(lead.callDate).toLocaleString('en-IN') : '-'}
                    </td>
                    <td className="p-4">
                      <div className="flex items-center justify-center gap-2">
                        {/* Call Button */}
                        <button
                          onClick={() => onCallLead(lead)}
                          disabled={lead.status === 'calling'}
                          className="p-2 rounded-lg bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 transition-all disabled:opacity-30 disabled:cursor-not-allowed"
                          title="Call this lead"
                        >
                          {loadingId === lead.id ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                          ) : (
                            <Phone className="w-4 h-4" />
                          )}
                        </button>

                        {/* Status Menu */}
                        <div className="relative">
                          <button
                            onClick={() => setMenuOpen(menuOpen === lead.id ? null : lead.id)}
                            className="p-2 rounded-lg bg-white/5 text-gray-400 hover:bg-white/10 transition-all"
                          >
                            <MoreHorizontal className="w-4 h-4" />
                          </button>

                          {menuOpen === lead.id && (
                            <div className="absolute right-0 top-10 z-50 w-48 py-2 bg-gray-900 border border-white/10 rounded-xl shadow-2xl animate-in fade-in slide-in-from-top-2">
                              <p className="px-3 py-1 text-xs text-gray-500 font-medium">Update Status</p>
                              {Object.entries(STATUS_CONFIG).map(([key, cfg]) => (
                                <button
                                  key={key}
                                  onClick={() => updateStatus(lead.id, key)}
                                  className={`w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-white/5 transition-colors ${cfg.color}`}
                                >
                                  <cfg.icon className="w-3.5 h-3.5" />
                                  {cfg.label}
                                </button>
                              ))}
                              <hr className="my-1 border-white/10" />
                              <button
                                onClick={() => deleteLead(lead.id)}
                                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-400 hover:bg-red-500/10 transition-colors"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                                Delete Lead
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between text-xs text-gray-500">
        <span>Showing {filtered.length} of {leads.length} leads</span>
        <span>Click ⋯ to change status manually</span>
      </div>
    </div>
  );
}
