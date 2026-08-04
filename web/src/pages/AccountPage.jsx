import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/core.js'
import { t } from '../keys.generated'

export default function AccountPage({ token }) {
  const [profile, setProfile] = useState({ username: '', email: '', first_name: '', last_name: '' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [ok, setOk] = useState(false)
  const navigate = useNavigate()
  useEffect(() => { (async () => {
    try {
      const me = await api('/me', { token })
      const u = me?.user || {}
      setProfile({
        username: String(u.username || ''),
        email: String(u.email || ''),
        first_name: String(u.first_name || ''),
        last_name: String(u.last_name || ''),
      })
    } catch {}
  })() }, [token])
  const save = async (e) => {
    e.preventDefault()
    setLoading(true); setError(''); setOk(false)
    try {
      await api('/me', { method: 'PATCH', token, body: profile })
      setOk(true)
    } catch (e2) {
      const code = e2?.data?.error
      const map = {
        invalid_email: 'errors.account.invalid_email',
        invalid_username: 'errors.account.invalid_username',
        username_taken: 'errors.account.username_taken',
        no_changes: 'errors.account.no_changes',
      }
      const key = map[code]
      setError(key && t(key) || t('ui.errors.save_failed'))
    } finally { setLoading(false) }
  }
  return (
    <main className="fund-account-screen">
      <section className="fund-account-card">
        <header className="fund-account-header">
          <div>
            <h2>{t('ui.account.heading')}</h2>
            <p>管理你的登录资料和联系方式。</p>
          </div>
          <button type="button" onClick={() => navigate('/')}>返回工作区</button>
        </header>
        <form className="fund-account-form" onSubmit={save}>
        <div>
          <label htmlFor="pf-username">{t('ui.account.labels.username')}</label>
          <input id="pf-username" data-testid="pf-username" value={profile.username} onChange={(e) => setProfile(p => ({ ...p, username: e.target.value }))} />
        </div>
        <div>
          <label htmlFor="pf-email">{t('ui.account.labels.email')}</label>
          <input id="pf-email" data-testid="pf-email" value={profile.email} onChange={(e) => setProfile(p => ({ ...p, email: e.target.value }))} />
        </div>
        <div>
          <label htmlFor="pf-first">{t('ui.account.labels.first_name')}</label>
          <input id="pf-first" data-testid="pf-first" value={profile.first_name} onChange={(e) => setProfile(p => ({ ...p, first_name: e.target.value }))} />
        </div>
        <div>
          <label htmlFor="pf-last">{t('ui.account.labels.last_name')}</label>
          <input id="pf-last" data-testid="pf-last" value={profile.last_name} onChange={(e) => setProfile(p => ({ ...p, last_name: e.target.value }))} />
        </div>
        <button type="submit" data-testid="pf-save" disabled={loading}>{t('ui.account.buttons.save')}</button>
        </form>
        {ok && <div className="fund-status-message is-success" data-testid="pf-ok">{t('ui.account.status.saved')}</div>}
        {error && <div className="fund-status-message is-error" role="alert">{error}</div>}
      </section>
    </main>
  )
}
