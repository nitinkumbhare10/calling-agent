import { NextRequest, NextResponse } from 'next/server';
import { updateLead, deleteLead, getLeads, getStats } from '@/lib/data-store';

// PATCH /api/leads/[id] - Update a lead's status
export async function PATCH(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const body = await req.json();
    const updated = updateLead(id, body);
    if (!updated) {
      return NextResponse.json({ error: 'Lead not found' }, { status: 404 });
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
