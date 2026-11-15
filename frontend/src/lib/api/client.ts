import type { components } from './schema';

export type Schemas = components['schemas'];

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

  get code(): string {
    return this.problem.code;
  }
}

export const API_BASE = '/api/v1';
const CSRF_COOKIES = ['__Host-csrf', 'csrf'];
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);

function csrfToken(): string | undefined {
  for (const part of document.cookie.split('; ')) {
    const [name, ...rest] = part.split('=');
    if (name && CSRF_COOKIES.includes(name)) return decodeURIComponent(rest.join('='));
  }
  return undefined;
}

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

/**
 * Calls the API with the session cookie. State-changing requests send the CSRF token
 * (double-submit cookie). Errors are thrown as ApiError with the problem details.
 */
export async function api<T = void>(
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE',
  path: string,
  body?: unknown,
  extraHeaders?: Record<string, string>,
): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json', ...extraHeaders };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (!SAFE_METHODS.has(method)) {
    const token = csrfToken();
    if (token) headers['X-CSRF-Token'] = token;
  }
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    credentials: 'same-origin',
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) throw await toApiError(response);
  if (response.status === 204 || response.status === 202) return undefined as T;
  return (await response.json()) as T;
}

/** Sends a file upload (multipart form). The browser sets the multipart content type. */
export async function upload<T>(path: string, form: FormData): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  const token = csrfToken();
  if (token) headers['X-CSRF-Token'] = token;
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers,
    credentials: 'same-origin',
    body: form,
  });
  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as T;
}

/** A same-origin URL for links that download a file with the session cookie. */
export function downloadUrl(path: string): string {
  return `${API_BASE}${path}`;
}
