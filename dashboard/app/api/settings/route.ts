import { NextResponse } from 'next/server';
import { getSettings, updateSettings } from '@/lib/data-store';
import { autoCallNext } from '@/lib/server-utils';

export async function GET() {
    try {
        const settings = getSettings();
        return NextResponse.json(settings);
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 });
    }
}

export async function PATCH(request: Request) {
    try {
        const body = await request.json();
        const updated = updateSettings(body);

        // If auto-calling is turned ON, trigger the first call after a short delay (2s)
        if (body.autoCallNextLead) {
            const host = request.headers.get('host') || 'localhost:3000';
            console.log("[AUTO CALL] Auto-call toggled ON. Triggering check in 2 seconds.");
            setTimeout(() => {
                autoCallNext(host);
            }, 2000);
        }

        return NextResponse.json(updated);
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 });
    }
}
