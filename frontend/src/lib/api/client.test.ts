import { api, ApiError } from './client';

describe('api', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    document.cookie = 'csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
  });

  it('returns parsed JSON on success', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ status: 'ok' }), { status: 200 }),
    );

    await expect(api('GET', '/health')).resolves.toEqual({ status: 'ok' });
  });

  it('sends the CSRF cookie value on state-changing requests', async () => {
    document.cookie = 'csrf=abc123';
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response(null, { status: 204 }));

    await api('POST', '/auth/logout');

    const headers = fetchMock.mock.calls[0]?.[1]?.headers as Record<string, string>;
    expect(headers['X-CSRF-Token']).toBe('abc123');
  });

  it('throws an ApiError carrying the problem details', async () => {
    const problem = { type: 'x', title: 'Not Found', status: 404, code: 'not_found' };
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(problem), { status: 404 }),
    );

    const error = await api('GET', '/x').catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe('not_found');
  });
});
