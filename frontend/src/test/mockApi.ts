/**
 * Minimal fake backend for component tests. Handlers are keyed "METHOD /path" (path below
 * /api/v1, without query string). Unknown requests fail the test loudly.
 */
type Handler = (body: unknown) => [number, unknown?];

export interface ApiCall {
  method: string;
  path: string;
  body: unknown;
  headers: Record<string, string>;
}

export function mockApi(handlers: Record<string, Handler | [number, unknown?]>) {
  const calls: ApiCall[] = [];
  const spy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = new URL(String(input), 'https://test');
    const method = init?.method ?? 'GET';
    const path = url.pathname.replace(/^\/api\/v1/, '');
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ method, path, body, headers: (init?.headers ?? {}) as Record<string, string> });
    const handler = handlers[`${method} ${path}`];
    if (!handler) throw new Error(`Unexpected request: ${method} ${path}`);
    const [status, json] = typeof handler === 'function' ? handler(body) : handler;
    return new Response(json === undefined ? null : JSON.stringify(json), { status });
  });
  return { calls, spy };
}

export const problem = (status: number, code: string, title = 'Error') => ({
  type: `https://weddingplanner.app/problems/${code}`,
  title,
  status,
  code,
});

export const ORG_ID = '0193a1c2-0000-7000-8000-000000000001';

export function meFixture(role: 'org_admin' | 'member' | 'client' = 'org_admin') {
  return {
    id: '0193a1c2-0000-7000-8000-0000000000aa',
    email: 'ada@example.com',
    full_name: 'Ada Admin',
    locale: 'en',
    memberships: [
      { organization_id: ORG_ID, organization_name: 'Atelier Test', role, accent_color: null },
    ],
  };
}
