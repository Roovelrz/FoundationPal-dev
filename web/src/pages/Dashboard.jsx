import { useEffect, useRef, useState } from 'react'
import { api, apiMaybeAsync, apiUpload, downloadExport, safeOpenExternal } from '../lib/core.js'
import { t } from '../keys.generated'
import { Phase12Workspace } from '../components/Phase12Workspace.jsx'

const normalizePlan = (raw) => ({
  schema_version: raw?.schema_version || 'v1',
  sections: (raw?.sections || []).map(section => ({
    ...section,
    id: section.id || section.key,
    inputs: (section.inputs || section.questions || []).slice(0, 20),
  })),
})

const APPLICATION_SYSTEM_OPTIONS = [
  { value: 'nsfc', label: '国自然' },
  { value: 'provincial', label: '省基金' },
  { value: 'university', label: '校级项目' },
  { value: 'other', label: '其他项目' },
]

const applicationSystemLabel = (value) => (
  APPLICATION_SYSTEM_OPTIONS.find(option => option.value === value)?.label || '未设置'
)

const planFromProposal = (proposal) => {
  if (!proposal?.sections?.length) return null
  return normalizePlan({
    schema_version: proposal.schema_version,
    sections: proposal.sections.map(section => ({
      id: section.key,
      title: section.title,
      inputs: section.inputs || section.questions || [],
    })),
  })
}

const planningFieldLabels = {
  funding_category: '申报类别',
  research_direction: '研究方向',
  core_problem: '核心科学问题',
  research_foundation: '已有研究基础',
  available_equipment: '可用设备',
  project_duration: '计划周期',
  budget_range: '预算范围',
  expected_outcomes: '预期成果',
  prohibited_content: '不得生成的内容',
}

function MarkdownPreview({ value, testId }) {
  const renderInline = (line) => line.split(/(\*\*.*?\*\*)/g).map((part, index) => (
    part.startsWith('**') && part.endsWith('**')
      ? <strong key={index}>{part.slice(2, -2)}</strong>
      : part
  ))
  return (
    <div
      data-testid={testId}
      className="fund-markdown-preview"
    >
      {value ? value.split('\n').map((line, index) => {
        if (line.startsWith('### ')) return <h3 key={index}>{renderInline(line.slice(4))}</h3>
        if (line.startsWith('## ')) return <h2 key={index}>{renderInline(line.slice(3))}</h2>
        if (line.startsWith('# ')) return <h1 key={index}>{renderInline(line.slice(2))}</h1>
        if (line.startsWith('- ')) return <div key={index}>• {renderInline(line.slice(2))}</div>
        if (!line.trim()) return <div key={index} style={{ height: 8 }} />
        return <p key={index}>{renderInline(line)}</p>
      }) : <span className="fund-markdown-empty">暂无内容</span>}
    </div>
  )
}

function FullDraftPreview({ value, sections, onSectionClick, disabled = false }) {
  const renderInline = (line) => line.split(/(\*\*.*?\*\*)/g).map((part, index) => (
    part.startsWith('**') && part.endsWith('**')
      ? <strong key={index}>{part.slice(2, -2)}</strong>
      : part
  ))
  const sectionForHeading = (heading) => sections.find(section => {
    const title = String(section.title || section.id || '').trim()
    return title && (heading === title || heading.includes(title))
  })
  return (
    <div className='fund-markdown-preview fund-full-draft-preview' data-testid='full-draft-preview'>
      {value ? value.split('\n').map((line, index) => {
        if (line.startsWith('## ')) {
          const heading = line.slice(3).trim()
          const section = sectionForHeading(heading)
          if (section) {
            return (
              <button
                className='fund-full-draft-section-link'
                type='button'
                key={index}
                onClick={() => onSectionClick(section)}
                disabled={disabled}
              >
                {renderInline(heading)}
              </button>
            )
          }
          return <h2 key={index}>{renderInline(heading)}</h2>
        }
        if (line.startsWith('### ')) return <h3 key={index}>{renderInline(line.slice(4))}</h3>
        if (line.startsWith('# ')) return <h1 key={index}>{renderInline(line.slice(2))}</h1>
        if (line.startsWith('- ')) return <div key={index}>• {renderInline(line.slice(2))}</div>
        if (!line.trim()) return <div key={index} style={{ height: 8 }} />
        return <p key={index}>{renderInline(line)}</p>
      }) : <span className='fund-markdown-empty'>暂无内容</span>}
    </div>
  )
}

function GenerationFeedback({ action, status, sectionId = '', hideDone = false }) {
  if (status.action !== action || (sectionId && status.sectionId !== sectionId)) return null
  if (status.state === 'loading') {
    return (
      <span className="fund-generation-feedback" role="status">
        <span className="fund-spinner" aria-hidden="true" />
        {status.message || '深度思考中，请稍候'}
      </span>
    )
  }
  if (status.state === 'done') {
    if (hideDone) return null
    return <span className="fund-generation-feedback is-done" role="status">内容生成完毕！</span>
  }
  return null
}

function EvidencePanel({ evidence }) {
  if (!evidence?.length) return null
  return (
    <section className="fund-evidence-panel" aria-label="章节证据">
      <h4>本章节检索证据</h4>
      {evidence.map(item => (
        <details key={`${item.chunk_id}-${item.rank}`}>
          <summary>
            {item.cited_by_model ? '已引用' : '已注入'}  {item.document_name}
            {item.is_uploaded_material && item.page_start ? `  第 ${item.page_start}-${item.page_end || item.page_start} 页` : ''}
          </summary>
          <p>{item.section_title || '证据片段'}</p>
          <p>{item.text}</p>
        </details>
      ))}
    </section>
  )
}

function UserIntentPanel({ taskMode, qualityLevel, onTaskModeChange, onQualityLevelChange, onConfirm, confirmed, loading }) {
  return (
    <section className="fund-user-intent-panel">
      <h4>先确认你的写作目标</h4>
      <p className="fund-field-hint">两项均为必填，用于确定起草方式和打磨深度。</p>
      <fieldset>
        <legend>你现在希望系统做什么 <b className="fund-required-marker" aria-hidden="true">*</b></legend>
        <p className="fund-field-hint">本项为必填。请选择最符合当前情况的写作目标，系统会据此安排工作流程。</p>
        <label><input type="radio" name="task-mode" value="polish_existing" checked={taskMode === 'polish_existing'} onChange={(event) => onTaskModeChange(event.target.value)} />润色已有文本</label>
        <label><input type="radio" name="task-mode" value="refine_outline" checked={taskMode === 'refine_outline'} onChange={(event) => onTaskModeChange(event.target.value)} />完善已有思路</label>
        <label><input type="radio" name="task-mode" value="plan_from_scratch" checked={taskMode === 'plan_from_scratch'} onChange={(event) => onTaskModeChange(event.target.value)} />从头规划并起草</label>
      </fieldset>
      <fieldset>
        <legend>你希望做到什么程度 <b className="fund-required-marker" aria-hidden="true">*</b></legend>
        <p className="fund-field-hint">本项为必填。请选择期望的完善程度，系统会据此调整生成与修订的侧重点。</p>
        <label><input type="radio" name="quality-level" value="quick" checked={qualityLevel === 'quick'} onChange={(event) => onQualityLevelChange(event.target.value)} />快速成稿</label>
        <label><input type="radio" name="quality-level" value="standard" checked={qualityLevel === 'standard'} onChange={(event) => onQualityLevelChange(event.target.value)} />标准完善</label>
        <label><input type="radio" name="quality-level" value="deep" checked={qualityLevel === 'deep'} onChange={(event) => onQualityLevelChange(event.target.value)} />深度打磨</label>
      </fieldset>
      <button type="button" onClick={onConfirm} disabled={loading || !taskMode || !qualityLevel}>
        {loading ? <><span className="fund-spinner" aria-hidden="true" />正在保存</> : (confirmed ? '已确认工作目标' : '确认工作目标')}
      </button>
    </section>
  )
}

function SectionApprovalPanel({ tasks, onDecision, onPreReview, onAcceptPreReview, onDismissPreReview, onApplyPreReview, loading, title = '待审批章节', testId = 'section-approval-tasks' }) {
  const [dialog, setDialog] = useState(null)
  const [preReviewProgress, setPreReviewProgress] = useState(null)
  const [decisionProgress, setDecisionProgress] = useState(null)
  const [dialogAction, setDialogAction] = useState('')

  const decide = async (task, action) => {
    setDecisionProgress({ taskId: task.id, action })
    try {
      await onDecision(task, action)
    } finally {
      setDecisionProgress(null)
    }
  }

  const openPreReview = async (task) => {
    const previousCount = Number(task.model_output?.pre_review_request_count || 0)
    if (previousCount >= 1) window.alert('请谨慎采纳章节预审批意见！')
    setPreReviewProgress({ taskId: task.id, phase: 'reviewing' })
    try {
      const next = await onPreReview(task)
      if (next) setDialog({ task: next, mode: 'review' })
    } finally {
      setPreReviewProgress(null)
    }
  }

  const applyPreReview = async (task) => {
    setPreReviewProgress({ taskId: task.id, phase: 'applying' })
    try {
      const next = await onApplyPreReview(task)
      if (next) setDialog(null)
    } finally {
      setPreReviewProgress(null)
    }
  }

  const review = dialog?.task?.model_output?.pre_review
  if (!tasks.length) return null
  return (
    <section className='fund-section-approval-tasks' data-testid={testId}>
      <h4>{title}</h4>
      {tasks.map(task => {
        const input = task.input || {}
        const modelOutput = task.model_output || {}
        const preReview = modelOutput.pre_review
        const isFullDraft = input.kind === 'full_draft'
        const taskLabel = input.draft_title || input.section_title || input.section_key || '当前草稿'
        const reviewLabel = isFullDraft ? '全文预评审' : '章节预评审'
        return (
          <article className='fund-section-approval-card' key={task.id}>
            <strong>{taskLabel}</strong>
            {preReviewProgress?.taskId === task.id && (
              <p className='fund-pre-review-progress' role='status'>
                <span className='fund-spinner' aria-hidden='true' />
                {preReviewProgress.phase === 'reviewing'
                  ? '深度思考中，请等待预审批结果。'
                  : isFullDraft
                    ? '正在根据预评审意见优化全文。'
                    : '正在根据预评审意见优化草稿。'}
              </p>
            )}
            {preReview && modelOutput.pre_review_status === 'accepted' && (
              <section className='fund-pre-review-persisted'>
                <strong>已采纳的{reviewLabel}</strong>
                <p>{preReview.summary}</p>
                <div>
                  <b>优点</b>
                  <ul>{(preReview.strengths || []).map((item, index) => <li key={index}>{item}</li>)}</ul>
                </div>
                <div>
                  <b>改进建议</b>
                  {(preReview.issues || []).map((item, index) => (
                    <p key={index}><b>{item.problem}</b><br />理由：{item.reason}<br />改正方向：{item.direction}</p>
                  ))}
                </div>
              </section>
            )}
            <div className='fund-section-approval-actions'>
              <button type='button' onClick={() => decide(task, 'approve')} disabled={loading}>
                {decisionProgress?.taskId === task.id && decisionProgress.action === 'approve' ? <><span className='fund-spinner' aria-hidden='true' />正在审批</> : (isFullDraft ? '通过全文审批' : '通过并锁定章节')}
              </button>
              <button type='button' onClick={() => openPreReview(task)} disabled={loading}>
                {preReviewProgress?.taskId === task.id && preReviewProgress.phase === 'reviewing' ? <><span className='fund-spinner' aria-hidden='true' />正在预评审</> : reviewLabel}
              </button>
              <button className='fund-return-edit' type='button' onClick={() => decide(task, 'edit')} disabled={loading}>
                {decisionProgress?.taskId === task.id && decisionProgress.action === 'edit' ? <><span className='fund-spinner' aria-hidden='true' />正在退回</> : (isFullDraft ? '退回全文修改' : '退回修改')}
              </button>
            </div>
          </article>
        )
      })}
      {dialog && review && (
        <div className='fund-dialog-backdrop' role='presentation'>
          <section className='fund-dialog fund-pre-review-dialog' role='dialog' aria-modal='true' aria-labelledby='section-pre-review-title'>
            <header className='fund-dialog-header'>
              <div>
                <h2 id='section-pre-review-title'>{dialog.task.input?.kind === 'full_draft' ? '全文预评审' : '章节预评审'}</h2>
                <p>{dialog.task.input?.draft_title || dialog.task.input?.section_title || dialog.task.input?.section_key}</p>
              </div>
              <button type='button' onClick={() => setDialog(null)} disabled={loading}>关闭</button>
            </header>
            {dialog.mode === 'review' ? (
              <>
                <p className='fund-pre-review-summary'>{review.summary}</p>
                <section className='fund-pre-review-section'>
                  <h3>值得保留的优点</h3>
                  <ul>{(review.strengths || []).map((item, index) => <li key={index}>{item}</li>)}</ul>
                </section>
                <section className='fund-pre-review-section'>
                  <h3>需要改进的内容</h3>
                  {(review.issues || []).map((item, index) => (
                    <article key={index}>
                      <strong>{item.problem}</strong>
                      <p>理由：{item.reason}</p>
                      <p>改正方向：{item.direction}</p>
                    </article>
                  ))}
                </section>
                <footer className='fund-dialog-actions'>
                  <button type='button' onClick={async () => {
                    setDialogAction('dismiss')
                    try {
                      const next = await onDismissPreReview(dialog.task)
                      if (next) setDialog(null)
                    } finally {
                      setDialogAction('')
                    }
                  }} disabled={loading}>{dialogAction === 'dismiss' ? <><span className='fund-spinner' aria-hidden='true' />正在驳回</> : '驳回'}</button>
                  <button type='button' onClick={async () => {
                    setDialogAction('accept')
                    try {
                      const next = await onAcceptPreReview(dialog.task)
                      if (next) setDialog({ task: next, mode: 'confirm' })
                    } finally {
                      setDialogAction('')
                    }
                  }} disabled={loading}>{dialogAction === 'accept' ? <><span className='fund-spinner' aria-hidden='true' />正在采纳</> : '采纳'}</button>
                </footer>
              </>
            ) : (
              <>
                <p className='fund-pre-review-summary'>是否需要根据评审内容重新修改草稿？</p>
                {dialog.task.input?.kind === 'full_draft' && preReviewProgress?.taskId === dialog.task.id && preReviewProgress.phase === 'applying' && (
                  <p className='fund-pre-review-progress' role='status'>
                    <span className='fund-spinner' aria-hidden='true' />
                    已采纳全文预评审结果，正在根据建议重新优化全文。
                  </p>
                )}
                <footer className='fund-dialog-actions'>
                  <button type='button' onClick={() => applyPreReview(dialog.task)} disabled={loading}>{preReviewProgress?.taskId === dialog.task.id && preReviewProgress.phase === 'applying' ? <><span className='fund-spinner' aria-hidden='true' />正在优化</> : '是'}</button>
                  <button type='button' onClick={() => setDialog(null)} disabled={loading}>否</button>
                </footer>
              </>
            )}
          </section>
        </div>
      )}
    </section>
  )
}

function AuthorPanel({ token, orgId, proposal, onSaved, onExport, exporting }) {
  const intakeSnapshot = proposal?.content?.meta?.intake_snapshot || {}
  const [plan, setPlan] = useState(() => planFromProposal(proposal))
  const [activeStage, setActiveStage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [loadingMessage, setLoadingMessage] = useState('')
  const [error, setError] = useState('')
  const [sectionIndex, setSectionIndex] = useState(0)
  const [answersBySection, setAnswersBySection] = useState(() => Object.fromEntries(
    (proposal?.sections || []).map(section => [section.key, section.answers || {}])
  ))
  const [draftsBySection, setDraftsBySection] = useState(() => Object.fromEntries(
    (proposal?.sections || []).map(section => [section.key, section.draft_content || section.approved_content || ''])
  ))
  const [previousDraftsBySection, setPreviousDraftsBySection] = useState(() => Object.fromEntries(
    (proposal?.sections || []).map(section => [section.key, section.previous_draft || ''])
  ))
  const [changeReq, setChangeReq] = useState('')
  const [setupReady, setSetupReady] = useState(() => Boolean(proposal?.content?.meta?.user_setup?.ready))
  const [taskMode, setTaskMode] = useState(intakeSnapshot.task_mode || '')
  const [qualityLevel, setQualityLevel] = useState(intakeSnapshot.quality_level || '')
  const [intentConfirmed, setIntentConfirmed] = useState(() => Boolean(intakeSnapshot.task_mode && intakeSnapshot.quality_level))
  const [lastSavedAt, setLastSavedAt] = useState(null)
  const [templateHint, setTemplateHint] = useState('')
  const [formattedText, setFormattedText] = useState('')
  const [fullDraft, setFullDraft] = useState('')
  const [previousFullDraft, setPreviousFullDraft] = useState('')
  const [fullDraftApprovalStatus, setFullDraftApprovalStatus] = useState('draft')
  const [fullDraftLoaded, setFullDraftLoaded] = useState(false)
  const [fullChangeReq, setFullChangeReq] = useState('')
  const [filesBySection, setFilesBySection] = useState({})
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const [note, setNote] = useState('')
  const [proposalTitle, setProposalTitle] = useState(proposal?.content?.meta?.title || '')
  const [me, setMe] = useState(null)
  const [generationStatus, setGenerationStatus] = useState({ action: '', state: '', sectionId: '' })
  const [evidenceBySection, setEvidenceBySection] = useState({})
  const [humanTasks, setHumanTasks] = useState([])
  const [sectionOverrides, setSectionOverrides] = useState({})
  const [planningInfo, setPlanningInfo] = useState(null)
  const [planningAnswers, setPlanningAnswers] = useState({})
  const [planningInfoVisible, setPlanningInfoVisible] = useState(false)
  const [planningInfoLoading, setPlanningInfoLoading] = useState(false)

  const sections = plan?.sections || []
  const current = sections[sectionIndex]
  const persistedSections = proposal?.sections || []
  const persistedByKey = Object.fromEntries(persistedSections.map(section => [
    section.key,
    { ...section, ...(sectionOverrides[section.key] || {}) },
  ]))
  const currentSection = current ? persistedByKey[current.id] : null
  const answers = current ? (answersBySection[current.id] || currentSection?.answers || {}) : {}
  const draft = current ? (draftsBySection[current.id] || '') : ''
  const setDraft = (value) => {
    if (!current) return
    setDraftsBySection(previous => ({
      ...previous,
      [current.id]: typeof value === 'function' ? value(previous[current.id] || '') : value,
    }))
  }
  const setAnswers = (value) => {
    if (!current) return
    setAnswersBySection(previous => ({
      ...previous,
      [current.id]: typeof value === 'function'
        ? value(previous[current.id] || currentSection?.answers || {})
        : value,
    }))
  }
  const approvedById = proposal?.content?.sections || {}
  const persistedDraft = currentSection?.approved_content
    || currentSection?.draft_content
    || approvedById?.[current?.id]?.content
    || ''
  const previousDraft = current ? (previousDraftsBySection[current.id] || currentSection?.previous_draft || '') : ''
  const approvedSectionCount = sections.filter(
    section => persistedByKey[section.id]?.state === 'approved'
  ).length
  const allApproved = sections.length > 0 && approvedSectionCount === sections.length
  const sectionApprovalTasks = humanTasks.filter(task => task.node === 'section_approval')
  const fullDraftApprovalTasks = humanTasks.filter(task => (
    task.node === 'final_export_confirmation' && task.input?.kind === 'full_draft'
  ))
  const fullDraftApprovalPending = fullDraftApprovalTasks.length > 0
  const fullDraftApproved = fullDraftApprovalStatus === 'approved'
  const proposalFinalized = Boolean(formattedText || proposal?.final_markdown)
  const currentApprovalPending = Boolean(current && humanTasks.some(
    task => task.input?.section_key === current.id
  ))
  const currentEvidence = current ? (evidenceBySection[current.id] || []) : []
  const planningQuestion = planningInfo?.question
  const planningFields = Array.isArray(planningQuestion?.fields) ? planningQuestion.fields : []
  const planningAnswerValue = (field) => (
    Object.prototype.hasOwnProperty.call(planningAnswers, field)
      ? planningAnswers[field]
      : (planningInfo?.collected_answers?.[field] || '')
  )
  const planningAnswerPayload = Object.fromEntries(
    planningFields.map(field => [field, planningAnswerValue(field)])
  )
  const startLoading = (message) => {
    setLoadingMessage(message)
    setLoading(true)
  }
  const stopLoading = () => {
    setLoading(false)
    setLoadingMessage('')
  }
  const workflowErrorMessage = (requestError, fallback) => {
    if (requestError?.status === 401) return '登录状态已失效，请重新登录后再试。'
    if (requestError?.status === 403) return '你没有操作当前工作区的权限。'
    if (requestError?.data?.message) return requestError.data.message
    if (requestError?.data?.error?.error_code === 'invalid_provider_output') {
      return '生成内容的格式异常，系统未保存该结果，请重新生成。'
    }
    if (requestError?.data?.error === 'ai_provider_error') return '模型服务暂时不可用，请检查密钥和网络后重试。'
    return fallback
  }

  const refreshHumanTasks = async () => {
    if (!proposal?.id) {
      setHumanTasks([])
      return
    }
    try {
      const result = await api('/ai/human-tasks?proposal_id=' + proposal.id, { token, orgId: orgId || undefined })
      setHumanTasks(result.tasks || [])
    } catch {
      setHumanTasks([])
    }
  }

  const loadFullDraft = async () => {
    const result = await api(`/ai/proposals/${proposal.id}/full-draft`, { token, orgId: orgId || undefined })
    setFullDraft(result.draft_text || '')
    setFullDraftApprovalStatus(result.approval_status || 'draft')
    setFullDraftLoaded(true)
    return result
  }

  useEffect(() => {
    const restored = planFromProposal(proposal)
    if (restored) setPlan(restored)
    setAnswersBySection(previous => {
      const next = { ...previous }
      for (const section of proposal?.sections || []) {
        if (!next[section.key] || Object.keys(next[section.key]).length === 0) {
          next[section.key] = section.answers || {}
        }
      }
      return next
    })
    setDraftsBySection(previous => {
      const next = { ...previous }
      for (const section of proposal?.sections || []) {
        if (!next[section.key]) {
          next[section.key] = section.draft_content || section.approved_content || ''
        }
      }
      return next
    })
    setPreviousDraftsBySection(previous => {
      const next = { ...previous }
      for (const section of proposal?.sections || []) {
        if (!Object.prototype.hasOwnProperty.call(next, section.key)) {
          next[section.key] = section.previous_draft || ''
        }
      }
      return next
    })
  }, [proposal?.id, proposal?.sections])

  useEffect(() => {
    setSectionOverrides({})
  }, [proposal?.sections])

  useEffect(() => {
    if (!currentSection?.id || !current) return
    api(`/ai/sections/${currentSection.id}/evidence`, { token, orgId: orgId || undefined })
      .then(result => setEvidenceBySection(previous => ({ ...previous, [current.id]: result.evidence || [] })))
      .catch(() => {})
  }, [current?.id, currentSection?.id, orgId, token])

  useEffect(() => {
    refreshHumanTasks()
  }, [proposal?.id, orgId, token])

  useEffect(() => {
    // Initialize note from proposal.content.meta.note
    const n = proposal?.content?.meta?.note
    setNote(typeof n === 'string' ? n : '')
    setProposalTitle(proposal?.content?.meta?.title || '')
    setSetupReady(Boolean(proposal?.content?.meta?.user_setup?.ready))
    const snapshot = proposal?.content?.meta?.intake_snapshot || {}
    setTaskMode(snapshot.task_mode || '')
    setQualityLevel(snapshot.quality_level || '')
    setIntentConfirmed(Boolean(snapshot.task_mode && snapshot.quality_level))
    setPlanningInfo(null)
    setPlanningAnswers({})
    setPlanningInfoVisible(false)
    setLoadingMessage('')
    setGenerationStatus({ action: '', state: '', sectionId: '' })
    setFullDraft('')
    setPreviousFullDraft('')
    setFullDraftApprovalStatus('draft')
    setFullDraftLoaded(false)
    setFullChangeReq('')
  }, [proposal?.id])

  useEffect(() => {
    setFormattedText(proposal?.final_markdown || '')
  }, [proposal?.id, proposal?.final_markdown])

  useEffect(() => {
    if (!allApproved || !proposal?.id) {
      setFullDraftLoaded(false)
      return
    }
    let cancelled = false
    loadFullDraft().catch(requestError => {
      if (!cancelled) setError(workflowErrorMessage(requestError, '审批后全文草稿加载失败，请稍后重试。'))
    })
    return () => { cancelled = true }
  }, [allApproved, proposal?.id, orgId, token])

  useEffect(() => {
    // Fetch current user (for display only)
    (async () => {
      try {
        const res = await api('/me', { token })
        setMe(res?.user || null)
      } catch {}
    })()
  }, [token])

  const onUploadFile = async (e) => {
    const file = e.target.files && e.target.files[0]
    if (!file || !current) return
    setUploading(true)
    setUploadError('')
    try {
      const info = await apiUpload('/files', {
        token,
        orgId: orgId || undefined,
        file,
        fields: { proposal_id: proposal.id, material_kind: 'evidence' },
      })
      setFilesBySection(prev => ({
        ...prev,
        [current.id]: [ ...(prev[current.id] || []), { ...info, name: file.name } ],
      }))
      e.target.value = ''
  } catch {
  setUploadError(t('ui.common.upload_failed'))
    } finally {
      setUploading(false)
    }
  }

  const selectSection = (nextIndex) => {
    if (nextIndex < 0 || nextIndex >= sections.length) return
    setSectionIndex(nextIndex)
    setChangeReq('')
  }

  const confirmIntent = async () => {
    if (!taskMode || !qualityLevel) {
      setError('请先完成两个带红色星号的写作目标选择。')
      return
    }
    startLoading('正在保存写作目标。')
    setError('')
    try {
      await api('/ai/intake', {
        method: 'POST',
        token,
        orgId: orgId || undefined,
        body: {
          proposal_id: proposal.id,
          task_mode: taskMode,
          quality_level: qualityLevel,
          inputs: {},
          user_overrides: {},
        },
      })
      setIntentConfirmed(true)
      await onSaved?.()
    } catch (requestError) {
      setError(workflowErrorMessage(requestError, '工作目标保存失败，请稍后重试。'))
    } finally {
      stopLoading()
    }
  }

  const loadPlanningInfo = async () => {
    setPlanningInfoLoading(true)
    try {
      const next = await api('/ai/grill?proposal_id=' + proposal.id + '&mode=planning', {
        token,
        orgId: orgId || undefined,
      })
      setPlanningInfo(next)
      setPlanningAnswers({})
      return next
    } catch (requestError) {
      setError(workflowErrorMessage(requestError, '补充规划信息加载失败，请稍后重试。'))
      return null
    } finally {
      setPlanningInfoLoading(false)
    }
  }

  const openPlanningInfo = async () => {
    setPlanningInfoVisible(true)
    if (!planningInfo) await loadPlanningInfo()
  }

  const savePlanningInfo = async (body) => {
    setPlanningInfoLoading(true)
    setError('')
    try {
      const next = await api('/ai/grill', {
        method: 'POST',
        token,
        orgId: orgId || undefined,
        body: { proposal_id: proposal.id, mode: 'planning', ...body },
      })
      setPlanningInfo(next)
      setPlanningAnswers({})
      return next
    } catch (requestError) {
      setError(workflowErrorMessage(requestError, '补充规划信息保存失败，请稍后重试。'))
      return null
    } finally {
      setPlanningInfoLoading(false)
    }
  }

  const answerPlanningQuestion = async (skip) => {
    if (!planningQuestion) return
    await savePlanningInfo({ answers: planningAnswerPayload, skip })
  }

  const previousPlanningQuestion = async () => {
    if (!planningQuestion) return
    await savePlanningInfo({ answers: planningAnswerPayload, previous: true })
  }

  const finishPlanningInfo = async () => {
    await savePlanningInfo({ answers: planningAnswerPayload, finish: true, confirm: true })
  }

  const startPlan = async () => {
    if (proposalFinalized) {
      setError('最终定稿已生成，章节规划已锁定，不能重新生成。')
      return
    }
    if (!setupReady) {
      setError('请先完成上方带红色星号的项目基础信息。')
      return
    }
    if (!intentConfirmed) {
      setError('请先确认你的写作目标，再生成章节规划。')
      return
    }
    startLoading('深度思考中，正在生成章节规划。')
    setError('')
    setGenerationStatus({ action: 'plan', state: 'loading', sectionId: '' })
    try {
      const p = await apiMaybeAsync('/ai/plan', {
        method: 'POST',
        token,
        orgId: orgId || undefined,
        body: { proposal_id: proposal.id },
      })
      const normalized = normalizePlan(p)
      setPlan(normalized)
      setSectionIndex(0)
      setAnswersBySection({})
      setDraftsBySection({})
      setChangeReq('')
      const plannedAllApproved = normalized.sections.length > 0 && normalized.sections.every(
        section => persistedByKey[section.id]?.state === 'approved'
      )
      const firstHasDraft = !!persistedByKey[normalized.sections[0]?.id]?.draft_content
      setActiveStage(plannedAllApproved ? 4 : firstHasDraft ? 3 : 2)
      await onSaved?.()
      setGenerationStatus({ action: 'plan', state: 'done', sectionId: '' })
    } catch (requestError) {
      setGenerationStatus({ action: 'plan', state: 'error', sectionId: '' })
      if (requestError?.status === 409 && requestError?.data?.error === 'grill_confirmation_required') {
        await openPlanningInfo()
        setError('请先完成补充规划信息并确认后，再生成章节规划。')
        return
      }
      setError(workflowErrorMessage(requestError, '章节规划生成失败，请稍后重试。'))
    } finally {
      stopLoading()
    }
  }

  const writeDraft = async () => {
    if (!current) return
    startLoading('深度思考中，正在生成本章草稿。')
    setError('')
    setGenerationStatus({ action: 'write', state: 'loading', sectionId: current.id })
    try {
      const res = await apiMaybeAsync('/ai/write', {
        method: 'POST',
        token,
        orgId: orgId || undefined,
        body: {
          proposal_id: proposal.id,
          section_id: current.id,
          answers,
          file_refs: (current && filesBySection[current.id]) ? filesBySection[current.id] : [],
        },
      })
      const before = draft || persistedDraft
      const nextDraft = res?.draft_text || ''
      setDraft(nextDraft)
      if (before && nextDraft && before !== nextDraft) {
        setPreviousDraftsBySection(previous => ({ ...previous, [current.id]: before }))
      }
      if (res?.evidence) setEvidenceBySection(previous => ({ ...previous, [current.id]: res.evidence }))
      await onSaved?.()
      setGenerationStatus({ action: 'write', state: 'done', sectionId: current.id })
    } catch (requestError) {
      setGenerationStatus({ action: 'write', state: 'error', sectionId: current.id })
      setError(workflowErrorMessage(requestError, '本章草稿生成失败，请稍后重试。'))
    } finally { stopLoading() }
  }

  const applyChanges = async () => {
    if (!current) return
    startLoading('深度思考中，正在按照要求修订本章。')
    setError('')
    setGenerationStatus({ action: 'revise', state: 'loading', sectionId: current.id })
    try {
      const res = await apiMaybeAsync('/ai/revise', {
        method: 'POST',
        token,
        orgId: orgId || undefined,
        body: {
          proposal_id: proposal.id,
          section_id: current.id,
          base_text: draft || persistedDraft,
          change_request: changeReq,
          file_refs: (current && filesBySection[current.id]) ? filesBySection[current.id] : [],
        },
      })
      const before = draft || persistedDraft
      setDraft(res?.draft_text || draft)
      setPreviousDraftsBySection(previous => ({ ...previous, [current.id]: before }))
      setChangeReq('')
      await onSaved?.()
      setGenerationStatus({ action: 'revise', state: 'done', sectionId: current.id })
    } catch (requestError) {
      setGenerationStatus({ action: 'revise', state: 'error', sectionId: current.id })
      setError(workflowErrorMessage(requestError, '本章修订失败，请稍后重试。'))
    } finally { stopLoading() }
  }

  const saveCurrentDraft = async () => {
    if (!currentSection?.id) return
    const currentDraft = draft || persistedDraft
    if (!currentDraft.trim()) {
      setError('当前草稿为空，无法保存。')
      return
    }
    startLoading('正在保存当前草稿。')
    setError('')
    try {
      const result = await api(`/ai/sections/${currentSection.id}/draft`, {
        method: 'PATCH',
        token,
        orgId: orgId || undefined,
        body: { draft_text: currentDraft },
      })
      setDraft(result.draft_text || currentDraft)
      setPreviousDraftsBySection(previous => ({
        ...previous,
        [current.id]: result.previous_draft || previous[current.id] || '',
      }))
      setLastSavedAt(new Date())
      await onSaved?.()
    } catch (requestError) {
      setError(workflowErrorMessage(requestError, '当前草稿保存失败，请稍后重试。'))
    } finally {
      stopLoading()
    }
  }

  const submitForApproval = async () => {
    if (!currentSection?.id) return
    startLoading('正在提交章节审批。')
    setError('')
    try {
      const currentDraft = draft || persistedDraft
      if (currentDraft && currentDraft !== persistedDraft) {
        const result = await api(`/ai/sections/${currentSection.id}/draft`, {
          method: 'PATCH',
          token,
          orgId: orgId || undefined,
          body: { draft_text: currentDraft },
        })
        setPreviousDraftsBySection(previous => ({
          ...previous,
          [current.id]: result.previous_draft || previous[current.id] || '',
        }))
      }
      await api('/ai/workflow/run', {
        method: 'POST',
        token,
        orgId: orgId || undefined,
        body: {
          proposal_id: proposal.id,
          section_key: current.id,
          plan: sections.map(section => ({
            section_key: section.id,
            title: section.title,
            questions: section.inputs || [],
          })),
          answers,
          draft: currentDraft,
          review: {
            schema_version: 'v1',
            section_key: current.id,
            decision: 'human_review',
            issues: [],
            required_changes: [],
            protected_facts: [],
            evidence_gaps: [],
          },
        },
      })
      setLastSavedAt(new Date())
      await refreshHumanTasks()
      await onSaved?.()
      setActiveStage(3)
    } catch (requestError) {
      setError(workflowErrorMessage(requestError, '提交章节审批失败，请稍后重试。'))
    } finally { stopLoading() }
  }

  const saveNote = async () => {
    // Patch proposal content.meta.note without touching sections
    const content = { ...(proposal.content || {}) }
    content.meta = { ...(content.meta || {}), note }
    const body = { content, schema_version: proposal.schema_version || plan?.schema_version || 'v1' }
    startLoading('正在保存备注。')
    setError('')
    try {
      await api(`/proposals/${proposal.id}/`, { method: 'PATCH', token, orgId: orgId || undefined, body })
      setLastSavedAt(new Date())
      await onSaved?.()
    } catch {
  setError(t('ui.errors.save_note_failed'))
    } finally { stopLoading() }
  }

  const saveTitle = async () => {
    const title = proposalTitle.trim()
    if (!title) {
      setError('项目标题不能为空')
      return
    }
    const content = { ...(proposal.content || {}) }
    content.meta = { ...(content.meta || {}), title }
    startLoading('正在保存项目标题。')
    setError('')
    try {
      await api(`/proposals/${proposal.id}/`, {
        method: 'PATCH',
        token,
        orgId: orgId || undefined,
        body: {
          content,
          schema_version: proposal.schema_version || plan?.schema_version || 'v1',
        },
      })
      setLastSavedAt(new Date())
      await onSaved?.()
    } catch {
      setError('项目标题保存失败')
    } finally {
      stopLoading()
    }
  }

  const persistFullDraft = async (draftText) => {
    const result = await api(`/ai/proposals/${proposal.id}/full-draft`, {
      method: 'PATCH',
      token,
      orgId: orgId || undefined,
      body: { draft_text: draftText },
    })
    setFullDraft(result.draft_text || draftText)
    setFullDraftApprovalStatus(result.approval_status || 'draft')
    setFullDraftLoaded(true)
    return result
  }

  const reviseFullDraft = async ({ baseText, changeRequest, source }) => {
    const isPreReviewRevision = source === 'pre_review'
    const action = isPreReviewRevision ? 'full-pre-review-revise' : 'full-manual-revise'
    const message = isPreReviewRevision
      ? '已采纳全文预评审结果，正在根据建议重新优化全文。'
      : '深度思考中，正在按照要求修订全文。'
    startLoading(isPreReviewRevision ? '正在根据全文预评审意见修订草稿。' : '正在修订全文。')
    setError('')
    setGenerationStatus({ action, state: 'loading', sectionId: '__full__', message })
    try {
      if (!allApproved) {
        setError('请先完成所有章节的人工作审批，再修订全文。')
        setGenerationStatus({ action, state: 'error', sectionId: '__full__', message: '' })
        return null
      }
      if (!changeRequest?.trim()) {
        setError('请先填写全文审核修改要求。')
        setGenerationStatus({ action, state: 'error', sectionId: '__full__', message: '' })
        return null
      }
      let resolvedBaseText = String(baseText || '').trim()
      if (!resolvedBaseText) {
        const restored = await loadFullDraft()
        resolvedBaseText = String(restored?.draft_text || '').trim()
      }
      if (!resolvedBaseText) {
        setError('审批后全文草稿尚未准备完成，请稍后重试。')
        setGenerationStatus({ action, state: 'error', sectionId: '__full__', message: '' })
        return null
      }
      const allFileRefs = []
      for (const section of sections) {
        if (filesBySection[section.id]?.length) allFileRefs.push(...filesBySection[section.id])
      }
      const result = await apiMaybeAsync('/ai/revise', {
        method: 'POST',
        token,
        orgId: orgId || undefined,
        body: {
          proposal_id: proposal.id,
          draft_scope: 'full',
          base_text: resolvedBaseText,
          change_request: changeRequest,
          file_refs: allFileRefs,
        },
      })
      const nextDraft = result?.draft_text || ''
      if (!nextDraft) {
        setError('系统未返回修订后的全文草稿，请稍后重试。')
        setGenerationStatus({ action, state: 'error', sectionId: '__full__', message: '' })
        return null
      }
      const before = resolvedBaseText
      await persistFullDraft(nextDraft)
      setPreviousFullDraft(before)
      if (!isPreReviewRevision) setFullChangeReq('')
      await refreshHumanTasks()
      await onSaved?.()
      setGenerationStatus({ action, state: 'done', sectionId: '__full__', message: '' })
      return true
    } catch (requestError) {
      setGenerationStatus({ action, state: 'error', sectionId: '__full__', message: '' })
      setError(workflowErrorMessage(
        requestError,
        isPreReviewRevision ? '根据全文预评审修订草稿失败，请稍后重试。' : '全文草稿修订失败，请稍后重试。',
      ))
      return null
    } finally {
      stopLoading()
    }
  }

  const applyFullDraftChanges = async () => (
    reviseFullDraft({
      baseText: fullDraft,
      changeRequest: fullChangeReq,
      source: 'manual',
    })
  )

  const applyFullPreReviewChanges = async (task) => {
    const changeRequest = task.model_output?.pre_review?.revision_request || ''
    if (!changeRequest.trim()) {
      setError('当前全文预评审内容不可用，无法自动修订。')
      return null
    }
    return reviseFullDraft({
      baseText: fullDraft || task.input?.draft_text || '',
      changeRequest,
      source: 'pre_review',
    })
  }

  const submitFullDraftForApproval = async () => {
    if (!allApproved || !fullDraft.trim() || fullDraftApprovalPending) return
    startLoading('正在提交全文审批。')
    setError('')
    try {
      const state = await persistFullDraft(fullDraft)
      await api('/ai/human-tasks', {
        method: 'POST',
        token,
        orgId: orgId || undefined,
        body: {
          proposal_id: proposal.id,
          node: 'final_export_confirmation',
          thread_id: `full-draft-${proposal.id}-${state.version}-${Date.now()}`,
          input: {
            kind: 'full_draft',
            draft_title: '审批后全文草稿',
            draft_version: state.version,
            draft_text: state.draft_text,
          },
        },
      })
      setFullDraftApprovalStatus('pending')
      await refreshHumanTasks()
      await onSaved?.()
    } catch (requestError) {
      setError(workflowErrorMessage(requestError, '提交全文审批失败，请稍后重试。'))
    } finally {
      stopLoading()
    }
  }

  const reopenApprovedSection = async (section) => {
    const persisted = persistedByKey[section.id]
    if (!persisted?.id || proposalFinalized) return
    startLoading('正在解除章节审批锁定。')
    setError('')
    try {
      const result = await api(`/ai/sections/${persisted.id}/reopen`, {
        method: 'POST',
        token,
        orgId: orgId || undefined,
      })
      setSectionOverrides(previous => ({
        ...previous,
        [section.id]: {
          state: result.state || 'draft',
          locked: Boolean(result.locked),
          draft_content: result.draft_text || previous[section.id]?.draft_content || '',
        },
      }))
      setDraftsBySection(previous => ({ ...previous, [section.id]: result.draft_text || previous[section.id] || '' }))
      setFullDraft('')
      setFullDraftLoaded(false)
      setFullDraftApprovalStatus('draft')
      const targetIndex = sections.findIndex(item => item.id === section.id)
      await refreshHumanTasks()
      await onSaved?.()
      if (targetIndex >= 0) setSectionIndex(targetIndex)
      setActiveStage(3)
    } catch (requestError) {
      setError(workflowErrorMessage(requestError, '解除章节审批锁定失败，请稍后重试。'))
    } finally {
      stopLoading()
    }
  }

  const runFinalFormatting = async () => {
    if (!allApproved || !fullDraftApproved || proposalFinalized) return
    startLoading('深度思考中，正在生成最终定稿。')
    setError('')
    setGenerationStatus({ action: 'format', state: 'loading', sectionId: '' })
    try {
      const allFileRefs = []
      for (const s of sections) {
        if (filesBySection[s.id]?.length) {
          allFileRefs.push(...filesBySection[s.id])
        }
      }
      const res = await apiMaybeAsync('/ai/format', {
        method: 'POST',
        token,
        orgId: orgId || undefined,
        body: {
          proposal_id: proposal.id,
          template_hint: templateHint || undefined,
          file_refs: allFileRefs,
        },
      })
      setFormattedText(res?.formatted_text || '')
      await onSaved?.()
      setGenerationStatus({ action: 'format', state: 'done', sectionId: '' })
    } catch (requestError) {
      setGenerationStatus({ action: 'format', state: 'error', sectionId: '' })
      setError(workflowErrorMessage(requestError, '最终定稿生成失败，请稍后重试。'))
    } finally { stopLoading() }
  }

  const decideHumanTask = async (task, action) => {
    startLoading(action === 'approve' ? '正在提交审批结果。' : '正在退回修改。')
    setError('')
    try {
      const result = await api('/ai/human-tasks/' + task.id + '/decision', {
        method: 'POST',
        token,
        orgId: orgId || undefined,
        body: { thread_id: task.thread_id, action },
      })
      await refreshHumanTasks()
      await onSaved?.()
      if (task.input?.kind === 'full_draft') {
        setFullDraftApprovalStatus(action === 'approve' ? 'approved' : 'draft')
        if (result?.status === 'approved' || action === 'edit') await loadFullDraft()
        setActiveStage(4)
      } else if (action === 'edit') {
        const targetIndex = sections.findIndex(section => section.id === task.input?.section_key)
        if (targetIndex >= 0) setSectionIndex(targetIndex)
        setActiveStage(3)
      } else if (action === 'approve') {
        const targetIndex = sections.findIndex(section => section.id === task.input?.section_key)
        if (targetIndex >= 0 && targetIndex < sections.length - 1) {
          selectSection(targetIndex + 1)
          setActiveStage(2)
        } else {
          setActiveStage(4)
        }
      }
    } catch (requestError) {
      setError(workflowErrorMessage(requestError, '人工审批提交失败，请稍后重试。'))
    } finally {
      stopLoading()
    }
  }

  const replaceHumanTask = (nextTask) => {
    setHumanTasks(previous => previous.map(task => task.id === nextTask.id ? nextTask : task))
    return nextTask
  }

  const runSectionPreReview = async (task) => {
    startLoading('正在生成章节预评审。')
    setError('')
    try {
      const next = await api(`/ai/human-tasks/${task.id}/pre-review`, {
        method: 'POST',
        token,
        orgId: orgId || undefined,
      })
      return replaceHumanTask(next)
    } catch (requestError) {
      setError(workflowErrorMessage(requestError, '章节预评审生成失败，请稍后重试。'))
      return null
    } finally {
      stopLoading()
    }
  }

  const acceptSectionPreReview = async (task) => {
    startLoading('正在采纳预审批结果。')
    setError('')
    try {
      const next = await api(`/ai/human-tasks/${task.id}/pre-review`, {
        method: 'POST',
        token,
        orgId: orgId || undefined,
        body: { action: 'accept' },
      })
      return replaceHumanTask(next)
    } catch (requestError) {
      setError(workflowErrorMessage(requestError, '章节预评审采纳失败，请稍后重试。'))
      return null
    } finally {
      stopLoading()
    }
  }

  const dismissSectionPreReview = async (task) => {
    startLoading('正在驳回预审批结果。')
    setError('')
    try {
      const next = await api(`/ai/human-tasks/${task.id}/pre-review`, {
        method: 'POST',
        token,
        orgId: orgId || undefined,
        body: { action: 'dismiss' },
      })
      return replaceHumanTask(next)
    } catch (requestError) {
      setError(workflowErrorMessage(requestError, '章节预评审驳回失败，请稍后重试。'))
      return null
    } finally {
      stopLoading()
    }
  }

  const applySectionPreReview = async (task) => {
    if (task.input?.kind === 'full_draft') {
      const revised = await applyFullPreReviewChanges(task)
      return revised ? task : null
    }
    const sectionKey = task.input?.section_key
    const reviewRequest = task.model_output?.pre_review?.revision_request || ''
    const targetIndex = sections.findIndex(section => section.id === sectionKey)
    const targetSection = persistedByKey[sectionKey]
    const baseText = draftsBySection[sectionKey] || targetSection?.draft_content || targetSection?.approved_content || ''
    if (!sectionKey || !reviewRequest || !baseText) {
      setError('当前章节或预评审内容不可用，无法自动修订。')
      return null
    }
    if (targetIndex >= 0) setSectionIndex(targetIndex)
    setActiveStage(3)
    startLoading('正在根据评审建议修订本章。')
    setError('')
    setGenerationStatus({ action: 'revise', state: 'loading', sectionId: sectionKey, message: '已采纳审批结果，正在根据建议重新优化该章节。' })
    try {
      const result = await apiMaybeAsync('/ai/revise', {
        method: 'POST',
        token,
        orgId: orgId || undefined,
        body: {
          proposal_id: proposal.id,
          section_id: sectionKey,
          base_text: baseText,
          change_request: reviewRequest,
          file_refs: filesBySection[sectionKey] || [],
        },
      })
      const nextDraft = result?.draft_text || ''
      if (!nextDraft) {
        setError('系统未返回修订后的草稿，请稍后重试。')
        setGenerationStatus({ action: 'revise', state: 'error', sectionId: sectionKey, message: '' })
        return null
      }
      setDraftsBySection(previous => ({ ...previous, [sectionKey]: nextDraft }))
      setPreviousDraftsBySection(previous => ({ ...previous, [sectionKey]: baseText }))
      const nextTask = await api(`/ai/human-tasks/${task.id}/pre-review`, {
        method: 'POST',
        token,
        orgId: orgId || undefined,
        body: { action: 'dismiss' },
      })
      replaceHumanTask(nextTask)
      setGenerationStatus({ action: 'revise', state: 'done', sectionId: sectionKey, message: '' })
      await onSaved?.()
      return nextTask
    } catch (requestError) {
      setGenerationStatus({ action: 'revise', state: 'error', sectionId: sectionKey, message: '' })
      setError(workflowErrorMessage(requestError, '根据章节预评审修订草稿失败，请稍后重试。'))
      return null
    } finally {
      stopLoading()
    }
  }

  return (
    <div className="fund-author-panel">
      <Phase12Workspace
        proposal={proposal}
        token={token}
        orgId={orgId}
        onReady={async status => {
          setSetupReady(Boolean(status?.ready))
          await onSaved?.()
        }}
        onContinue={() => {
          setActiveStage(1)
          document.getElementById(`proposal-planning-${proposal.id}`)?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
        }}
      />
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
        <div>
          <h3 style={{ margin: 0 }}>基金申请书工作区</h3>
          <div className="fund-title-editor">
            <label className="fund-title-required-label" htmlFor={`proposal-title-${proposal.id}`}>
              <span>项目标题 <b className="fund-required-marker" aria-hidden="true">*</b></span>
              <small className="fund-field-hint">本项为必填。请填写能够概括申请主题的项目名称。</small>
            </label>
            <input
              id={`proposal-title-${proposal.id}`}
              aria-label="项目标题"
              value={proposalTitle}
              onChange={(e) => setProposalTitle(e.target.value)}
              placeholder="请输入项目标题"
            />
            <button onClick={saveTitle} disabled={loading}>保存标题</button>
          </div>
          <div><strong>创建者</strong>：#{proposal.author}</div>
          <div><strong>创建时间</strong>：{proposal.created_at ? new Date(proposal.created_at).toLocaleString() : '暂无'}</div>
          <div><strong>最近编辑</strong>：{proposal.last_edited ? new Date(proposal.last_edited).toLocaleString() : '暂无'}{me ? `，编辑者 ${me.username || '当前用户'}` : ''}{lastSavedAt ? '，刚刚保存' : ''}</div>
        </div>
        <div style={{ minWidth: 280 }}>
          <label className="fund-inline-field">
            <span>内部备注，可选</span>
            <small className="fund-field-hint">仅供自己或协作者查看；如无需要记录的事项可留空。</small>
            <textarea style={{ width: '100%' }} data-testid="note-text" rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="例如：待补充的材料或后续沟通事项" />
          </label>
          <button data-testid="note-save" onClick={saveNote} disabled={loading}>保存备注</button>
        </div>
      </div>

      <div className="fund-stage-tabs" role="tablist" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(120px, 1fr))', gap: 8, margin: '20px 0' }}>
        {[
          [1, '1 章节规划'],
          [2, '2 分章写作'],
          [3, '3 人工审核与修订'],
          [4, '4 定稿与导出'],
        ].map(([stage, label]) => (
          <button
            key={stage}
            role="tab"
            aria-selected={activeStage === stage}
            onClick={() => setActiveStage(stage)}
            disabled={stage > 1 && !plan}
            style={{ padding: 10, fontWeight: activeStage === stage ? 700 : 400 }}
          >
            {label}
          </button>
        ))}
      </div>
      <SectionApprovalPanel
        tasks={sectionApprovalTasks}
        onDecision={decideHumanTask}
        onPreReview={runSectionPreReview}
        onAcceptPreReview={acceptSectionPreReview}
        onDismissPreReview={dismissSectionPreReview}
        onApplyPreReview={applySectionPreReview}
        loading={loading}
      />
      {loading && loadingMessage && (
        <p className='fund-api-action-feedback' role='status'>
          <span className='fund-spinner' aria-hidden='true' />
          {loadingMessage}
        </p>
      )}

      {activeStage === 1 && (
        <div id={`proposal-planning-${proposal.id}`} style={{ padding: 16, background: '#fff', borderRadius: 8 }}>
          <h4>规划申请书章节</h4>
          <p>系统将依据已保存的项目基础信息、基金指南和用户材料生成章节问题。</p>
          {!setupReady && <p className="fund-status-message is-error">请先完成上方带红色星号的项目基础信息。</p>}
          <UserIntentPanel
            taskMode={taskMode}
            qualityLevel={qualityLevel}
            confirmed={intentConfirmed}
            loading={loading}
            onTaskModeChange={(value) => {
              setTaskMode(value)
              setIntentConfirmed(false)
            }}
            onQualityLevelChange={(value) => {
              setQualityLevel(value)
              setIntentConfirmed(false)
            }}
            onConfirm={confirmIntent}
           />
           {!intentConfirmed && <p className="fund-status-message">请完成上方两个写作目标选择后继续。</p>}
           {intentConfirmed && !planningInfoVisible && (
             <button type='button' onClick={openPlanningInfo} disabled={loading}>
               补充规划信息，可选
             </button>
           )}
           {planningInfoVisible && (
             <section className='fund-planning-info' data-testid='planning-info'>
               <strong>补充规划信息</strong>
               <p>此步骤可选。补充已掌握的信息有助于章节规划更贴合项目；对暂时无法判断的问题，可留空或如实填写：不清楚，也可使用跳过此题。</p>
               {planningInfoLoading && <p className='fund-api-action-feedback' role='status'><span className='fund-spinner' aria-hidden='true' />正在处理补充规划信息。</p>}
               {planningInfo?.confirmed && <p>补充信息已确认，可以生成章节规划。</p>}
               {!planningInfoLoading && planningQuestion && (
                 <div className='fund-planning-question'>
                   <p>第 {planningQuestion.index} 题，共 {planningInfo.max_questions} 题：{planningQuestion.prompt}</p>
                   {planningFields.map(field => (
                     <label className='fund-planning-answer' key={field}>
                       <span>{planningFieldLabels[field] || '补充信息'}</span>
                       <textarea
                         aria-label={planningFieldLabels[field] || '补充信息'}
                         rows={2}
                         placeholder='请填写已掌握的信息；若无可提供信息，可留空或如实填写：不清楚'
                         value={planningAnswerValue(field)}
                         onChange={event => setPlanningAnswers(previous => ({ ...previous, [field]: event.target.value }))}
                       />
                     </label>
                   ))}
                   <div className='fund-planning-controls'>
                     <button type='button' onClick={previousPlanningQuestion} disabled={planningQuestion.index <= 1 || planningInfoLoading}>上一题</button>
                     <button type='button' onClick={() => answerPlanningQuestion(false)} disabled={planningInfoLoading}>下一题</button>
                     <button type='button' onClick={() => answerPlanningQuestion(true)} disabled={planningInfoLoading}>跳过此题</button>
                     <button type='button' onClick={finishPlanningInfo} disabled={planningInfoLoading}>结束补充</button>
                   </div>
                 </div>
               )}
               {!planningInfoLoading && !planningQuestion && !planningInfo?.confirmed && (
                 <div className='fund-planning-controls'>
                   <span>已完成固定问题，请确认后继续。</span>
                   <button type='button' onClick={finishPlanningInfo}>结束补充</button>
                 </div>
               )}
             </section>
           )}
           <div className="fund-generation-action">
            <button onClick={startPlan} disabled={loading || !setupReady || !intentConfirmed || proposalFinalized}>生成章节规划</button>
            <GenerationFeedback action="plan" status={generationStatus} />
          </div>
          {proposalFinalized && <p className='fund-final-approval-status'>最终定稿已生成，章节规划已锁定。</p>}
          {sections.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <strong>已保存的章节</strong>
              <ol>
                {sections.map(section => (
                  <li key={section.id}>{section.title || section.id}，{section.inputs.length} 个问题</li>
                ))}
              </ol>
              <button onClick={() => setActiveStage(allApproved ? 4 : 2)}>继续当前申请书</button>
            </div>
          )}
        </div>
      )}

      {plan && activeStage !== 1 && (
        <div style={{ padding: 16, background: '#fff', borderRadius: 8 }}>
          {activeStage !== 4 && (
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap', marginBottom: 16 }}>
              <button onClick={() => selectSection(sectionIndex - 1)} disabled={loading || sectionIndex === 0}>上一章节</button>
              <div>
            <div><strong>第 {sectionIndex + 1} 章，共 {sections.length} 章：</strong> {current?.title}</div>
            <div>
              结构版本：{plan?.schema_version || 'v1'}
              {lastSavedAt && <span> · 最近保存：{lastSavedAt.toLocaleTimeString()}</span>}
            </div>
          </div>
              <button onClick={() => selectSection(sectionIndex + 1)} disabled={loading || sectionIndex >= sections.length - 1}>下一章节</button>
            </div>
          )}
          {activeStage === 2 && (
            <div>
              <h4>逐题回答</h4>
              <p className="fund-field-hint">逐题补充已掌握的事实、数据或方案，有助于提升本章内容质量。若无可提供信息，可留空或如实填写：不清楚。</p>
              {(current?.inputs || []).length === 0 && <p className="fund-no-question-hint">当前章节没有规划问题，可以直接生成基础草稿。</p>}
              {(current?.inputs || []).slice(0, 20).map((key, index) => (
                <div key={`${index}-${key}`} style={{ marginBottom: 14 }}>
                  <label style={{ display: 'block', fontWeight: 600, marginBottom: 4 }}>{index + 1}. {key}</label>
                  <textarea
                    style={{ width: '100%' }}
                    rows={3}
                    placeholder="请填写与本章有关的事实、依据或已有方案；若无可提供信息，可留空或如实填写：不清楚"
                    value={answers[key] || ''}
                    onChange={(e) => setAnswers(previous => ({ ...previous, [key]: e.target.value }))}
                  />
                </div>
              ))}
              <div style={{ margin: '16px 0' }}>
                <label htmlFor={`file-${current?.id || 'section'}`}>上传本章补充材料，可选</label>
                <input id={`file-${current?.id || 'section'}`} type="file" accept=".pdf,.docx,.txt" onChange={onUploadFile} />
                {uploading && <span className='fund-api-action-feedback'><span className='fund-spinner' aria-hidden='true' />正在上传</span>}
                {uploadError && <div>{uploadError}</div>}
                {current && filesBySection[current.id]?.length > 0 && (
                  <ul>
                    {filesBySection[current.id].map((file, index) => (
                      <li key={index}>
                        <a href={file.url} target="_blank" rel="noopener noreferrer">{file.name || `file-${index + 1}`}</a>
                        {file.ocr_text && (
                          <div>
                            <div>材料文字预览</div>
                            <textarea style={{ width: '100%' }} readOnly rows={3} value={file.ocr_text} />
                          </div>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="fund-generation-action">
                <button onClick={writeDraft} disabled={loading || currentSection?.locked}>生成本章草稿</button>
                <GenerationFeedback action="write" status={generationStatus} sectionId={current?.id} />
              </div>
              {currentSection?.locked && <span> 当前章节已审批锁定</span>}
              <h4>当前草稿</h4>
              <MarkdownPreview value={draft || persistedDraft} testId="draft-text" />
              <EvidencePanel evidence={currentEvidence} />
            </div>
          )}

          {activeStage === 3 && (
            <div>
              <h4>人工审核修改要求</h4>
              <p className="fund-field-hint">可选。请说明需要修改、补充或删减的具体内容；暂无修改要求时可留空并直接提交章节审批。</p>
              <textarea style={{ width: '100%' }} rows={3} placeholder="例如：补充前期基础，明确技术路线，并删减重复表述" value={changeReq} onChange={(e) => setChangeReq(e.target.value)} />
              <div style={{ display: 'flex', gap: 8, margin: '8px 0 16px' }}>
                <button onClick={applyChanges} disabled={loading || currentSection?.locked || !(draft || persistedDraft) || !changeReq.trim()}>按要求修订</button>
                <button onClick={submitForApproval} disabled={loading || currentSection?.locked || currentApprovalPending || !(draft || persistedDraft)}>提交章节审批</button>
                <button onClick={() => setActiveStage(2)}>返回问答</button>
              </div>
              {currentApprovalPending && <p>当前章节已提交人工审批，请在上方待审批章节卡片中处理。</p>}
              <div className='fund-draft-heading-row'>
                <h4>当前草稿（可直接在下方进行编辑）</h4>
                <GenerationFeedback action="revise" status={generationStatus} sectionId={current?.id} />
              </div>
              <textarea
                className="fund-current-draft-editor"
                data-testid="current-draft-editor"
                rows={18}
                value={draft || persistedDraft}
                onChange={(event) => setDraft(event.target.value)}
                disabled={loading || currentSection?.locked}
              />
              <div className="fund-generation-action">
                <button onClick={saveCurrentDraft} disabled={loading || currentSection?.locked || !(draft || persistedDraft)}>保存当前草稿</button>
              </div>
              <details className="fund-previous-draft">
                <summary>查看修改前草稿</summary>
                <MarkdownPreview value={previousDraft} />
              </details>
            </div>
          )}

          {activeStage === 4 && (
            <div>
              <h4>最终定稿</h4>
              <div>已审批章节：{approvedSectionCount} / {sections.length}</div>
              {!allApproved && <p>所有章节完成人工审批后才能生成最终稿。</p>}
              {allApproved && (
                <>
                  <p className='fund-final-approval-status'>所有章节均已人工审核完毕。请先完成全文草稿审批，再生成最终定稿。</p>
                  {!fullDraftLoaded && <p className='fund-status-message'>正在载入审批后全文草稿。</p>}
                  {fullDraftLoaded && !fullDraftApproved && (
                    <>
                      <section className='fund-full-draft-workspace'>
                        <div className='fund-draft-heading-row'>
                          <div>
                            <h4>审批后全文草稿</h4>
                            <p className='fund-field-hint'>点击章节标题可追溯到对应章节，解除该章节的旧审批锁定后继续修改与重新审批。</p>
                          </div>
                        </div>
                        <FullDraftPreview
                          value={fullDraft}
                          sections={sections}
                          onSectionClick={reopenApprovedSection}
                          disabled={loading || proposalFinalized}
                        />
                        <h4>全文审核修改要求</h4>
                        <p className='fund-field-hint'>可选。请说明需要调整的全文逻辑、章节衔接、重复内容或排版表达。</p>
                        <textarea
                          className='fund-current-draft-editor'
                          rows={4}
                          placeholder='例如：统一各章术语，补充章节衔接，并删除重复论述'
                          value={fullChangeReq}
                          onChange={event => setFullChangeReq(event.target.value)}
                          disabled={loading || fullDraftApprovalPending}
                        />
                        <div className='fund-generation-action'>
                          <button type='button' onClick={() => applyFullDraftChanges()} disabled={loading || fullDraftApprovalPending || !fullChangeReq.trim()}>
                            {generationStatus.action === 'full-manual-revise' && generationStatus.state === 'loading'
                              ? <><span className='fund-spinner' aria-hidden='true' />正在修订全文</>
                              : '按要求修订全文'}
                          </button>
                          <GenerationFeedback action='full-manual-revise' status={generationStatus} sectionId='__full__' hideDone />
                          <GenerationFeedback action='full-pre-review-revise' status={generationStatus} sectionId='__full__' hideDone />
                          <button onClick={submitFullDraftForApproval} disabled={loading || fullDraftApprovalPending || !fullDraft.trim()}>提交全文审批</button>
                        </div>
                        {previousFullDraft && (
                          <details className='fund-previous-draft'>
                            <summary>查看修改前全文草稿</summary>
                            <MarkdownPreview value={previousFullDraft} />
                          </details>
                        )}
                      </section>
                      <SectionApprovalPanel
                        tasks={fullDraftApprovalTasks}
                        title='待审批全文草稿'
                        testId='full-draft-approval-tasks'
                        onDecision={decideHumanTask}
                        onPreReview={runSectionPreReview}
                        onAcceptPreReview={acceptSectionPreReview}
                        onDismissPreReview={dismissSectionPreReview}
                        onApplyPreReview={applySectionPreReview}
                        loading={loading}
                      />
                      {fullDraftApprovalPending && <p className='fund-status-message'>全文草稿已提交审批，请在上方审批卡片中处理。</p>}
                    </>
                  )}
                  {fullDraftLoaded && fullDraftApproved && (
                    <section className='fund-full-draft-workspace'>
                      <h4>定稿预览</h4>
                      <MarkdownPreview value={formattedText || fullDraft} testId='final-preview' />
                      {formattedText && (
                        <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                          <button onClick={() => onExport?.(proposal.id, 'md')} disabled={exporting}>{exporting ? <><span className='fund-spinner' aria-hidden='true' />正在导出</> : '下载 Markdown'}</button>
                          <button onClick={() => onExport?.(proposal.id, 'docx')} disabled={exporting}>{exporting ? <><span className='fund-spinner' aria-hidden='true' />正在导出</> : '下载 DOCX'}</button>
                          <button onClick={() => onExport?.(proposal.id, 'pdf')} disabled={exporting}>{exporting ? <><span className='fund-spinner' aria-hidden='true' />正在导出</> : '下载 PDF'}</button>
                        </div>
                      )}
                    </section>
                  )}
                  {fullDraftApproved && !proposalFinalized && (
                    <>
                      <label className="fund-inline-field">
                        <span>排版模板要求，可选</span>
                        <small className="fund-field-hint">可补充封面、字体、章节层级或单位模板要求；无明确要求可留空。</small>
                        <input style={{ width: '100%', margin: '6px 0 12px' }} placeholder="例如：一级标题使用黑体四号，二级标题使用宋体小四号，英文使用Times New Roman小四号" value={templateHint} onChange={(e) => setTemplateHint(e.target.value)} />
                      </label>
                      <div className="fund-generation-action">
                        <button onClick={runFinalFormatting} disabled={loading}>生成最终定稿</button>
                        <GenerationFeedback action="format" status={generationStatus} hideDone />
                      </div>
                    </>
                  )}
                </>
              )}
            </div>
          )}

          {error && <div className="fund-status-message is-error" role="alert">{error}</div>}
        </div>
      )}
    </div>
  )
}

export function Proposals({ token, selectedOrgId }) {
  const [items, setItems] = useState([])
  const [loadedOrgId, setLoadedOrgId] = useState('')
  const [loading, setLoading] = useState(false)
  const [creating, setCreating] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [applicationSystem, setApplicationSystem] = useState('')
  const [exporting, setExporting] = useState(null)
  const [mutatingProjectId, setMutatingProjectId] = useState(null)
  const [fmtById, setFmtById] = useState({})
  const [openAuthorForId, setOpenAuthorForId] = useState(null)
  const [showTrash, setShowTrash] = useState(false)
  const [actionMessage, setActionMessage] = useState('')
  const orgId = selectedOrgId !== undefined
    ? String(selectedOrgId || '')
    : (localStorage.getItem('orgId') || '')
  const activeOrgIdRef = useRef(orgId)
  activeOrgIdRef.current = orgId
  const archive = async (p) => {
    setMutatingProjectId(p.id)
    try {
      await api(`/proposals/${p.id}/`, { method: 'PATCH', token, orgId: orgId || undefined, body: { state: 'archived' } })
      await refresh()
      setActionMessage(`项目 ${p.content?.meta?.title || `编号 ${p.workspace_number || '待分配'}`} 已移入回收站`)
    } catch (e) {
      setActionMessage(`归档失败：${e?.data?.error || e.message}`)
    } finally {
      setMutatingProjectId(null)
    }
  }
  const unarchive = async (p) => {
    setMutatingProjectId(p.id)
    try {
      await api(`/proposals/${p.id}/`, { method: 'PATCH', token, orgId: orgId || undefined, body: { state: 'draft' } })
      await refresh()
      setActionMessage(`项目 ${p.content?.meta?.title || `编号 ${p.workspace_number || '待分配'}`} 已恢复`)
    } catch (e) {
      setActionMessage(`恢复失败：${e?.data?.error || e.message}`)
    } finally {
      setMutatingProjectId(null)
    }
  }
  const requestErrorMessage = (error, action) => {
    if (error?.status === 401) return `${action}失败：登录状态已失效，请重新登录后再试。`
    if (error?.status === 403) return `${action}失败：当前账号无权操作这个工作区，请重新选择后再试。`
    if (error?.status === 400 && error?.data?.workspace === 'workspace_required') {
      return `${action}失败：请先选择工作区。`
    }
    return `${action}失败：${error?.data?.error || error?.message || '请稍后重试。'}`
  }
  const refresh = async () => {
    const requestOrgId = orgId
    setLoading(true)
    setActionMessage('')
    try {
      const data = await api('/proposals/', { token, orgId: requestOrgId || undefined })
      const nextItems = Array.isArray(data) ? data : data.results || []
      if (activeOrgIdRef.current !== requestOrgId) return null
      setItems(nextItems)
      setLoadedOrgId(requestOrgId)
      setOpenAuthorForId(currentId => {
        if (currentId && nextItems.some(item => item.id === currentId)) return currentId
        return nextItems.find(item => item.state !== 'archived')?.id || null
      })
      return nextItems
    } catch (e) {
      if (activeOrgIdRef.current !== requestOrgId) return null
      setActionMessage(requestErrorMessage(e, '加载项目'))
      return null
    } finally {
      if (activeOrgIdRef.current === requestOrgId) setLoading(false)
    }
  }
  const doExport = async (proposalId, fmt='pdf') => {
    setExporting(proposalId)
    try {
      const job = await api('/exports', { method: 'POST', token, orgId: orgId || undefined, body: { proposal_id: proposalId, format: fmt } })
      if (job.download_url) {
        await downloadExport(job.download_url, { token, orgId: orgId || undefined })
        return
      }
      if (job.url) {
        safeOpenExternal(job.url)
        return
      }
      const id = job.id
      for (let i = 0; i < 20; i++) {
        await new Promise(r => setTimeout(r, 500))
        const status = await api(`/exports/${id}`, { token, orgId: orgId || undefined })
        if (status.download_url) {
          await downloadExport(status.download_url, { token, orgId: orgId || undefined })
          return
        }
        if (status.url) {
          safeOpenExternal(status.url)
          return
        }
      }
  alert(t('ui.errors.export_still_processing'))
  } catch (e) {
      alert(`导出失败：${e?.data?.error || e.message}`)
    } finally {
      setExporting(null)
    }
  }
  const createOne = async () => {
    const title = newTitle.trim()
    if (!title) {
      alert('请先输入项目标题')
      return
    }
    if (!applicationSystem) {
      alert('请选择申报体系')
      return
    }
    setCreating(true)
    try {
      const created = await api('/proposals/', {
        method: 'POST',
        token,
        orgId: orgId || undefined,
        body: {
          content: { meta: { title, application_system: applicationSystem }, sections: {} },
          schema_version: 'v1',
        },
      })
      if (created?.id) setOpenAuthorForId(created.id)
      setNewTitle('')
      setApplicationSystem('')
      await refresh()
    } catch (e) {
      setActionMessage(requestErrorMessage(e, '新建申请'))
    } finally {
      setCreating(false)
    }
  }
  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem('exportFormats') || '{}')
      if (saved && typeof saved === 'object') setFmtById(saved)
    } catch {}
  }, [])
  useEffect(() => {
    try { localStorage.setItem('exportFormats', JSON.stringify(fmtById)) } catch {}
  }, [fmtById])
  useEffect(() => { refresh() }, [token, orgId])
  const currentItems = loadedOrgId === orgId ? items : []
  const activeProposal = currentItems.find(item => item.id === openAuthorForId)
  const activeItems = currentItems.filter(item => item.state !== 'archived')
  const archivedItems = currentItems.filter(item => item.state === 'archived')
  return (
    <section className="fund-workspace">
      <aside className="fund-project-sidebar">
        <div className="fund-sidebar-heading">
          <div>
            <h2>我的基金申请</h2>
            <p></p>
          </div>
          <button className="fund-primary-button fund-new-button" disabled={creating} onClick={createOne}>{creating ? <><span className="fund-spinner" aria-hidden="true" />正在新建</> : '新建申请'}</button>
        </div>

        <div className="fund-new-proposal-fields">
          <label className="fund-new-title-label" htmlFor="new-proposal-title">
            <span>项目标题 <b className="fund-required-marker" aria-hidden="true">*</b></span>
            <small className="fund-field-hint"></small>
            <input
              id="new-proposal-title"
              className="fund-new-title"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="输入新项目标题"
            />
          </label>
          <fieldset className="fund-application-system" aria-required="true">
            <legend>申报体系 <b className="fund-required-marker" aria-hidden="true">*</b></legend>
            <p className="fund-field-hint">本项为必填。选择后，系统会按对应申报体系调整写作侧重点。</p>
            {APPLICATION_SYSTEM_OPTIONS.map(option => (
              <label key={option.value}>
                <input
                  type="radio"
                  name="application-system"
                  value={option.value}
                  checked={applicationSystem === option.value}
                  onChange={(event) => setApplicationSystem(event.target.value)}
                />
                {option.label}
              </label>
            ))}
          </fieldset>
        </div>

        {loading && <div className="fund-loading" role="status"><span className="fund-spinner" aria-hidden="true" />正在加载</div>}
        {actionMessage && <div className="fund-action-message" role="status">{actionMessage}</div>}
        <div className="fund-project-list">
          {activeItems.map(p => (
            <article className={`fund-project-card ${openAuthorForId === p.id ? 'is-active' : ''}`} key={p.id}>
              <button className="fund-project-open" onClick={() => setOpenAuthorForId(p.id)}>
                <strong>{(p.content?.meta?.title) || t('ui.common.untitled')}</strong>
                <span>编号 {p.workspace_number || '待分配'} · {applicationSystemLabel(p.content?.meta?.application_system)} · {p.state === 'archived' ? '已归档' : '草稿'}</span>
              </button>
              <div className="fund-project-actions">
                <select aria-label={`format-${p.id}`} value={fmtById[p.id] || 'pdf'} onChange={(e) => setFmtById(s => ({ ...s, [p.id]: e.target.value }))}>
                  <option value="pdf">{t('ui.dashboard.format_pdf')}</option>
                  <option value="docx">{t('ui.dashboard.format_docx')}</option>
                  <option value="md">{t('ui.dashboard.format_md')}</option>
                </select>
                <button
                  disabled={exporting === p.id || !p.sections?.length || p.sections.some(section => section.state !== 'approved')}
                  onClick={() => doExport(p.id, fmtById[p.id] || 'pdf')}
                >
                  {exporting === p.id ? <><span className="fund-spinner" aria-hidden="true" />正在导出</> : '导出'}
                </button>
                <button onClick={() => setOpenAuthorForId(p.id)}>打开撰写区</button>
                {p.state !== 'archived' ? (
                  <button className="fund-danger-button" disabled={mutatingProjectId === p.id} onClick={() => archive(p)}>{mutatingProjectId === p.id ? <><span className="fund-spinner" aria-hidden="true" />正在归档</> : '归档'}</button>
                ) : (
                  <button disabled={mutatingProjectId === p.id} onClick={() => unarchive(p)}>{mutatingProjectId === p.id ? <><span className="fund-spinner" aria-hidden="true" />正在恢复</> : '取消归档'}</button>
                )}
              </div>
            </article>
          ))}
        </div>

        {activeItems.length === 0 && !loading && (
          <div className="fund-empty-sidebar">还没有申请书，点击新建申请开始</div>
        )}

        <div className="fund-sidebar-footer">
          <button className="fund-trash-toggle" onClick={() => setShowTrash(value => !value)}>
            回收站（{archivedItems.length}）
          </button>
          {showTrash && (
            <div className="fund-trash">
              <h3>回收站</h3>
              {archivedItems.length === 0 && <p>回收站为空</p>}
              {archivedItems.map(p => (
                <article className="fund-project-card" key={p.id}>
                  <strong>{p.content?.meta?.title || t('ui.common.untitled')}</strong>
                  <div className="fund-project-actions">
                    <button disabled={mutatingProjectId === p.id} onClick={() => unarchive(p)}>{mutatingProjectId === p.id ? <><span className="fund-spinner" aria-hidden="true" />正在恢复</> : '恢复项目'}</button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </div>
      </aside>

      <main className="fund-workspace-main">
        {activeProposal ? (
          <AuthorPanel
            key={`${orgId}:${activeProposal.id}`}
            token={token}
            orgId={orgId || undefined}
            proposal={activeProposal}
            onSaved={async () => { await refresh() }}
            onExport={doExport}
            exporting={exporting === activeProposal.id}
          />
        ) : (
          <div className="fund-empty-workspace">
            <div className="fund-empty-icon">NSFC</div>
            <h2>开始撰写基金申请书</h2>
            <p>新建申请后，系统将引导你依次完成规划、逐章写作、人工修订和定稿导出。</p>
            <button className="fund-primary-button" disabled={creating} onClick={createOne}>
              {creating ? <><span className="fund-spinner" aria-hidden="true" />正在新建</> : '新建第一份申请'}
            </button>
          </div>
        )}
      </main>
    </section>
  )
}

export default function Dashboard({ token, selectedOrgId, onSelectOrg }) {
  return (
    <div>
      <div>
        <Proposals token={token} selectedOrgId={selectedOrgId} />
      </div>
    </div>
  )
}

// Named exports for tests
export { AuthorPanel }
export { default as SectionDiff } from '../components/SectionDiff.jsx'
