import { NextRequest, NextResponse } from 'next/server';
import { getCallLogs, addCallLog } from '@/lib/data-store';

// GET /api/calls - Get all call logs
export async function GET() {
  try {
    const calls = getCallLogs();
    return NextResponse.json({ calls });
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}

// POST /api/calls - Add a call log (used by agent webhook)
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { leadId, phoneNumber, businessName, status, duration, transcript } = body;

    const callLog = addCallLog({
      leadId: leadId || null,
      phoneNumber: phoneNumber || '',
      businessName: businessName || 'Unknown',
      status: status || 'completed',
      duration: duration || 0,
      timestamp: new Date().toISOString(),
      transcript: transcript || '',
    });

    return NextResponse.json({ callLog });
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
