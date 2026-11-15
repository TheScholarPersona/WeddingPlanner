import { apiGet, ApiError } from './client';

describe('apiGet', () => {
  afterEach(() => vi.restoreAllMocks());

  it('returns parsed JSON on success', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ status: 'ok', database: 'ok' }), { status: 200 }),
    );

    await expect(apiGet('/api/v1/health')).resolves.toEqual({ status: 'ok', database: 'ok' });
  });

  it('throws an ApiError carrying the problem details', async () => {
    const problem = { type: 'x', title: 'Not Found', status: 404, code: 'not_found' };
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(problem), { status: 404 }),
    );

    const error = await apiGet('/api/v1/health').catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).problem.code).toBe('not_found');
  });
});
