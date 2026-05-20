"use client";

import { Users, Phone, CheckCircle, XCircle, Clock, PhoneOff, PhoneIncoming } from 'lucide-react';

interface StatsData {
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

export default function StatsCards({ stats }: { stats: StatsData }) {
  const cards = [
    { label: 'Total Leads', value: stats.totalLeads, icon: Users, color: 'from-blue-500 to-blue-600', bg: 'bg-blue-500/10', border: 'border-blue-500/20', pulse: false },
    { label: 'Pending', value: stats.pending, icon: Clock, color: 'from-yellow-500 to-orange-500', bg: 'bg-yellow-500/10', border: 'border-yellow-500/20', pulse: false },
    { label: 'On Call 🔴', value: stats.onCall, icon: PhoneIncoming, color: 'from-emerald-400 to-green-500', bg: 'bg-emerald-500/15', border: 'border-emerald-400/40', pulse: true },
    { label: 'Demo Confirmed', value: stats.demoConfirmed, icon: CheckCircle, color: 'from-green-500 to-emerald-500', bg: 'bg-green-500/10', border: 'border-green-500/20', pulse: false },
    { label: 'Not Confirmed', value: stats.notConfirmed, icon: XCircle, color: 'from-red-500 to-rose-500', bg: 'bg-red-500/10', border: 'border-red-500/20', pulse: false },
    { label: 'Total Calls', value: stats.totalCalls, icon: Phone, color: 'from-purple-500 to-violet-500', bg: 'bg-purple-500/10', border: 'border-purple-500/20', pulse: false },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
      {cards.map((card) => (
        <div
          key={card.label}
          className={`relative p-4 rounded-xl ${card.bg} border ${card.border} backdrop-blur-sm transition-all duration-300 hover:scale-105 hover:shadow-lg ${
            card.pulse && card.value > 0 ? 'animate-pulse shadow-[0_0_12px_3px_rgba(52,211,153,0.3)]' : ''
          }`}
        >
          <div className="flex items-center justify-between mb-2">
            <card.icon className={`w-5 h-5 ${card.pulse && card.value > 0 ? 'text-emerald-400' : 'text-gray-400'}`} />
            <span className={`text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r ${card.color}`}>
              {card.value}
            </span>
          </div>
          <p className="text-xs text-gray-500 font-medium">{card.label}</p>
          {card.pulse && card.value > 0 && (
            <span className="absolute top-2 right-2 flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
