import React, { useEffect, useMemo, useState, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { api as coreApi, apiMaybeAsync as coreApiMaybeAsync, apiUpload as coreApiUpload, ROUTER_BASE as coreRouterBase } from './lib/core.js'
import './app.css'

// Inline flags fallback to avoid missing import
const flags = {
  UI_EXPERIMENTS: (import.meta.env.VITE_UI_EXPERIMENTS === '1' || import.meta.env.VITE_UI_EXPERIMENTS === 'true')
}

export function NotFound({ token }) {
  return (
    <div>
      <h1>404 — Page not found</h1>
      <p>The page you're looking for doesn't exist. It may have been moved.</p>
      <p>
        {token ? (
          <a href={`${ROUTER_BASE}`}>Go to the app</a>
        ) : (
          <a href={`${ROUTER_BASE}/login`}>Go to login</a>
        )}
        {' '}· <a href={`${ROUTER_BASE}`}>Homepage</a>
      </p>
    </div>
  )
}

// Router base is where the SPA is mounted. Default to '/app'.
const ROUTER_BASE = coreRouterBase

// Dev-time URL self-correction: ensure router base prefix exists so deep links work during dev
// Only run when dev asset base is '/'; otherwise, let host serve its own base path (e.g., '/static/app/')
// Skip during tests (jsdom doesn't implement full navigation APIs)
if (import.meta.env.DEV && import.meta.env.MODE !== 'test' && (import.meta.env.BASE_URL || '/') === '/') {
  try {
    const { origin, pathname, search, hash } = window.location
    if (pathname && !pathname.startsWith(ROUTER_BASE)) {
      const normalizedBase = ROUTER_BASE.endsWith('/') ? ROUTER_BASE.slice(0, -1) : ROUTER_BASE
      const normalizedPath = pathname.startsWith('/') ? pathname : `/${pathname}`
      const target = new URL(`${normalizedBase}${normalizedPath}${search}${hash}`, origin)
      // Same-origin only
      if (target.origin === origin) {
        window.location.replace(target.toString())
      }
    }
  } catch {}
}

// Ensure post-login destinations are internal-only
function sanitizeNext(dest) {
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

// Lazy page chunks (route-level code splitting)
const LazyAccountPage = React.lazy(() => import('./pages/AccountPage.jsx'))
const LazyProposals = React.lazy(() => import('./pages/Dashboard.jsx').then(m => ({ default: (props) => <m.Proposals {...props} /> })))
const LazyWorkspaceManager = React.lazy(() => import('./pages/OrgsPage.jsx'))

// Opportunistic idle preloads for likely-next routes (no-op in tests)
function useIdlePreloads() {
  useEffect(() => {
    if (import.meta.env.MODE === 'test') return
    const conn = (navigator && 'connection' in navigator) ? navigator.connection : null
    const saveData = conn && conn.saveData
    const slow = conn && (conn.effectiveType === '2g' || conn.effectiveType === 'slow-2g')
    if (saveData || slow) return
    const preload = () => {
      try { import('./pages/AccountPage.jsx') } catch {}
      try { import('./pages/OrgsPage.jsx') } catch {}
    }
    if ('requestIdleCallback' in window) {
      // @ts-ignore
      window.requestIdleCallback(preload, { timeout: 2000 })
    } else {
      setTimeout(preload, 500)
    }
  }, [])
}

// Optional: Web Vitals reporting in dev/experiments only
function useWebVitals() {
  useEffect(() => {
    if (import.meta.env.MODE === 'test') return
    const enable = (import.meta.env.VITE_WEB_VITALS === '1' || import.meta.env.VITE_UI_EXPERIMENTS === '1' || import.meta.env.VITE_UI_EXPERIMENTS === 'true')
    if (!enable) return
    let cancelled = false
    import('web-vitals').then((mod) => {
      if (cancelled) return
      const log = (m) => {
        try { console.info('[Vitals]', m.name, Math.round(m.value), m) } catch {}
      }
      try {
        mod.onCLS(log)
        mod.onFID(log)
        mod.onLCP(log)
        mod.onINP && mod.onINP(log)
        mod.onTTFB(log)
      } catch {}
    }).catch(() => {})
    return () => { cancelled = true }
  }, [])
}

function Umami() {
  // Inject Umami script if configured
  useEffect(() => {
    const websiteId = import.meta.env.VITE_UMAMI_WEBSITE_ID
    const src = import.meta.env.VITE_UMAMI_SRC
    if (!websiteId || !src) return
    if (document.querySelector('script[data-umami="1"]')) return
    const s = document.createElement('script')
    s.async = true
    s.src = src
    s.setAttribute('data-website-id', websiteId)
    s.setAttribute('data-umami', '1')
    document.head.appendChild(s)
  }, [])
  // Best-effort SPA pageview tracking on route changes (in addition to Umami auto-track)
  const location = useLocation()
  useEffect(() => {
    try { window.umami && typeof window.umami.track === 'function' && window.umami.track('pageview') } catch {}
  }, [location.pathname, location.search, location.hash])
  return null
}

// Global invite banner: detects ?invite= token when authenticated and offers Accept/Dismiss
export function InviteBanner({ token }) {
  const location = useLocation()
  const navigate = useNavigate()
  const [pending, setPending] = useState('')
  useEffect(() => {
    try {
      const qs = new URLSearchParams(location.search || '')
      const inv = qs.get('invite') || ''
      setPending(token ? inv : '')
    } catch {
      setPending('')
    }
  }, [location.search, token])
  const clearParam = () => {
    try {
      const qs = new URLSearchParams(location.search || '')
      qs.delete('invite')
  // Use router-native replace navigation to avoid jsdom SecurityError and honor basename
  const search = qs.toString()
  const newPath = `${location.pathname}${search ? `?${search}` : ''}${location.hash || ''}`
  navigate(newPath, { replace: true })
    } catch {}
  }
  if (!token || !pending) return null
  return (
    <div data-testid="invite-banner" role="region" aria-label="org-invite">
      <span>Organization invite detected.</span>
      <button
        type="button"
        data-testid="invite-accept"
        onClick={async () => {
          try {
            await api('/orgs/invites/accept', { method: 'POST', token, body: { token: pending } })
            // Clear from URL and local state, then navigate to app root to refresh org lists
            clearParam()
            setPending('')
            navigate('/', { replace: true })
            alert('Invite accepted')
          } catch (e) {
            alert('Invite accept failed: ' + (e?.data?.error || e.message))
          }
        }}
      >Accept invite</button>
      <button
        type="button"
        data-testid="invite-dismiss"
        onClick={() => { clearParam(); setPending('') }}
      >Not now</button>
    </div>
  )
}

function useToken() {
  const [token, setToken] = useState(() => localStorage.getItem('jwt') || '')
  useEffect(() => {
    const onRefreshed = (event) => setToken(event.detail?.access || '')
    window.addEventListener('foundationpal:token-refreshed', onRefreshed)
    return () => window.removeEventListener('foundationpal:token-refreshed', onRefreshed)
  }, [])
  const save = (t, refresh) => {
    setToken(t || '')
    if (t) {
      localStorage.setItem('jwt', t)
      if (refresh) localStorage.setItem('jwt_refresh', refresh)
    } else {
      localStorage.removeItem('jwt')
      localStorage.removeItem('jwt_refresh')
    }
  }
  return [token, save]
}

async function api(path, { method = 'GET', token, body, orgId } = {}) {
  return coreApi(path, { method, token, body, orgId })
}

async function apiMaybeAsync(path, { method = 'POST', token, body, orgId } = {}) {
  return coreApiMaybeAsync(path, { method, token, body, orgId })
}
// Simple account/profile page to edit username, email, first/last name
export function AccountPage(props) {
  return (
    <Suspense fallback={<div>Loading…</div>}>
      <LazyAccountPage {...props} />
    </Suspense>
  )
}

// Multipart upload helper for files (no JSON headers)
async function apiUpload(path, { token, orgId, file, fields = {} }) {
  return coreApiUpload(path, { token, orgId, file, fields })
}

export function LoginPage({ token, setToken }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const next = useMemo(() => new URLSearchParams(location.search).get('next') || `${ROUTER_BASE}`, [location.search])
  const safeNext = useMemo(() => sanitizeNext(next), [next])

  useEffect(() => {
    if (token) navigate(safeNext, { replace: true })
  }, [token, safeNext, navigate])

  const onLogin = async (e) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      const data = await api('/token', { method: 'POST', body: { username, password } })
      if (data.refresh) setToken(data.access, data.refresh)
      else setToken(data.access)
      try {
        const orgs = await api('/orgs/', { token: data.access })
        if (Array.isArray(orgs) && orgs.length === 0) {
          await api('/orgs/', {
            method: 'POST',
            token: data.access,
            body: {},
          })
        }
      } catch {}
      navigate(safeNext, { replace: true })
    } catch {
      setToken('')
      setError('用户名或密码错误，请重新输入')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="fund-auth-page">
      <section className="fund-auth-card">
        <div className="fund-auth-brand">NSFC</div>
        <h1>基金申请书撰写助手</h1>
        <p>登录后继续规划、写作、人工审核和定稿</p>
        <form onSubmit={onLogin} className="fund-auth-form">
          <label>
            用户名
            <input
              autoFocus
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="请输入用户名"
              required
            />
          </label>
          <label>
            密码
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="请输入密码"
              required
            />
          </label>
          {error && <div className="fund-auth-error" role="alert">{error}</div>}
          <button className="fund-primary-button" type="submit" disabled={submitting}>
            {submitting ? '正在登录' : '登录'}
          </button>
        </form>
        <button
          className="fund-auth-secondary"
          type="button"
          onClick={() => navigate(`/register?next=${encodeURIComponent(safeNext)}`)}
        >
          创建新用户
        </button>
      </section>
    </main>
  )
}

// Re-exported wrappers to keep tests working while code splits
export function Proposals(props) {
  return (
    <Suspense fallback={<div>Loading…</div>}>
      <LazyProposals {...props} />
    </Suspense>
  )
}

export function RegisterPage({ setToken }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const next = useMemo(() => new URLSearchParams(location.search).get('next') || `${ROUTER_BASE}`, [location.search])
  const safeNext = useMemo(() => sanitizeNext(next), [next])

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    if (password !== confirmPassword) {
      setError('两次输入的密码不一致')
      return
    }
    setSubmitting(true)
    try {
      const data = await api('/register', {
        method: 'POST',
        body: { username, password },
      })
      if (data.refresh) setToken(data.access, data.refresh)
      else setToken(data.access)
      if (data.org?.id) localStorage.setItem('orgId', String(data.org.id))
      navigate(safeNext, { replace: true })
    } catch (e2) {
      const code = e2?.data?.error
      if (code === 'username_taken') setError('该用户名已存在')
      else if (code === 'password_too_short') setError('密码至少需要 8 个字符')
      else setError('创建用户失败，请稍后重试')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="fund-auth-page">
      <section className="fund-auth-card">
        <div className="fund-auth-brand">NSFC</div>
        <h1>创建新用户</h1>
        <p>创建后会自动建立个人基金申请工作区</p>
        <form onSubmit={submit} className="fund-auth-form">
          <label>
            用户名
            <input
              autoFocus
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="请输入用户名"
              required
            />
          </label>
          <label>
            密码
            <input
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="至少 8 个字符"
              required
            />
          </label>
          <label>
            确认密码
            <input
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="再次输入密码"
              required
            />
          </label>
          {error && <div className="fund-auth-error" role="alert">{error}</div>}
          <button className="fund-primary-button" type="submit" disabled={submitting}>
            {submitting ? '正在创建' : '创建并登录'}
          </button>
        </form>
        <button className="fund-auth-secondary" type="button" onClick={() => navigate('/login')}>
          返回登录
        </button>
      </section>
    </main>
  )
}

// Org-required guard: ensures the user belongs to at least one organization
export function RequireOrg({ token, children }) {
  const [checking, setChecking] = useState(true)
  const [hasOrg, setHasOrg] = useState(true)
  const location = useLocation()
  const navigate = useNavigate()
  useEffect(() => {
    let ignore = false
    ;(async () => {
      setChecking(true)
      try {
        const orgs = await api('/orgs/', { token })
        if (!ignore) {
          const ok = Array.isArray(orgs) && orgs.length > 0
          setHasOrg(ok)
          if (!ok) {
            const dest = encodeURIComponent(location.pathname + location.search)
            navigate(`/register?next=${dest}`, { replace: true })
          }
        }
      } catch {
        // On error, allow through to avoid lockout; backend will enforce where needed
        if (!ignore) setHasOrg(true)
      } finally {
        if (!ignore) setChecking(false)
      }
    })()
    return () => { ignore = true }
  }, [token, location.pathname, location.search, navigate])
  if (checking) return <div>Loading…</div>
  if (!hasOrg) return null
  return children
}

// Authenticated app shell with logout
function AppShell({ token, setToken }) {
  const [activeOrgId, setActiveOrgId] = useState(() => localStorage.getItem('orgId') || '')
  const [orgs, setOrgs] = useState([])
  const [workspaceManagerOpen, setWorkspaceManagerOpen] = useState(false)
  const location = useLocation()
  useEffect(() => { if (activeOrgId) localStorage.setItem('orgId', activeOrgId); else localStorage.removeItem('orgId') }, [activeOrgId])
  const applyOrgList = (list) => {
    const nextOrgs = Array.isArray(list) ? list : []
    setOrgs(nextOrgs)
    setActiveOrgId(current => (
      nextOrgs.some(org => String(org.id) === String(current))
        ? String(current)
        : String(nextOrgs[0]?.id || '')
    ))
    return nextOrgs
  }
  const refreshOrgs = async () => applyOrgList(await api('/orgs/', { token }))
  useEffect(() => {
    refreshOrgs().catch(() => {})
  }, [token])
  const navigate = useNavigate()
  useEffect(() => {
    setWorkspaceManagerOpen(new URLSearchParams(location.search).get('dialog') === 'workspaces')
  }, [location.search])
  const openWorkspaceManager = () => {
    setWorkspaceManagerOpen(true)
    navigate('/?dialog=workspaces')
  }
  const closeWorkspaceManager = () => {
    setWorkspaceManagerOpen(false)
    navigate('/')
  }
  const logout = () => { setToken(''); navigate('/login', { replace: true }) }
  return (
    <div className="fund-app-shell">
      {flags.UI_EXPERIMENTS && (
        <div>
          UI Experiments enabled (VITE_UI_EXPERIMENTS=1)
        </div>
      )}
      <header className="fund-topbar">
        <div>
          <div className="fund-brand">NSFC 基金申请书撰写助手</div>
          <div className="fund-brand-subtitle">规划、写作、人工审核与定稿统一工作区</div>
        </div>
        <nav className="fund-topnav">
          <label>
            当前工作区
            <select aria-label="当前工作区" value={activeOrgId} onChange={(e) => setActiveOrgId(e.target.value)}>
              {orgs.map((org, index) => {
                const automaticName = `工作区 ${index + 1}`
                const customName = /^工作区\s*\d+$/.test(org.name || '') ? '' : org.name
                return (
                  <option key={org.id} value={String(org.id)}>
                    {automaticName}{customName ? `：${customName}` : ''}
                  </option>
                )
              })}
            </select>
          </label>
          <button onClick={() => navigate('/account')}>账户</button>
          <button onClick={openWorkspaceManager}>工作区管理</button>
          <button onClick={logout}>退出</button>
        </nav>
      </header>
      <div className="fund-app-content">
        <Suspense fallback={<div className="fund-loading">正在加载基金工作区</div>}>
          <LazyProposals token={token} selectedOrgId={activeOrgId} />
        </Suspense>
      </div>
      {workspaceManagerOpen && (
        <Suspense fallback={null}>
          <LazyWorkspaceManager
            token={token}
            activeOrgId={activeOrgId}
            onSelectOrg={setActiveOrgId}
            onOrgsChanged={applyOrgList}
            onClose={closeWorkspaceManager}
          />
        </Suspense>
      )}
    </div>
  )
}

// Route guard
// Named export used only in tests; runtime uses the same function below
export function RequireAuth({ token, children }) {
  const location = useLocation()
  if (!token) {
    const next = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/login?next=${next}`} replace />
  }
  return children
}

function Root() {
  const [token, setToken] = useToken()
  useIdlePreloads()
  useWebVitals()
  return (
    <BrowserRouter basename={ROUTER_BASE}>
      <Umami />
  <InviteBanner token={token} />
      <Routes>
        <Route path="/login" element={<LoginPage token={token} setToken={setToken} />} />
        <Route path="/register" element={<RegisterPage setToken={setToken} />} />
        <Route
          path="/account"
          element={
            <RequireAuth token={token}>
              <AccountPage token={token} />
            </RequireAuth>
          }
        />
        <Route
          path="/orgs"
          element={
            <RequireAuth token={token}>
              <Navigate to="/?dialog=workspaces" replace />
            </RequireAuth>
          }
        />
        <Route path="/404" element={<NotFound token={token} />} />
        <Route
          path="*"
          element={
            <RequireAuth token={token}>
              <RequireOrg token={token}>
                <AppShell token={token} setToken={setToken} />
              </RequireOrg>
            </RequireAuth>
          }
        />
      </Routes>
    </BrowserRouter>
  )
}

const mountEl = (typeof document !== 'undefined') ? document.getElementById('root') : null
if (mountEl) {
  const root = createRoot(mountEl)
  root.render(<Root />)
}
