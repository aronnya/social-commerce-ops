export class ApiError extends Error {
  readonly status: number
  readonly detail: unknown

  constructor(message: string, status: number, detail: unknown = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

function formatDetail(detail: unknown): string {
  if (typeof detail === 'string' && detail.trim()) {
    return detail
  }
  if (detail && typeof detail === 'object' && 'detail' in detail) {
    return formatDetail((detail as { detail: unknown }).detail)
  }
  if (Array.isArray(detail)) {
    return detail.map((item) => formatDetail(item)).filter(Boolean).join('; ')
  }
  return ''
}

async function parseBody(response: Response): Promise<unknown> {
  const text = await response.text()
  if (!text) {
    return null
  }
  try {
    return JSON.parse(text) as unknown
  } catch {
    return text
  }
}

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, {
      ...init,
      headers: {
        Accept: 'application/json',
        ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
        ...init?.headers,
      },
    })
  } catch {
    throw new ApiError('Network request failed.', 0)
  }

  const body = await parseBody(response)
  if (!response.ok) {
    const fromBody = formatDetail(body)
    const fallback =
      response.status === 404
        ? 'The requested record was not found.'
        : response.status === 409
          ? 'This action conflicts with the current record state.'
          : response.status === 422
            ? 'The request was not valid.'
            : `Request failed with status ${response.status}.`
    throw new ApiError(fromBody || fallback, response.status, body)
  }

  return body as T
}

export function apiGet<T>(path: string): Promise<T> {
  return apiRequest<T>(path)
}

export function withQuery(
  path: string,
  params: Record<string, string | number | boolean | undefined>,
): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) {
      search.set(key, String(value))
    }
  }
  const query = search.toString()
  return query ? `${path}?${query}` : path
}
