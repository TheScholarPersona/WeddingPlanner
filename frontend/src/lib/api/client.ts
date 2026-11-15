import type { paths } from './schema';

/** RFC 9457 Problem Details, as returned by every API error. */
export interface ProblemDetails {
  type: string;
  title: string;
  status: number;
  code: string;
  detail?: string;
  errors?: { field: string; code: string; message: string }[];
}

export class ApiError extends Error {
  readonly problem: ProblemDetails;

  constructor(problem: ProblemDetails) {
    super(problem.title);
    this.name = 'ApiError';
    this.problem = problem;
  }

  get status(): number {
    return this.problem.status;
  }
}

export const API_BASE = '/api/v1';

type GetPath = {
  [P in keyof paths]: paths[P] extends { get: unknown } ? P : never;
}[keyof paths];

type GetResponse<P extends GetPath> = paths[P] extends {
  get: { responses: { 200: { content: { 'application/json': infer R } } } };
}
  ? R
  : never;

async function toApiError(response: Response): Promise<ApiError> {
  try {
    return new ApiError((await response.json()) as ProblemDetails);
  } catch {
    return new ApiError({
      type: 'about:blank',
      title: response.statusText || 'Request failed',
      status: response.status,
      code: 'unknown_error',
    });
  }
}

/** Typed GET against the generated OpenAPI schema. Cookies carry the session. */
export async function apiGet<P extends GetPath>(
  path: P,
  init?: RequestInit,
): Promise<GetResponse<P>> {
  const response = await fetch(`${path}`, {
    ...init,
    method: 'GET',
    credentials: 'same-origin',
    headers: { Accept: 'application/json', ...init?.headers },
  });
  if (!response.ok) {
    throw await toApiError(response);
  }
  return (await response.json()) as GetResponse<P>;
}
