import { NextRequest, NextResponse } from 'next/server';
import { updateLead, deleteLead, getLeads, getStats, getSettings } from '@/lib/data-store';
import { autoCallNext } from '@/lib/server-utils';

// PATCH /api/leads/[id] - Update a lead's status
export async function PATCH(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const body = await req.json();
    const updated = updateLead(id, body);
    if (!updated) {
      return NextResponse.json({ error: 'Lead not found' }, { status: 404 });
    }

    // Trigger auto-call for next lead if setting is enabled and call ended
    const finalStatuses = ['demo_confirmed', 'not_confirmed', 'no_answer', 'callback'];
    if (body.status && finalStatuses.includes(body.status)) {
      const settings = getSettings();
      if (settings.autoCallNextLead) {
        const host = req.headers.get('host') || 'localhost:3000';
        console.log(`[AUTO CALL] Lead ${id} call ended with status '${body.status}'. Triggering next call in 10 seconds.`);
        setTimeout(() => {
          autoCallNext(host);
        }, 10000);
      }
    }

    return NextResponse.json({ lead: updated, leads: getLeads(), stats: getStats() });
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}

// DELETE /api/leads/[id] - Delete a specific lead
export async function DELETE(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const success = deleteLead(id);
    if (!success) {
      return NextResponse.json({ error: 'Lead not found' }, { status: 404 });
    }
    return NextResponse.json({ message: 'Lead deleted', leads: getLeads(), stats: getStats() });
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
