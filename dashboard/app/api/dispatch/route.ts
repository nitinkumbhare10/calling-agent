import { NextResponse } from 'next/server';
import { agentDispatchClient } from '@/lib/server-utils';
import { getLeads } from '@/lib/data-store';

export async function POST(request: Request) {
    try {
        const body = await request.json();
        const { phoneNumber, prompt, modelProvider, voice, leadId } = body;

        if (!phoneNumber) {
            return NextResponse.json({ error: "Phone number is required" }, { status: 400 });
        }

        // Generate a unique room name for this call
        const cleanNumber = phoneNumber.replace(/\+/g, '').replace(/\s/g, '');
        const roomName = `call-${cleanNumber}-${Math.floor(Math.random() * 10000)}`;

        console.log(`Dispatching Agent to call ${phoneNumber} in room ${roomName}`);

        // Fetch business name dynamically from data-store
        let businessName = '';
        if (leadId) {
            const leads = getLeads();
            const lead = leads.find(l => l.id === leadId);
            if (lead) {
                businessName = lead.businessName;
            }
        }

        // Determine request host to correctly notify the hosted dashboard (Vercel)
        const host = request.headers.get('host') || 'localhost:3000';
        const protocol = host.includes('localhost') ? 'http' : 'https';
        const dashboardUrl = `${protocol}://${host}`;

        // Prepare metadata for the agent
        const metadata = JSON.stringify({
            phone_number: phoneNumber,
            lead_id: leadId || null,
            business_name: businessName || null,
            dashboard_url: dashboardUrl
        });

        // Dispatch the Agent
        // This tells LiveKit to find a worker named 'outbound-caller' and send it to the room.
        // The agent worker (agent.py) will then initiate the SIP call.
        const dispatch = await agentDispatchClient.createDispatch(
            roomName,
            "outbound-caller", // Must match agent_name in agent.py
            {
                metadata: metadata
            }
        );

        return NextResponse.json({
            success: true,
            roomName,
            dispatchId: dispatch.id
        });

    } catch (error: any) {
        console.error("Error dispatching call:", error);
        return NextResponse.json({ error: error.message || "Internal Server Error" }, { status: 500 });
    }
}
