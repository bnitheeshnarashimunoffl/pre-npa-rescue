import { http, HttpResponse } from 'msw';
import { fixtures } from './fixtures';

export const handlers = [
  // Auth
  http.post('*/api/v1/auth/login', async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as { username?: string };
    const username = body.username || 'priya';
    const roleMap: Record<string, string> = {
      priya: 'customer',
      ravi: 'customer',
      collector1: 'collector',
      officer1: 'hardship_officer',
      admin1: 'admin',
      auditor1: 'auditor'
    };
    const role = roleMap[username] || 'customer';
    return HttpResponse.json({
      access_token: `mock-jwt-token-for-${username}`,
      token_type: 'bearer',
      role,
      user_id: username === 'priya' ? 'CUST-DEMO-PRIYA' : username === 'ravi' ? 'CUST-DEMO-RAVI' : username
    });
  }),

  // Health
  http.get('*/api/v1/health', () => {
    return HttpResponse.json({ status: 'ok', version: '0.1.0' });
  }),

  // Collector queue
  http.get('*/api/v1/collector/queue', () => {
    return HttpResponse.json(fixtures.queue);
  }),

  // Collector account summary
  http.get('*/api/v1/collector/accounts/:accountId/summary', ({ params }) => {
    const accountId = String(params.accountId);
    const item = fixtures.queue.items.find((i: any) => i.account_id === accountId) || fixtures.queue.items[0];
    return HttpResponse.json({
      account_id: accountId,
      customer_id: accountId.includes('RAVI') ? 'CUST-DEMO-RAVI' : 'CUST-DEMO-PRIYA',
      customer_name: item?.customer_name || 'Cardholder',
      bucket: item?.bucket || 'sma0',
      dpd: item?.dpd || 15,
      total_due_paise: item?.total_due_paise || 1500000,
      risk: item?.nba?.risk || fixtures.riskScore,
      segment: item?.nba?.segment || fixtures.segment,
      uplift: item?.nba?.uplift || fixtures.uplift,
      nba: item?.nba || fixtures.nba,
      offers: [fixtures.offer],
      contacts: [],
      dpd_history: [
        { month: '2026-04', dpd: 0, payments_paise: 500000 },
        { month: '2026-05', dpd: 0, payments_paise: 500000 },
        { month: '2026-06', dpd: 0, payments_paise: 200000 },
        { month: '2026-07', dpd: 5, payments_paise: 100000 },
        { month: '2026-08', dpd: 12, payments_paise: 50000 },
        { month: '2026-09', dpd: item?.dpd || 15, payments_paise: 0 }
      ]
    });
  }),

  // Models & NBA endpoints
  http.get('*/api/v1/accounts/:accountId/risk', () => {
    return HttpResponse.json(fixtures.riskScore);
  }),

  http.get('*/api/v1/accounts/:accountId/segment', () => {
    return HttpResponse.json(fixtures.segment);
  }),

  http.get('*/api/v1/accounts/:accountId/uplift', () => {
    return HttpResponse.json(fixtures.uplift);
  }),

  http.get('*/api/v1/accounts/:accountId/nba', () => {
    return HttpResponse.json(fixtures.nba);
  }),

  // Compliance check
  http.post('*/api/v1/contacts/check', () => {
    return HttpResponse.json({
      allowed: true,
      rule_ids: ['RBI-454Y4-WINDOW'],
      next_allowed_at: null,
      explanation: 'Contact permitted within 08:00–19:00 IST window (IS 18295 / RBI 454Y)'
    });
  }),

  // Relief options
  http.get('*/api/v1/customers/:customerId/relief-options', ({ params }) => {
    const customerId = String(params.customerId);
    if (customerId.includes('RAVI')) {
      return HttpResponse.json(fixtures.reliefOptionsRavi);
    }
    return HttpResponse.json(fixtures.reliefOptionsPriya);
  }),

  // Offers
  http.post('*/api/v1/offers', () => {
    return HttpResponse.json(fixtures.offer);
  }),

  http.post('*/api/v1/offers/:id/approve', () => {
    return HttpResponse.json({ ...fixtures.offer, status: 'approved' });
  }),

  http.post('*/api/v1/offers/:id/accept', () => {
    return HttpResponse.json({ ...fixtures.offer, status: 'accepted' });
  }),

  http.post('*/api/v1/offers/:id/reject', () => {
    return HttpResponse.json({ ...fixtures.offer, status: 'rejected' });
  }),

  // Chat
  http.post('*/api/v1/chat/sessions', () => {
    return HttpResponse.json({ session_id: 'SESS-DEMO-001' });
  }),

  http.post('*/api/v1/chat/sessions/:sid/messages', async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as { text?: string };
    const text = body.text?.toLowerCase() || '';
    if (text.includes('lost') || text.includes('cannot pay') || text.includes('ravi') || text.includes('0')) {
      return HttpResponse.json(fixtures.botReplyZeroCapacity);
    }
    return HttpResponse.json(fixtures.botReplyOffer);
  }),

  // Complaints
  http.post('*/api/v1/complaints', () => {
    return HttpResponse.json(fixtures.complaint);
  }),

  http.get('*/api/v1/complaints/:docketNo', () => {
    return HttpResponse.json(fixtures.complaint);
  }),

  // Callbacks
  http.post('*/api/v1/callbacks', () => {
    return HttpResponse.json(fixtures.callback);
  }),

  http.get('*/api/v1/callbacks', () => {
    return HttpResponse.json([fixtures.callback]);
  }),

  // Policy admin
  http.get('*/api/v1/admin/policy', () => {
    return HttpResponse.json(fixtures.policy);
  }),

  http.put('*/api/v1/admin/policy', async ({ request }) => {
    const updated = await request.json();
    return HttpResponse.json(updated);
  }),

  // Red team & Scorecard
  http.get('*/api/v1/redteam/scorecard/latest', () => {
    return HttpResponse.json(fixtures.scorecard);
  }),

  http.post('*/api/v1/redteam/runs', () => {
    return HttpResponse.json({ run_id: 'RT-20261012-1100' });
  }),

  // Metrics
  http.get('*/api/v1/metrics/simulation', () => {
    return HttpResponse.json(fixtures.simulationMetrics);
  }),

  http.get('*/api/v1/metrics/kpis', () => {
    return HttpResponse.json({
      accounts_in_queue: fixtures.queue.items.length,
      contact_window_compliance_pct: 100.0,
      open_complaints: 1,
      handoffs_today: 4
    });
  })
];
