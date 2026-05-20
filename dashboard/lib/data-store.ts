import fs from 'fs';
import path from 'path';

const DATA_DIR = path.join(process.cwd(), 'data');

// Ensure data directory exists
if (!fs.existsSync(DATA_DIR)) {
  fs.mkdirSync(DATA_DIR, { recursive: true });
}

// --- Types ---
export interface Lead {
  id: string;
  businessName: string;
  phoneNumber: string;
  status: 'pending' | 'calling' | 'on_call' | 'demo_confirmed' | 'not_confirmed' | 'no_answer' | 'callback';
  callDate: string | null;
  notes: string;
  campaignId: string;
}

export interface CallLog {
  id: string;
  leadId: string | null;
  phoneNumber: string;
  businessName: string;
  status: 'completed' | 'no_answer' | 'failed' | 'in_progress';
  duration: number;
  timestamp: string;
  transcript: string;
}

// --- Helper Functions ---
function readJSON<T>(filename: string): T[] {
  const filePath = path.join(DATA_DIR, filename);
  if (!fs.existsSync(filePath)) {
    fs.writeFileSync(filePath, '[]', 'utf-8');
    return [];
  }
  try {
    const data = fs.readFileSync(filePath, 'utf-8');
    return JSON.parse(data);
  } catch {
    return [];
  }
}

function writeJSON<T>(filename: string, data: T[]): void {
  const filePath = path.join(DATA_DIR, filename);
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2), 'utf-8');
}

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
}

// --- Leads ---
export function getLeads(): Lead[] {
  return readJSON<Lead>('leads.json');
}

export function addLeads(leads: Omit<Lead, 'id' | 'status' | 'callDate' | 'notes'>[]): Lead[] {
  const existing = getLeads();
  const newLeads: Lead[] = leads.map(l => ({
    id: generateId(),
    businessName: l.businessName,
    phoneNumber: l.phoneNumber,
    status: 'pending',
    callDate: null,
    notes: '',
    campaignId: l.campaignId || 'default',
  }));
  const all = [...existing, ...newLeads];
  writeJSON('leads.json', all);
  return newLeads;
}

export function updateLead(id: string, updates: Partial<Lead>): Lead | null {
  const leads = getLeads();
  const index = leads.findIndex(l => l.id === id);
  if (index === -1) return null;
  leads[index] = { ...leads[index], ...updates };
  writeJSON('leads.json', leads);
  return leads[index];
}

export function deleteLead(id: string): boolean {
  const leads = getLeads();
  const filtered = leads.filter(l => l.id !== id);
  if (filtered.length === leads.length) return false;
  writeJSON('leads.json', filtered);
  return true;
}

export function clearLeads(): void {
  writeJSON('leads.json', []);
}

// --- Call Logs ---
export function getCallLogs(): CallLog[] {
  return readJSON<CallLog>('calls.json');
}

export function addCallLog(log: Omit<CallLog, 'id'>): CallLog {
  const logs = getCallLogs();
  const newLog: CallLog = { id: generateId(), ...log };
  logs.unshift(newLog); // newest first
  writeJSON('calls.json', logs);
  return newLog;
}

export function updateCallLog(id: string, updates: Partial<CallLog>): CallLog | null {
  const logs = getCallLogs();
  const index = logs.findIndex(l => l.id === id);
  if (index === -1) return null;
  logs[index] = { ...logs[index], ...updates };
  writeJSON('calls.json', logs);
  return logs[index];
}

// --- CSV Parsing ---
export function parseCSV(csvText: string): { businessName: string; phoneNumber: string }[] {
  const lines = csvText.trim().split('\n');
  if (lines.length < 2) return [];

  // Parse header
  const header = lines[0].split(',').map(h => h.trim().toLowerCase().replace(/['"]/g, ''));
  
  // Find column indices (flexible matching)
  const nameIdx = header.findIndex(h => 
    h.includes('business') || h.includes('name') || h.includes('company') || h.includes('shop')
  );
  const phoneIdx = header.findIndex(h => 
    h.includes('phone') || h.includes('number') || h.includes('mobile') || h.includes('contact')
  );

  if (nameIdx === -1 || phoneIdx === -1) {
    // Try positional: assume first column is name, second is phone
    return lines.slice(1).filter(l => l.trim()).map(line => {
      const cols = line.split(',').map(c => c.trim().replace(/['"]/g, ''));
      return {
        businessName: cols[0] || 'Unknown',
        phoneNumber: cols[1] || '',
      };
    }).filter(r => r.phoneNumber);
  }

  return lines.slice(1).filter(l => l.trim()).map(line => {
    const cols = line.split(',').map(c => c.trim().replace(/['"]/g, ''));
    return {
      businessName: cols[nameIdx] || 'Unknown',
      phoneNumber: cols[phoneIdx] || '',
    };
  }).filter(r => r.phoneNumber);
}

// --- Export to CSV ---
export function leadsToCSV(leads: Lead[]): string {
  const header = 'Business Name,Phone Number,Status,Call Date,Notes';
  const rows = leads.map(l => 
    `"${l.businessName}","${l.phoneNumber}","${l.status}","${l.callDate || ''}","${l.notes || ''}"`
  );
  return [header, ...rows].join('\n');
}

// --- Stats ---
export function getStats() {
  const leads = getLeads();
  const calls = getCallLogs();
  return {
    totalLeads: leads.length,
    pending: leads.filter(l => l.status === 'pending').length,
    calling: leads.filter(l => l.status === 'calling').length,
    onCall: leads.filter(l => l.status === 'on_call').length,
    demoConfirmed: leads.filter(l => l.status === 'demo_confirmed').length,
    notConfirmed: leads.filter(l => l.status === 'not_confirmed').length,
    noAnswer: leads.filter(l => l.status === 'no_answer').length,
    callback: leads.filter(l => l.status === 'callback').length,
    totalCalls: calls.length,
  };
}
