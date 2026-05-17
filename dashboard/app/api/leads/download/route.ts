import { NextResponse } from 'next/server';
import { getLeads, leadsToCSV } from '@/lib/data-store';

// GET /api/leads/download - Download leads as CSV
export async function GET() {
  try {
    const leads = getLeads();
    const csv = leadsToCSV(leads);

    return new NextResponse(csv, {
      status: 200,
      headers: {
        'Content-Type': 'text/csv',
        'Content-Disposition': `attachment; filename="leads_${new Date().toISOString().split('T')[0]}.csv"`,
      },
    });
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
