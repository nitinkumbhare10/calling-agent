import { RoomServiceClient, SipClient, AgentDispatchClient } from 'livekit-server-sdk';

const LIVEKIT_URL = process.env.LIVEKIT_URL;
const LIVEKIT_API_KEY = process.env.LIVEKIT_API_KEY;
const LIVEKIT_API_SECRET = process.env.LIVEKIT_API_SECRET;

if (!LIVEKIT_URL || !LIVEKIT_API_KEY || !LIVEKIT_API_SECRET) {
  throw new Error("Missing LiveKit Credentials");
}

export const roomService = new RoomServiceClient(LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET);
export const sipClient = new SipClient(LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET);
export const agentDispatchClient = new AgentDispatchClient(LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET);

import { getLeads, updateLead, getSettings, addCallLog, updateSettings } from './data-store';

export async function autoCallNext(host: string) {
  try {
    // 1. Check settings again
    const settings = getSettings();
    if (!settings.autoCallNextLead) {
      console.log("[AUTO CALL] Auto-call is disabled. Aborting.");
      return;
    }

    if (settings.autoDialEndTime && Date.now() > settings.autoDialEndTime) {
      console.log("[AUTO CALL] Auto-call duration has expired. Disabling auto-call.");
      updateSettings({ autoCallNextLead: false, autoDialEndTime: null });
      return;
    }

    // 2. Check if any call is already in progress
    const leads = getLeads();
    const activeCall = leads.find(l => l.status === 'calling' || l.status === 'on_call');
    if (activeCall) {
      console.log("[AUTO CALL] A call is already in progress. Aborting auto-call.");
      return;
    }

    // 3. Find the next pending lead
    const nextLead = leads.find(l => l.status === 'pending');
    if (!nextLead) {
      console.log("[AUTO CALL] No more pending leads. Auto-call stopped.");
      return;
    }

    console.log(`[AUTO CALL] Initiating call to next lead: ${nextLead.businessName} (${nextLead.phoneNumber})`);

    // 4. Set status to calling
    updateLead(nextLead.id, { status: 'calling', callDate: new Date().toISOString() });

    // 5. Dispatch LiveKit Agent
    const cleanNumber = nextLead.phoneNumber.replace(/\+/g, '').replace(/\s/g, '');
    const roomName = `call-${cleanNumber}-${Math.floor(Math.random() * 10000)}`;

    const protocol = host.includes('localhost') ? 'http' : 'https';
    const dashboardUrl = `${protocol}://${host}`;

    const metadata = JSON.stringify({
      phone_number: nextLead.phoneNumber,
      lead_id: nextLead.id,
      business_name: nextLead.businessName || null,
      dashboard_url: dashboardUrl
    });

    const dispatch = await agentDispatchClient.createDispatch(
      roomName,
      "outbound-caller",
      { metadata: metadata }
    );

    // 6. Log the call in calls.json
    addCallLog({
      leadId: nextLead.id,
      phoneNumber: nextLead.phoneNumber,
      businessName: nextLead.businessName,
      status: 'in_progress',
      duration: 0,
      timestamp: new Date().toISOString(),
      transcript: '',
    });

    console.log(`[AUTO CALL] Successfully dispatched call to ${nextLead.businessName} (Dispatch ID: ${dispatch.id})`);
  } catch (error) {
    console.error("[AUTO CALL] Error during auto-call execution:", error);
  }
}
