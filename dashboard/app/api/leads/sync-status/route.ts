import { NextResponse } from 'next/server';
import { getLeads, updateLead } from '@/lib/data-store';
import { roomService } from '@/lib/server-utils';

// POST /api/leads/sync-status - Auto-fix stale "calling" statuses
// Checks LiveKit rooms and marks leads as "no_answer" if their room no longer exists
export async function POST() {
  try {
    const leads = getLeads();
    const callingLeads = leads.filter(l => l.status === 'calling');
    
    if (callingLeads.length === 0) {
      return NextResponse.json({ message: 'No calling leads to sync', fixed: 0 });
    }

    // Get all active LiveKit rooms
    let activeRooms: string[] = [];
    try {
      const rooms = await roomService.listRooms();
      activeRooms = rooms.map(r => r.name);
    } catch (e) {
      console.error('Failed to list rooms:', e);
    }

    let fixed = 0;
    for (const lead of callingLeads) {
      // Check if the call date is older than 5 minutes (stale)
      const callTime = lead.callDate ? new Date(lead.callDate).getTime() : 0;
      const now = Date.now();
      const fiveMinutes = 5 * 60 * 1000;
      
      if (callTime && (now - callTime) > fiveMinutes) {
        // Check if there's an active room for this phone number
        const cleanPhone = lead.phoneNumber.replace(/\+/g, '').replace(/\s/g, '');
        const hasActiveRoom = activeRooms.some(room => room.includes(cleanPhone));
        
        if (!hasActiveRoom) {
          // No active room found, mark as no_answer (stale call)
          updateLead(lead.id, { status: 'no_answer' });
          fixed++;
          console.log(`Fixed stale calling status for lead ${lead.id} (${lead.businessName})`);
        }
      }
    }

    return NextResponse.json({ message: `Synced status for ${fixed} leads`, fixed });
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
