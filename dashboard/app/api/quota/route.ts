import { NextResponse } from 'next/server';
import { roomService, sipClient } from '@/lib/server-utils';
import fs from 'fs';
import path from 'path';

const STATE_FILE_PATH = path.join(process.cwd(), 'quota_state.json');

interface QuotaState {
  lastNotified: Record<string, 'ok' | 'error' | 'quota_exceeded' | 'checking'>;
}

function readQuotaState(): QuotaState {
  try {
    if (fs.existsSync(STATE_FILE_PATH)) {
      const data = fs.readFileSync(STATE_FILE_PATH, 'utf8');
      return JSON.parse(data);
    }
  } catch (e) {
    console.error('Failed to read quota state:', e);
  }
  return { lastNotified: {} };
}

function writeQuotaState(state: QuotaState) {
  try {
    fs.writeFileSync(STATE_FILE_PATH, JSON.stringify(state, null, 2), 'utf8');
  } catch (e) {
    console.error('Failed to write quota state:', e);
  }
}

async function sendTelegramMessage(text: string) {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TELEGRAM_CHAT_ID;
  if (!token || !chatId) {
    console.log('[TELEGRAM] Missing token or chat ID. Notification skipped.');
    return;
  }
  const url = `https://api.telegram.org/bot${token}/sendMessage`;
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        chat_id: chatId,
        text,
        parse_mode: 'Markdown',
      }),
    });
    if (!res.ok) {
      console.error('[TELEGRAM] Failed to send message:', await res.text());
    } else {
      console.log('[TELEGRAM] Quota alert sent successfully');
    }
  } catch (e) {
    console.error('[TELEGRAM] Error sending Telegram message:', e);
  }
}


interface ServiceStatus {
  name: string;
  status: 'ok' | 'error' | 'quota_exceeded' | 'checking';
  message: string;
  checkedAt: string;
}

async function checkCartesia(): Promise<ServiceStatus> {
  const key = process.env.CARTESIA_API_KEY;
  const name = 'Cartesia TTS';
  if (!key) return { name, status: 'error', message: 'API key not configured', checkedAt: new Date().toISOString() };

  try {
    const res = await fetch('https://api.cartesia.ai/voices', {
      method: 'GET',
      headers: { 'X-API-Key': key, 'Cartesia-Version': '2024-06-10' },
      signal: AbortSignal.timeout(8000),
    });
    if (res.ok) return { name, status: 'ok', message: 'Active', checkedAt: new Date().toISOString() };
    if (res.status === 402) return { name, status: 'quota_exceeded', message: 'Model credits limit reached', checkedAt: new Date().toISOString() };
    if (res.status === 401) return { name, status: 'error', message: 'Invalid API key', checkedAt: new Date().toISOString() };
    return { name, status: 'error', message: `HTTP ${res.status}`, checkedAt: new Date().toISOString() };
  } catch (e: any) {
    return { name, status: 'error', message: e?.message || 'Connection failed', checkedAt: new Date().toISOString() };
  }
}

async function checkDeepgram(): Promise<ServiceStatus> {
  const key = process.env.DEEPGRAM_API_KEY;
  const name = 'Deepgram STT';
  if (!key) return { name, status: 'error', message: 'API key not configured', checkedAt: new Date().toISOString() };

  try {
    const res = await fetch('https://api.deepgram.com/v1/projects', {
      method: 'GET',
      headers: { 'Authorization': `Token ${key}` },
      signal: AbortSignal.timeout(8000),
    });
    if (res.ok) return { name, status: 'ok', message: 'Active', checkedAt: new Date().toISOString() };
    if (res.status === 401 || res.status === 403) return { name, status: 'error', message: 'Invalid API key or forbidden', checkedAt: new Date().toISOString() };
    if (res.status === 402) return { name, status: 'quota_exceeded', message: 'Credits exhausted', checkedAt: new Date().toISOString() };
    return { name, status: 'error', message: `HTTP ${res.status}`, checkedAt: new Date().toISOString() };
  } catch (e: any) {
    return { name, status: 'error', message: e?.message || 'Connection failed', checkedAt: new Date().toISOString() };
  }
}

async function checkGroq(): Promise<ServiceStatus> {
  const key = process.env.GROQ_API_KEY;
  const name = 'Groq LLM';
  if (!key) return { name, status: 'error', message: 'API key not configured', checkedAt: new Date().toISOString() };

  try {
    const res = await fetch('https://api.groq.com/openai/v1/models', {
      method: 'GET',
      headers: { 'Authorization': `Bearer ${key}` },
      signal: AbortSignal.timeout(8000),
    });
    if (res.ok) return { name, status: 'ok', message: 'Active', checkedAt: new Date().toISOString() };
    if (res.status === 429) return { name, status: 'quota_exceeded', message: 'Rate limit / quota exceeded', checkedAt: new Date().toISOString() };
    if (res.status === 401) return { name, status: 'error', message: 'Invalid API key', checkedAt: new Date().toISOString() };
    return { name, status: 'error', message: `HTTP ${res.status}`, checkedAt: new Date().toISOString() };
  } catch (e: any) {
    return { name, status: 'error', message: e?.message || 'Connection failed', checkedAt: new Date().toISOString() };
  }
}

async function checkSarvam(): Promise<ServiceStatus> {
  const key = process.env.SARVAM_API_KEY;
  const name = 'Sarvam TTS';
  if (!key) return { name, status: 'error', message: 'API key not configured', checkedAt: new Date().toISOString() };

  try {
    // Sarvam doesn't have a dedicated health endpoint; use a lightweight list-voices or similar
    const res = await fetch('https://api.sarvam.ai/text-to-speech', {
      method: 'POST',
      headers: {
        'api-subscription-key': key,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        inputs: ["test"],
        target_language_code: "hi-IN",
        model: "bulbul:v3",
        speaker: "amit",
      }),
      signal: AbortSignal.timeout(8000),
    });
    // Even a 200 or 400 (bad request) means the API is reachable and key works
    if (res.ok || res.status === 200) return { name, status: 'ok', message: 'Active', checkedAt: new Date().toISOString() };
    if (res.status === 401) return { name, status: 'error', message: 'Invalid API key', checkedAt: new Date().toISOString() };
    if (res.status === 402 || res.status === 429) return { name, status: 'quota_exceeded', message: 'Credits/rate limit exceeded', checkedAt: new Date().toISOString() };
    // 400 means API is up, key is valid, just bad params (which is fine for health check)
    if (res.status === 400) return { name, status: 'ok', message: 'Active', checkedAt: new Date().toISOString() };
    return { name, status: 'error', message: `HTTP ${res.status}`, checkedAt: new Date().toISOString() };
  } catch (e: any) {
    return { name, status: 'error', message: e?.message || 'Connection failed', checkedAt: new Date().toISOString() };
  }
}

async function checkLiveKit(): Promise<ServiceStatus> {
  const name = 'LiveKit Infra';
  try {
    // listRooms is a very lightweight call
    await roomService.listRooms();
    return { name, status: 'ok', message: 'Active', checkedAt: new Date().toISOString() };
  } catch (e: any) {
    const msg = e?.message || 'Connection failed';
    if (msg.includes('402') || msg.includes('payment')) {
      return { name, status: 'quota_exceeded', message: 'Account limit reached', checkedAt: new Date().toISOString() };
    }
    return { name, status: 'error', message: msg, checkedAt: new Date().toISOString() };
  }
}

async function checkVobiz(): Promise<ServiceStatus> {
  const trunkId = process.env.VOBIZ_SIP_TRUNK_ID;
  const name = 'Vobiz SIP';
  if (!trunkId) return { name, status: 'error', message: 'SIP Trunk ID not configured', checkedAt: new Date().toISOString() };

  try {
    // List SIP trunks via LiveKit API to verify the trunk exists and is active
    const trunks = await sipClient.listSipInboundTrunk();
    // Check if our trunk ID exists in the list
    const ourTrunk = trunks.find((t: any) => t.sipTrunkId === trunkId);
    if (ourTrunk) {
      return { name, status: 'ok', message: 'Trunk active', checkedAt: new Date().toISOString() };
    }
    // Trunk not found but API is reachable — might be outbound-only trunk, still OK
    return { name, status: 'ok', message: 'SIP reachable', checkedAt: new Date().toISOString() };
  } catch (e: any) {
    const msg = e?.message || 'Connection failed';
    if (msg.includes('402') || msg.includes('payment') || msg.includes('Payment Required')) {
      return { name, status: 'quota_exceeded', message: 'SIP credits exhausted', checkedAt: new Date().toISOString() };
    }
    if (msg.includes('401') || msg.includes('Unauthorized')) {
      return { name, status: 'error', message: 'Invalid credentials', checkedAt: new Date().toISOString() };
    }
    return { name, status: 'error', message: msg, checkedAt: new Date().toISOString() };
  }
}

export async function GET() {
  // Run all checks in parallel for speed
  const [cartesia, deepgram, groq, sarvam, livekit, vobiz] = await Promise.all([
    checkCartesia(),
    checkDeepgram(),
    checkGroq(),
    checkSarvam(),
    checkLiveKit(),
    checkVobiz(),
  ]);

  const services = [cartesia, deepgram, groq, sarvam, livekit, vobiz];
  const hasIssue = services.some(s => s.status !== 'ok');

  // TELEGRAM NOTIFICATION SYSTEM FOR QUOTA EXHAUSTED/RESTORED
  try {
    const state = readQuotaState();
    let stateChanged = false;

    for (const service of services) {
      const prevStatus = state.lastNotified[service.name];
      const newStatus = service.status;

      // If status changed to quota_exceeded
      if (newStatus === 'quota_exceeded' && prevStatus !== 'quota_exceeded') {
        const msg = `⚠️ *Quota Alert!*\n\n*Service:* ${service.name}\n*Status:* Quota Exceeded\n*Message:* ${service.message}`;
        await sendTelegramMessage(msg);
        state.lastNotified[service.name] = 'quota_exceeded';
        stateChanged = true;
      }
      // If status transitioned back to ok from quota_exceeded (recovery)
      else if (newStatus === 'ok' && prevStatus === 'quota_exceeded') {
        const msg = `✅ *Quota Restored!*\n\n*Service:* ${service.name}\n*Status:* OK\n*Message:* Service is active again.`;
        await sendTelegramMessage(msg);
        state.lastNotified[service.name] = 'ok';
        stateChanged = true;
      }
      // Initialize or update state if it is not set (so we track transitions from undefined or other statuses)
      else if (prevStatus === undefined || (newStatus === 'ok' && prevStatus !== 'ok' && prevStatus !== 'quota_exceeded')) {
        state.lastNotified[service.name] = newStatus;
        stateChanged = true;
      }
    }

    if (stateChanged) {
      writeQuotaState(state);
    }
  } catch (e) {
    console.error('Telegram notification quota check failed:', e);
  }

  return NextResponse.json({
    services,
    overall: hasIssue ? 'warning' : 'healthy',
    checkedAt: new Date().toISOString(),
  });
}
