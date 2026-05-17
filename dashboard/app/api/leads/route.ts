import { NextRequest, NextResponse } from 'next/server';
import { getLeads, addLeads, clearLeads, parseCSV, getStats } from '@/lib/data-store';

// GET /api/leads - Get all leads + stats
export async function GET() {
  try {
    const leads = getLeads();
    const stats = getStats();
    return NextResponse.json({ leads, stats });
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}

// POST /api/leads - Upload CSV and add leads
export async function POST(req: NextRequest) {
  try {
    const contentType = req.headers.get('content-type') || '';

    if (contentType.includes('multipart/form-data')) {
      // Handle file upload
      const formData = await req.formData();
      const file = formData.get('file') as File;
      const campaignId = (formData.get('campaignId') as string) || 'default';

      if (!file) {
        return NextResponse.json({ error: 'No file provided' }, { status: 400 });
      }

      const csvText = await file.text();
      const parsed = parseCSV(csvText);

      if (parsed.length === 0) {
        return NextResponse.json({ error: 'No valid records found in CSV. Make sure it has columns for business name and phone number.' }, { status: 400 });
      }

      const leadsToAdd = parsed.map(p => ({
        businessName: p.businessName,
        phoneNumber: p.phoneNumber,
        campaignId,
      }));

      const newLeads = addLeads(leadsToAdd);
      const stats = getStats();

      return NextResponse.json({ 
        message: `${newLeads.length} leads imported successfully`,
        count: newLeads.length,
        leads: getLeads(),
        stats,
      });
    } else {
      // Handle JSON body (manual add)
      const body = await req.json();
      const { businessName, phoneNumber, campaignId } = body;

      if (!businessName || !phoneNumber) {
        return NextResponse.json({ error: 'Business name and phone number are required' }, { status: 400 });
      }

      const newLeads = addLeads([{ businessName, phoneNumber, campaignId: campaignId || 'default' }]);
      return NextResponse.json({ lead: newLeads[0], leads: getLeads(), stats: getStats() });
    }
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}

// DELETE /api/leads - Clear all leads
export async function DELETE() {
  try {
    clearLeads();
    return NextResponse.json({ message: 'All leads cleared', stats: getStats() });
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
