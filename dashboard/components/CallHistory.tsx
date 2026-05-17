"use client";

import { useState, useEffect } from 'react';
import { Phone, Clock, MessageSquare, ChevronDown, ChevronUp } from 'lucide-react';

interface CallLog {
  id: string;
  leadId: string | null;
  phoneNumber: string;
  businessName: string;
  status: string;
  duration: number;
  timestamp: string;
  transcript: string;
}

export default function CallHistory() {
  const [calls, setCalls] = useState<CallLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const fetchCalls = async () => {
    try {
      const res = await fetch('/api/calls');
      const data = await res.json();
      setCalls(data.calls || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCalls();
    const interval = setInterval(fetchCalls, 10000); // Refresh every 10s
    return () => clearInterval(interval);
  }, []);

  const formatDuration = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  const STATUS_COLORS: Record<string, string> = {
    completed: 'text-green-400 bg-green-500/10 border-green-500/20',
    no_answer: 'text-gray-400 bg-gray-500/10 border-gray-500/20',
    failed: 'text-red-400 bg-red-500/10 border-red-500/20',
    in_progress: 'text-blue-400 bg-blue-500/10 border-blue-500/20',
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {calls.length === 0 ? (
        <div className="text-center py-16">
          <Phone className="w-12 h-12 text-gray-600 mx-auto mb-4" />
          <p className="text-gray-500">No call history yet</p>
          <p className="text-xs text-gray-600 mt-1">Calls will appear here as they are made</p>
        </div>
      ) : (
        calls.map((call) => (
          <div key={call.id} className="border border-white/10 rounded-xl bg-white/[0.02] overflow-hidden transition-all hover:border-white/15">
            {/* Call Header */}
            <div
              className="flex items-center justify-between p-4 cursor-pointer"
              onClick={() => setExpandedId(expandedId === call.id ? null : call.id)}
            >
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500/20 to-purple-500/20 flex items-center justify-center">
                  <Phone className="w-5 h-5 text-blue-400" />
                </div>
                <div>
                  <p className="text-white font-medium">{call.businessName}</p>
                  <p className="text-xs text-gray-500 font-mono">{call.phoneNumber}</p>
                </div>
              </div>

              <div className="flex items-center gap-4">
                <span className={`px-2.5 py-1 rounded-full text-xs font-medium border ${STATUS_COLORS[call.status] || STATUS_COLORS.completed}`}>
                  {call.status.replace('_', ' ')}
                </span>
                <div className="text-right hidden sm:block">
                  <p className="text-xs text-gray-400 flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {call.duration > 0 ? formatDuration(call.duration) : '-'}
                  </p>
                  <p className="text-xs text-gray-600">
                    {new Date(call.timestamp).toLocaleString('en-IN')}
                  </p>
                </div>
                {call.transcript ? (
                  expandedId === call.id ? (
                    <ChevronUp className="w-4 h-4 text-gray-500" />
                  ) : (
                    <ChevronDown className="w-4 h-4 text-gray-500" />
                  )
                ) : null}
              </div>
            </div>

            {/* Transcript (Expandable) */}
            {expandedId === call.id && call.transcript && (
              <div className="px-4 pb-4 border-t border-white/5 animate-in fade-in slide-in-from-top-1">
                <div className="mt-3 p-4 rounded-lg bg-black/40 border border-white/5">
                  <div className="flex items-center gap-2 mb-3">
                    <MessageSquare className="w-4 h-4 text-purple-400" />
                    <p className="text-xs text-purple-400 font-medium">Call Transcript</p>
                  </div>
                  <div className="space-y-2 text-sm max-h-64 overflow-y-auto custom-scrollbar">
                    {call.transcript.split('\n').map((line, i) => (
                      <p key={i} className={line.startsWith('USER:') ? 'text-blue-300' : line.startsWith('AGENT:') ? 'text-green-300' : 'text-gray-400'}>
                        {line}
                      </p>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        ))
      )}
    </div>
  );
}
