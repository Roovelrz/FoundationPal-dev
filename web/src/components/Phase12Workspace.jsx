import { useEffect, useRef, useState } from 'react'
import { api, apiUpload } from '../lib/core.js'

function messageFor(error) {
  if (error?.status === 401) return '登录状态已失效，请重新登录后再试。'
  if (error?.status === 403) return '你没有操作当前项目的权限。'
  return error?.data?.message || error?.data?.error || '操作失败，请稍后重试。'
}

export function Phase12Workspace({ proposal, token, orgId, onReady, onContinue }) {
  const [setup, setSetup] = useState(null)
  const [researchDirection, setResearchDirection] = useState('')
  const [coreProblem, setCoreProblem] = useState('')
  const [guidelineText, setGuidelineText] = useState('')
  const [busy, setBusy] = useState(false)
  const [busyMessage, setBusyMessage] = useState('')
  const [error, setError] = useState('')
  const activeProposalIdRef = useRef(String(proposal.id))
  const hasUnsavedFieldsRef = useRef(false)
  const opts = { token, orgId: orgId || undefined }

  const load = async ({ hydrate = false } = {}) => {
    const proposalId = String(proposal.id)
    const next = await api(`/ai/proposals/${proposal.id}/setup`, opts)
    if (activeProposalIdRef.current !== proposalId) return next
    setSetup(next)
    if (hydrate && !hasUnsavedFieldsRef.current) {
      setResearchDirection(next.research_direction || '')
      setCoreProblem(next.core_problem || '')
      setGuidelineText(next.guideline_text || '')
    }
    return next
  }

  useEffect(() => {
    let disposed = false
    activeProposalIdRef.current = String(proposal.id)
    hasUnsavedFieldsRef.current = false
    setSetup(null)
    setError('')
    setGuidelineText('')
    load({ hydrate: true }).catch(requestError => {
      if (!disposed) setError(messageFor(requestError))
    })
    return () => { disposed = true }
  }, [proposal.id, token, orgId])

  const uploadMaterial = async (event, materialKind) => {
    const file = event.target.files?.[0]
    if (!file) return
    setBusy(true)
    setBusyMessage(materialKind === 'guideline' ? '正在上传基金指南文件。' : '正在上传用户补充材料。')
    setError('')
    try {
      await apiUpload('/files', {
        ...opts,
        file,
        fields: { proposal_id: proposal.id, material_kind: materialKind },
      })
      await load()
      event.target.value = ''
    } catch (requestError) {
      setError(messageFor(requestError))
    } finally {
      setBusy(false)
      setBusyMessage('')
    }
  }

  const saveSetup = async () => {
    if (!researchDirection.trim()) {
      setError('请填写带红色星号的必填内容。')
      return
    }
    if (!guidelineText.trim() && !setup?.guideline_ready) {
      setError('请粘贴基金指南或上传一份可解析的指南文件。')
      return
    }
    setBusy(true)
    setBusyMessage('正在保存基础信息。')
    setError('')
    try {
      const next = await api(`/ai/proposals/${proposal.id}/setup`, {
        ...opts,
        method: 'POST',
        body: {
          research_direction: researchDirection.trim(),
          core_problem: coreProblem.trim(),
          guideline_text: guidelineText.trim(),
        },
      })
      setSetup(next)
      setGuidelineText(next.guideline_text || guidelineText.trim())
      hasUnsavedFieldsRef.current = false
      onReady?.(next)
    } catch (requestError) {
      setError(messageFor(requestError))
    } finally {
      setBusy(false)
      setBusyMessage('')
    }
  }

  return (
    <section className="fund-project-setup" data-testid="project-setup">
      <header className="fund-project-setup-header">
        <div>
          <h3>项目基础信息</h3>
          <p>完成必要信息后，系统会依据你的指南和材料生成章节规划与草稿。</p>
        </div>
        {setup?.ready && <span className="fund-setup-ready">已完成</span>}
      </header>

      <div className="fund-project-setup-fields">
        <label>
          <span>研究方向 <b className="fund-required-marker" aria-hidden="true">*</b></span>
          <small className="fund-field-hint">本项为必填。提供明确的研究方向、研究对象和拟解决问题等信息，有助于系统生成更贴合的章节规划。该部分不建议留空。</small>
          <textarea
            aria-label="研究方向与核心问题"
            value={researchDirection}
            onChange={event => {
              hasUnsavedFieldsRef.current = true
              setResearchDirection(event.target.value)
            }}
            rows={4}
            placeholder="请描述您的研究方向、研究对象和拟解决问题"
            required
          />
        </label>

        <label>
          <span>深化描述核心科学问题</span>
          <small className="fund-field-hint">可补充研究目标、技术路线或创新侧重点；暂无补充时可留空。</small>
          <textarea
            aria-label="深化描述核心科学问题"
            value={coreProblem}
            onChange={event => {
              hasUnsavedFieldsRef.current = true
              setCoreProblem(event.target.value)
            }}
            rows={3}
            placeholder="可补充研究目标、技术路线或创新侧重点"
          />
        </label>

        <label>
          <span>基金指南或申报要求 <b className="fund-required-marker" aria-hidden="true">*</b></span>
              <small className="fund-field-hint">提供清晰的基金指南或申报要求，有助于提升申报书质量。可填写文本或上传可解析的指南文件，任选其一即可。本项为必填；若暂无相关材料，可如实填写：不清楚。</small>
          <textarea
            aria-label="基金指南或申报要求"
            value={guidelineText}
            onChange={event => {
              hasUnsavedFieldsRef.current = true
              setGuidelineText(event.target.value)
            }}
            rows={5}
                placeholder="粘贴与本项目相关的指南、通知或申报要求；提供清晰的指南和要求有助于提升申报书质量，若暂无材料可填写：不清楚"
            required={!setup?.guideline_ready}
          />
        </label>

        <div className="fund-project-material-row">
          <div>
            <span>上传基金指南文件，可用于完成上方必填项</span>
            <input id={`guideline-file-${proposal.id}`} data-testid="guideline-file-input" className="fund-file-input" type="file" accept=".pdf,.docx,.txt" onChange={event => uploadMaterial(event, 'guideline')} disabled={busy} />
            <label className="fund-file-picker" htmlFor={`guideline-file-${proposal.id}`}>选择文件并上传</label>
          </div>
          <span>{setup?.guideline_ready ? `已准备 ${setup.guideline_count} 份指南材料` : '可上传 PDF、DOCX 或文本文件，也可直接填写上方内容'}</span>
        </div>
        {(setup?.guideline_files || []).length > 0 && (
          <ul className="fund-material-list" aria-label="已上传指南材料">
            {setup.guideline_files.map(file => <li key={file.id}>{file.name}</li>)}
          </ul>
        )}

        <div className="fund-project-material-row">
          <div>
            <span>上传用户补充材料，可选</span>
            <input id={`evidence-file-${proposal.id}`} data-testid="evidence-file-input" className="fund-file-input" type="file" accept=".pdf,.docx,.txt" onChange={event => uploadMaterial(event, 'evidence')} disabled={busy} />
            <label className="fund-file-picker" htmlFor={`evidence-file-${proposal.id}`}>选择文件并上传</label>
          </div>
          <span>{setup?.evidence_count ? `已准备 ${setup.evidence_count} 份用户材料` : '可补充成果、前期基础、技术方案或数据说明；暂无材料可稍后上传'}</span>
        </div>
        {(setup?.evidence_files || []).length > 0 && (
          <ul className="fund-material-list" aria-label="已上传用户材料">
            {setup.evidence_files.map(file => <li key={file.id}>{file.name}</li>)}
          </ul>
        )}
      </div>

      <div className="fund-project-setup-actions">
        <button className="fund-primary-button" type="button" onClick={saveSetup} disabled={busy}>
          {busy ? <><span className="fund-spinner" aria-hidden="true" />正在处理</> : '保存基础信息并继续'}
        </button>
        <span>带 <b className="fund-required-marker" aria-hidden="true">*</b> 的内容必须填写。基金指南可通过填写文本或上传可解析文件完成。</span>
      </div>
      {busy && busyMessage && (
        <p className="fund-api-action-feedback" role="status">
          <span className="fund-spinner" aria-hidden="true" />
          {busyMessage}
        </p>
      )}
      {setup?.ready && (
        <div className="fund-next-step-guide">
          <strong>下一步：进入下方基金申请书工作区</strong>
          <span>确认写作目标后，即可生成章节规划。</span>
          <button type="button" onClick={onContinue}>前往章节规划</button>
        </div>
      )}
      {error && <p className="fund-status-message is-error" role="alert">{error}</p>}
    </section>
  )
}
