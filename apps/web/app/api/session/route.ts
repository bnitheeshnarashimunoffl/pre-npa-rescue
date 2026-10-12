import { NextRequest, NextResponse } from 'next/server';

export interface SessionData {
  username: string;
  role: string;
  customerId?: string;
  accountId?: string;
  token: string;
}

const DEMO_PERSONAS: Record<string, { role: string; customerId?: string; accountId?: string; defaultPath: string }> = {
  priya: {
    role: 'customer',
    customerId: 'CUST-DEMO-PRIYA',
    accountId: 'ACC-DEMO-PRIYA',
    defaultPath: '/chat'
  },
  ravi: {
    role: 'customer',
    customerId: 'CUST-DEMO-RAVI',
    accountId: 'ACC-DEMO-RAVI',
    defaultPath: '/chat'
  },
  collector1: {
    role: 'collector',
    defaultPath: '/dashboard'
  },
  officer1: {
    role: 'hardship_officer',
    defaultPath: '/dashboard'
  },
  admin1: {
    role: 'admin',
    defaultPath: '/policy'
  },
  auditor1: {
    role: 'auditor',
    defaultPath: '/scorecard'
  }
};

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const username = body.username as string;

    const persona = DEMO_PERSONAS[username];
    if (!persona) {
      return NextResponse.json(
        { error: { code: 'INVALID_CREDENTIALS', message: 'Unknown demo user' } },
        { status: 400 }
      );
    }

    const session: SessionData = {
      username,
      role: persona.role,
      customerId: persona.customerId,
      accountId: persona.accountId,
      token: `demo-jwt-token-for-${username}`
    };

    const response = NextResponse.json({
      success: true,
      session,
      defaultPath: persona.defaultPath
    });

    // Set session cookies
    response.cookies.set('demo_session', JSON.stringify(session), {
      httpOnly: false, // accessible to client for role display
      path: '/',
      sameSite: 'lax',
      maxAge: 60 * 60 * 24 // 24 hours
    });

    response.cookies.set('auth_token', session.token, {
      httpOnly: true,
      path: '/',
      sameSite: 'lax',
      maxAge: 60 * 60 * 24
    });

    return response;
  } catch (err: any) {
    return NextResponse.json(
      { error: { code: 'SERVER_ERROR', message: err?.message || 'Failed to establish session' } },
      { status: 500 }
    );
  }
}

export async function DELETE() {
  const response = NextResponse.json({ success: true });
  response.cookies.delete('demo_session');
  response.cookies.delete('auth_token');
  return response;
}
