import { useEffect, useState } from 'react'
import { api } from '../lib/core.js'

const MODES = [['polish_existing', '润色已有文本'], ['refine_outline', '完善已有思路'], ['plan_from_scratch', '从头规划并起草']]
const QUALITIES = [['quick', '快速成稿'], ['standard', '标准完善'], ['deep', '深度打磨']]

export function Phase12Workspace({ proposal, token, orgId }) {
  const key = `phase12:intake:${proposal.id}`
  const [mode, setMode] = useState('plan_from_scratch')
  const [quality, setQuality] = useState('standard')
  const [packId, setPackId] = useState('')
  const [sessionId, setSessionId] = useState(() => localStorage.getItem(key) || '')
  const [state, setState] = useState(null)
  const [answer, setAnswer] = useState('')
  const [pack, setPack] = useState(null)
  const [draftResourceIds, setDraftResourceIds] = useState('')
  const [evidence, setEvidence] = useState(null)
  const [error, setError] = useState('')
  const opts = { token, orgId: orgId || undefined }

  useEffect(() => {
    if (sessionId) api(`/ai/intake?session_id=${sessionId}`, opts).then(setState).catch(() => { localStorage.removeItem(key); setSessionId('') })
    api(`/ai/proposals/${proposal.id}/evidence-review`, opts).then(setEvidence).catch(() => {})
  }, [proposal.id, sessionId, token, orgId])

  const start = async () => {
    try {
      const data = await api('/ai/intake', { ...opts, method: 'POST', body: { proposal_id: proposal.id, task_mode: mode, quality_level: quality, inputs: packId ? { pack_version_id: Number(packId) } : {} } })
      localStorage.setItem(key, String(data.session_id)); setSessionId(String(data.session_id)); setState(data)
    } catch (e) { setError(e?.data?.error || e.message) }
  }
  const reply = async action => {
    const card = state?.question_card
    if (!card) return
    try {
      const data = await api('/ai/intake/grill', { ...opts, method: 'POST', body: { session_id: Number(sessionId), node_id: card.node_id, action, answer, idempotency_key: `${card.node_id}:${action}:${answer}` } })
      setAnswer(''); setState(previous => ({ ...previous, status: data.status, question_card: data.question_card, consensus_summary: data.consensus_summary }))
    } catch (e) { setError(e?.data?.error || e.message) }
  }
  const confirm = async () => {
    try { const data = await api('/ai/intake/consensus', { ...opts, method: 'POST', body: { session_id: Number(sessionId), confirm: true } }); setState(previous => ({ ...previous, consensus_summary: data })) } catch (e) { setError(e?.data?.error || e.message) }
  }
  const loadPack = async () => { try { setPack(await api(`/ai/grant-packs/${packId}/review`, opts)) } catch (e) { setError(e?.data?.error || e.message) } }
  const createPackDraft = async () => {
    try {
      const resource_ids = draftResourceIds.split(',').map(value => Number(value.trim())).filter(Boolean)
      const data = await api(`/ai/proposals/${proposal.id}/rule-pack-drafts`, { ...opts, method: 'POST', body: { resource_ids, name: '自定义基金规则包' } })
      setPackId(String(data.pack_version_id)); setPack(null)
    } catch (e) { setError(e?.data?.error || e.message) }
  }
  const verify = async (factId, verificationStatus) => {
    try { setEvidence(await api(`/ai/proposals/${proposal.id}/evidence-review`, { ...opts, method: 'POST', body: { action: 'verify_fact', fact_id: factId, verification_status: verificationStatus } })) } catch (e) { setError(e?.data?.error || e.message) }
  }
  const card = state?.question_card
  return <section style={{ marginBottom: 16, padding: 16, border: '1px solid #cbd5e1', borderRadius: 8 }} data-testid="phase12-workspace">
    <h3>项目向导与人工确认</h3>
    {!sessionId && <div><label>当前任务 <select value={mode} onChange={e => setMode(e.target.value)}>{MODES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label><label> 交付深度 <select value={quality} onChange={e => setQuality(e.target.value)}>{QUALITIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label><label> 已发布规则包版本编号，可选 <input value={packId} onChange={e => setPackId(e.target.value)} /></label><button onClick={start}>保存目标并评估</button></div>}
    {state?.work_plan_preview && <details open><summary>系统评估与工作方案</summary><pre>{JSON.stringify(state.work_plan_preview, null, 2)}</pre><p>用户只确认高层目标，系统不开放底层 Graph 参数。</p></details>}
    {proposal?.content?.meta?.intake_snapshot && <details><summary>当前规则包与材料快照</summary><pre>{JSON.stringify(proposal.content.meta.intake_snapshot, null, 2)}</pre></details>}
    {card && <div><h4>当前需要确认的决策</h4><p>{card.question}</p><p>推荐：{card.recommended_answer || '暂无推荐'}</p><p>{card.recommendation_reason}</p><p>阻断项：{card.blocking ? '是' : '否'}，受影响章节：{(card.affected_sections || []).join('、') || '待规划'}</p><textarea value={answer} onChange={e => setAnswer(e.target.value)} rows={3} style={{ width: '100%' }} /><div><button onClick={() => reply('adopt_recommendation')}>采用推荐</button><button onClick={() => reply('modify_and_adopt')}>修改后采用</button><button onClick={() => reply('custom')}>自行回答</button><button onClick={() => reply('skip')}>暂时跳过</button><button onClick={() => reply('end')}>结束追问并继续</button></div></div>}
    {state?.consensus_summary && <details open><summary>项目共识与剩余缺口</summary><pre>{JSON.stringify(state.consensus_summary, null, 2)}</pre><button onClick={confirm}>确认 ProposalBrief 并进入 Claim 规划</button></details>}
    <details><summary>规则包审核</summary><p>草稿、过期或未发布规则包不能直接使用。</p><label>新规则材料资源编号，以逗号分隔 <input value={draftResourceIds} onChange={e => setDraftResourceIds(e.target.value)} /></label><button disabled={!draftResourceIds} onClick={createPackDraft}>创建自定义规则包草稿</button><button disabled={!packId} onClick={loadPack}>载入审核结果</button>{pack && <div><p>状态：{pack.status}，未审核文件：{pack.unreviewed_document_count}</p>{pack.requirements.map(item => <details key={item.id}><summary>{item.mandatory ? '必填' : '非必填'} {item.text}</summary><p>{item.source_excerpt}</p></details>)}</div>}</details>
    <details><summary>用户资料审核</summary>{evidence?.evidence?.flatMap(item => item.facts).map(fact => <div key={fact.id}><strong>{fact.subject} {fact.predicate} {fact.object}</strong>，角色：{fact.user_role}，核验：{fact.verification_status}<button onClick={() => verify(fact.id, 'user_confirmed')}>确认</button><button onClick={() => verify(fact.id, 'rejected')}>拒绝</button></div>) || <p>暂无绑定到当前项目的可审核用户资料。</p>}</details>
    {error && <p role="alert">{error}</p>}
  </section>
}
