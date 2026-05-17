import { NextResponse } from 'next/server';
import { agentDispatchClient } from '@/lib/server-utils';

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

        // Prepare metadata for the agent - matching exactly what make_call.py sends
        const metadata = JSON.stringify({
            phone_number: phoneNumber,
            lead_id: leadId || null,
            dashboard_url: `http://localhost:${process.env.PORT || 3000}`
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
