import { useEffect, useState } from 'react'
import { api } from '../lib/core.js'

function workspaceLabel(org, index) {
  const defaultName = /^工作区\s*\d+$/.test(org.name || '')
  return `工作区 ${index + 1}${defaultName || !org.name ? '' : `：${org.name}`}`
}

function errorMessage(error) {
  if (error?.status === 401) return '登录状态已失效，请重新登录后再试。'
  if (error?.status === 403) return '你没有操作该工作区的权限。'
  if (error?.status === 409 && error?.data?.error === 'workspace_has_projects') {
    return `该工作区仍有 ${error.data.proposal_count || 0} 个项目，无法删除。`
  }
  return `操作失败：${error?.data?.error || error?.message || '请稍后重试'}`
}

export default function OrgsPage({ token, activeOrgId, onSelectOrg, onOrgsChanged, onClose }) {
  const [items, setItems] = useState([])
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [selectedId, setSelectedId] = useState('')
  const [membersByOrg, setMembersByOrg] = useState({})
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const refresh = async () => {
    const next = await api('/orgs/', { token })
    const list = Array.isArray(next) ? next : []
    setItems(list)
    onOrgsChanged?.(list)
    return list
  }

  const loadMembers = async (orgId) => {
    try {
      const members = await api(`/orgs/${orgId}/members/`, { token })
      setMembersByOrg(previous => ({ ...previous, [orgId]: members }))
    } catch (requestError) {
      setError(errorMessage(requestError))
    }
  }

  useEffect(() => {
    refresh().catch(requestError => setError(errorMessage(requestError)))
  }, [token])

  const createWorkspace = async () => {
    setBusy(true)
    setError('')
    try {
      const created = await api('/orgs/', {
        method: 'POST',
        token,
        body: { name: name.trim(), description: description.trim() },
      })
      setName('')
      setDescription('')
      await refresh()
      if (created?.id) onSelectOrg?.(String(created.id))
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setBusy(false)
    }
  }

  const confirmDelete = async () => {
    if (!deleteTarget) return
    setBusy(true)
    setError('')
    try {
      await api(`/orgs/${deleteTarget.id}/`, { method: 'DELETE', token })
      const next = await refresh()
      if (String(activeOrgId) === String(deleteTarget.id)) {
        onSelectOrg?.(String(next[0]?.id || ''))
      }
      setSelectedId('')
      setDeleteTarget(null)
    } catch (requestError) {
      setError(errorMessage(requestError))
      setDeleteTarget(null)
    } finally {
      setBusy(false)
    }
  }

  const toggleMembers = (orgId) => {
    const nextId = String(orgId)
    const open = selectedId === nextId
    setSelectedId(open ? '' : nextId)
    if (!open) loadMembers(orgId)
  }

  return (
    <div className="fund-dialog-backdrop" role="presentation" onMouseDown={event => {
      if (event.target === event.currentTarget && !busy) onClose?.()
    }}>
      <section className="fund-dialog" role="dialog" aria-modal="true" aria-labelledby="workspace-manager-title">
        <header className="fund-dialog-header">
          <div>
            <h2 id="workspace-manager-title">工作区管理</h2>
            <p>创建、切换和管理你的工作区。</p>
          </div>
          <button type="button" aria-label="关闭工作区管理" onClick={onClose} disabled={busy}>关闭</button>
        </header>

        <div className="fund-dialog-create">
          <label>
            工作区名称
            <input placeholder="例如：国自然" value={name} onChange={event => setName(event.target.value)} />
          </label>
          <label>
            说明
            <input placeholder="可选" value={description} onChange={event => setDescription(event.target.value)} />
          </label>
          <button type="button" className="fund-primary-button" onClick={createWorkspace} disabled={busy}>
            新建工作区
          </button>
        </div>

        <div className="fund-workspace-list">
          {items.map((org, index) => {
            const selected = selectedId === String(org.id)
            const active = String(activeOrgId) === String(org.id)
            return (
              <article className={`fund-workspace-item ${active ? 'is-active' : ''}`} key={org.id}>
                <div className="fund-workspace-item-main">
                  <div>
                    <strong>{workspaceLabel(org, index)}</strong>
                    {org.description && <p>{org.description}</p>}
                  </div>
                  <div className="fund-workspace-item-actions">
                    {!active && <button type="button" onClick={() => onSelectOrg?.(String(org.id))}>切换到此工作区</button>}
                    {active && <span className="fund-current-workspace">当前工作区</span>}
                    <button type="button" onClick={() => toggleMembers(org.id)}>成员</button>
                    <button type="button" className="fund-danger-button" onClick={() => setDeleteTarget(org)}>删除</button>
                  </div>
                </div>
                {selected && (
                  <div className="fund-members-panel">
                    <h3>成员</h3>
                    {(membersByOrg[org.id] || []).length === 0 ? (
                      <p>暂时没有其他成员。</p>
                    ) : (
                      <ul>
                        {(membersByOrg[org.id] || []).map(member => (
                          <li key={member.user.id}>{member.user.username}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </article>
            )
          })}
        </div>

        {error && <p className="fund-status-message is-error" role="alert">{error}</p>}
      </section>

      {deleteTarget && (
        <div className="fund-confirm-backdrop" role="presentation">
          <section className="fund-confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="delete-workspace-title">
            <h2 id="delete-workspace-title">确认删除工作区</h2>
            <p>确定删除 {workspaceLabel(deleteTarget, Math.max(items.findIndex(item => item.id === deleteTarget.id), 0))} 吗？</p>
            <p>删除后无法恢复。含有项目的工作区不能删除。</p>
            <div className="fund-dialog-actions">
              <button type="button" onClick={() => setDeleteTarget(null)} disabled={busy}>取消</button>
              <button type="button" className="fund-danger-button" onClick={confirmDelete} disabled={busy}>确认删除</button>
            </div>
          </section>
        </div>
      )}
    </div>
  )
}
