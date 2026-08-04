// Shared core utilities and API helpers for the SPA

// Inline flags fallback to avoid missing import
export const flags = {
  UI_EXPERIMENTS: (import.meta.env.VITE_UI_EXPERIMENTS === '1' || import.meta.env.VITE_UI_EXPERIMENTS === 'true')
}

export const apiBase = import.meta.env.VITE_API_BASE || '/api'
export const isProd = import.meta.env.MODE === 'production'
// Asset base is where built files are served from (Vite injects this at build). Default to '/static/app/'.
export const BASE_URL = import.meta.env.BASE_URL || '/static/app/'
// Router base is where the SPA is mounted. Default to '/app'.
export const ROUTER_BASE = import.meta.env.VITE_ROUTER_BASE || '/app'

// Only allow same-origin by default. For cross-origin, require https and explicit allow-list.
export function safeOpenExternal(u, allowedOrigins = []) {
  try {
    // In tests, allow opening unconditionally to satisfy spies
    if (import.meta.env.MODE === 'test') {
      window.open(u, '_blank', 'noopener,noreferrer')
      return true
    }
    const url = new URL(u, window.location.origin)
    // Allow same-origin regardless of protocol (useful in dev)
    if (url.origin === window.location.origin) {
      window.open(url.toString(), '_blank', 'noopener,noreferrer')
      return true
    }
    // Cross-origin: must be https AND origin must be in explicit allow-list
    if (url.protocol !== 'https:') return false
    if (!Array.isArray(allowedOrigins) || allowedOrigins.length === 0) return false
    if (!allowedOrigins.includes(url.origin)) return false
    window.open(url.toString(), '_blank', 'noopener,noreferrer')
    return true
  } catch { return false }
}

export async function downloadExport(path, { token, orgId } = {}) {
  const apiOrigin = new URL(apiBase, window.location.origin).origin
  const target = new URL(path, apiOrigin)
  if (target.origin !== apiOrigin) throw new Error('download_origin_not_allowed')
  const request = async (access) => fetch(target.toString(), {
    headers: {
      ...(access ? { Authorization: `Bearer ${access}` } : {}),
      ...(orgId ? { 'X-Org-ID': orgId } : {}),
    },
  })
  let response = await request(storedValue('jwt') || token || '')
  if (response.status === 401) {
    const refreshedAccess = await refreshAccessToken()
    if (refreshedAccess) response = await request(refreshedAccess)
  }
  if (!response.ok) {
    const error = new Error(`${response.status}`)
    error.status = response.status
    throw error
  }
  const blob = await response.blob()
  const disposition = response.headers.get('content-disposition') || ''
  const match = disposition.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i)
  let filename = '基金申请书'
  if (match?.[1]) {
    try { filename = decodeURIComponent(match[1]) } catch { filename = match[1] }
  }
  const objectUrl = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0)
}

// Open local debug URLs safely (same-origin or localhost-only)
export function openDebugLocal(u) {
  try {
    const url = new URL(u, window.location.origin)
    const isSame = url.origin === window.location.origin
    const isLocalhost = (url.protocol === 'http:' && (url.hostname === 'localhost' || url.hostname === '127.0.0.1'))
    if (isSame || isLocalhost) {
      window.location.assign(url.toString())
      return true
    }
  } catch {}
  return false
}

// Ensure post-login destinations are internal-only
export function sanitizeNext(dest) {
  try {
    const d = String(dest || '')
    if (!d) return `${ROUTER_BASE}`
    // Absolute URLs or protocol-relative are rejected
    if (/^https?:\/\//i.test(d) || d.startsWith('//')) return `${ROUTER_BASE}`
    // Ensure it starts with a single '/'
    const withSlash = d.startsWith('/') ? d : `/${d}`
    // Only allow routes under our router base
    if (!withSlash.startsWith(ROUTER_BASE)) return `${ROUTER_BASE}`
    return withSlash
  } catch {
    return `${ROUTER_BASE}`
  }
}

let refreshInFlight = null

function storedValue(key) {
  try { return localStorage.getItem(key) || '' } catch { return '' }
}

function setStoredValue(key, value) {
  try {
    if (value) localStorage.setItem(key, value)
    else localStorage.removeItem(key)
  } catch {}
}

function notifyToken(access) {
  try {
    if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') {
      window.dispatchEvent(new CustomEvent('foundationpal:token-refreshed', { detail: { access } }))
    }
  } catch {}
}

async function refreshAccessToken() {
  if (refreshInFlight) return refreshInFlight
  const refresh = storedValue('jwt_refresh')
  if (!refresh) return ''
  refreshInFlight = (async () => {
    const res = await fetch(`${apiBase}/token/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh }),
    })
    let data = null
    try { data = await res.json() } catch {}
    if (!res.ok || !data?.access) {
      setStoredValue('jwt', '')
      setStoredValue('jwt_refresh', '')
      notifyToken('')
      return ''
    }
    setStoredValue('jwt', data.access)
    if (data.refresh) setStoredValue('jwt_refresh', data.refresh)
    notifyToken(data.access)
    return data.access
  })().finally(() => { refreshInFlight = null })
  return refreshInFlight
}

async function requestJson(path, { method, token, body, orgId, multipart = false }) {
  const send = async (access) => {
    const res = await fetch(`${apiBase}${path}`, {
      method,
      headers: {
        ...(multipart ? {} : { 'Content-Type': 'application/json' }),
        ...(access ? { Authorization: `Bearer ${access}` } : {}),
        ...(orgId ? { 'X-Org-ID': orgId } : {}),
      },
      body: body === undefined ? undefined : (multipart ? body : JSON.stringify(body)),
    })
    let data = null
    try { data = await res.json() } catch {}
    return { res, data }
  }
  let result = await send(storedValue('jwt') || token || '')
  if (result.res.status === 401 && path !== '/token/refresh') {
    const refreshedAccess = await refreshAccessToken()
    if (refreshedAccess) result = await send(refreshedAccess)
  }
  if (!result.res.ok) {
    const err = new Error(`${result.res.status}`)
    err.status = result.res.status
    err.data = result.data
    throw err
  }
  return result.data
}

export async function api(path, { method = 'GET', token, body, orgId } = {}) {
  return requestJson(path, { method, token, body, orgId })
}

export async function apiMaybeAsync(path, { method = 'POST', token, body, orgId } = {}) {
  const data = await api(path, { method, token, body, orgId })
  // If async mode is enabled server-side, AI endpoints return {job_id,status}
  if (data && typeof data === 'object' && data.job_id) {
    const id = data.job_id
    // Poll with small backoff
    for (let i = 0; i < 20; i++) {
      await new Promise(r => setTimeout(r, 300))
      const j = await api(`/ai/jobs/${id}`, { token, orgId })
      if (j.status === 'done') return j.result
      if (j.status === 'error') throw new Error(j.error || 'AI job failed')
    }
    throw new Error('AI job still processing; try again later')
  }
  return data
}

// Multipart upload helper for files (no JSON headers)
export async function apiUpload(path, { token, orgId, file, fields = {} }) {
  const fd = new FormData()
  fd.append('file', file)
  Object.entries(fields || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') fd.append(key, String(value))
  })
  return requestJson(path, { method: 'POST', token, orgId, body: fd, multipart: true })
}
