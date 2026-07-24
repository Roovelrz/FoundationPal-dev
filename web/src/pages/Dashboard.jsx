import { useEffect, useState } from 'react'
import { api, apiMaybeAsync, apiUpload, safeOpenExternal } from '../lib/core.js'
import { t } from '../keys.generated'

const normalizePlan = (raw) => ({
  schema_version: raw?.schema_version || 'v1',
  sections: (raw?.sections || []).map(section => ({
    ...section,
    id: section.id || section.key,
    inputs: (section.inputs || section.questions || []).slice(0, 20),
  })),
})

const planFromProposal = (proposal) => {
  if (!proposal?.sections?.length) return null
  return normalizePlan({
    schema_version: proposal.schema_version,
    sections: proposal.sections.map(section => ({
      id: section.key,
      title: section.title,
      inputs: section.inputs || [],
    })),
  })
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
      style={{ padding: 16, border: '1px solid #d8dee9', borderRadius: 8, background: '#fff', minHeight: 120 }}
    >
      {value ? value.split('\n').map((line, index) => {
        if (line.startsWith('### ')) return <h3 key={index}>{renderInline(line.slice(4))}</h3>
        if (line.startsWith('## ')) return <h2 key={index}>{renderInline(line.slice(3))}</h2>
        if (line.startsWith('# ')) return <h1 key={index}>{renderInline(line.slice(2))}</h1>
        if (line.startsWith('- ')) return <div key={index}>• {renderInline(line.slice(2))}</div>
        if (!line.trim()) return <div key={index} style={{ height: 8 }} />
        return <p key={index}>{renderInline(line)}</p>
      }) : <span style={{ color: '#777' }}>暂无内容</span>}
    </div>
  )
}

function GenerationFeedback({ action, status }) {
  if (status.action !== action) return null
  if (status.state === 'loading') {
    return (
      <span className="fund-generation-feedback" role="status">
        <span className="fund-spinner" aria-hidden="true" />
        正在深度思考中
      </span>
    )
  }
  if (status.state === 'done') {
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
          <summary>{item.cited_by_model ? '已引用' : '已注入'} 路 {item.document_name} 路 第 {item.page_start}-{item.page_end} 页</summary>
          <p>{item.section_title || '未识别章节标题'}</p>
          <p>{item.text}</p>
        </details>
      ))}
    </section>
  )
}

const grillFieldLabels = {
  funding_category: '申报类别',
  research_direction: '研究方向',
  core_problem: '核心问题',
  research_foundation: '已有研究基础',
  available_equipment: '可使用设备',
  project_duration: '项目周期',
  budget_range: '预算范围',
  expected_outcomes: '预期成果',
  prohibited_content: '禁止生成的内容',
  change_goal: '修改目标',
  preserve: '必须保留的内容',
  constraints: '修改限制',
}

function GrillPanel({ mode, proposal, section, token, orgId, onImport }) {
  const [session, setSession] = useState(null)
  const [answers, setAnswers] = useState({})
  const [loading, setLoading] = useState(false)

  const load = async () => {
    if (!proposal?.id || (mode === 'revision' && !section?.key)) return
    const query = new URLSearchParams({ proposal_id: proposal.id, mode })
    if (mode === 'revision') query.set('section_key', section.key)
    try {
      const result = await api(`/ai/grill?${query.toString()}`, { token, orgId: orgId || undefined })
      setSession(result)
      setAnswers(result.collected_answers || {})
    } catch {}
  }

  useEffect(() => { load() }, [mode, proposal?.id, section?.key, token, orgId])

  const submit = async ({ skip = false, finish = false, confirm = false } = {}) => {
    if (!proposal?.id) return
    setLoading(true)
    try {
      const result = await api('/ai/grill', {
        method: 'POST',
        token,
        orgId: orgId || undefined,
        body: {
          proposal_id: proposal.id,
          mode,
          section_key: mode === 'revision' ? section?.key : undefined,
          answers,
          skip,
          finish,
          confirm,
        },
      })
      setSession(result)
      setAnswers(result.collected_answers || {})
    } finally {
      setLoading(false)
    }
  }

  const question = session?.question
  return (
    <div className="fund-grill-panel" data-testid={`${mode}-grill`} style={{ margin: '12px 0', padding: 12, border: '1px solid #cbd5e1', borderRadius: 8, background: '#f8fafc' }}>
      <strong>{mode === 'planning' ? '规划澄清' : '本章节修改澄清'}</strong>
      {mode === 'revision' && <div style={{ marginTop: 4 }}>当前草稿已载入，仅生成修改建议。</div>}
      {!session && <div style={{ marginTop: 6 }}>正在载入澄清状态</div>}
      {question && (
        <div style={{ marginTop: 8 }}>
          <div>{question.index} / {session.max_questions}　{question.prompt}</div>
          {question.fields.map(field => (
            <label key={field} style={{ display: 'block', marginTop: 8 }}>
              {grillFieldLabels[field] || field}
              <textarea
                style={{ display: 'block', width: '100%', marginTop: 4 }}
                rows={2}
                value={answers[field] || ''}
                onChange={(event) => setAnswers(previous => ({ ...previous, [field]: event.target.value }))}
              />
            </label>
          ))}
          <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
            <button onClick={() => submit()} disabled={loading}>保存并继续</button>
            <button onClick={() => submit({ skip: true })} disabled={loading}>跳过本题</button>
            <button onClick={() => submit({ finish: true })} disabled={loading}>结束澄清</button>
          </div>
        </div>
      )}
      {session?.completion_reason && (
        <div style={{ marginTop: 8 }}>
          <div>澄清结束：{session.completion_reason}</div>
          {mode === 'planning' && !session.confirmed && <button onClick={() => submit({ confirm: true })} disabled={loading}>确认并用于章节规划</button>}
          {mode === 'revision' && session.suggestion && (
            <>
              <textarea aria-label="修改建议" style={{ width: '100%', marginTop: 8 }} readOnly rows={4} value={session.suggestion} />
              <button onClick={() => onImport?.(session.suggestion)} disabled={loading}>导入到整体修订要求</button>
            </>
          )}
        </div>
      )}
    </div>
  )
}

function HumanTaskPanel({ tasks, onDecision, loading }) {
  const [edits, setEdits] = useState({})
  if (!tasks.length) return null
  return (
    <section style={{ margin: '12px 0', padding: 12, border: '1px solid #f59e0b', borderRadius: 8, background: '#fffbeb' }}>
      <h4 style={{ marginTop: 0 }}>待人工确认</h4>
      {tasks.map(task => (
        <details key={task.id} open>
          <summary>{task.node}</summary>
          <div>中断前输入：{JSON.stringify(task.input)}</div>
          <div>模型输出：{JSON.stringify(task.model_output)}</div>
          <textarea
            style={{ width: '100%', marginTop: 8 }}
            rows={2}
            placeholder="编辑后的确认内容，可选"
            value={edits[task.id] || ''}
            onChange={(event) => setEdits(previous => ({ ...previous, [task.id]: event.target.value }))}
          />
          <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
            <button onClick={() => onDecision(task, 'approve')} disabled={loading}>批准</button>
            <button onClick={() => onDecision(task, 'edit', { instruction: edits[task.id] || '' })} disabled={loading}>编辑后校验</button>
            <button onClick={() => onDecision(task, 'reject')} disabled={loading}>拒绝</button>
          </div>
        </details>
      ))}
    </section>
  )
}

function AuthorPanel({ token, orgId, proposal, onSaved, onExport, exporting }) {
  const [plan, setPlan] = useState(() => planFromProposal(proposal))
  const [activeStage, setActiveStage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [sectionIndex, setSectionIndex] = useState(0)
  const [answersBySection, setAnswersBySection] = useState(() => Object.fromEntries(
    (proposal?.sections || []).map(section => [section.key, section.answers || {}])
  ))
  const [draftsBySection, setDraftsBySection] = useState(() => Object.fromEntries(
    (proposal?.sections || []).map(section => [section.key, section.draft_content || section.approved_content || ''])
  ))
  const [changeReq, setChangeReq] = useState('')
  const [grantUrl, setGrantUrl] = useState('')
  const [textSpec, setTextSpec] = useState('')
  const [lastSavedAt, setLastSavedAt] = useState(null)
  const [templateHint, setTemplateHint] = useState('')
  const [formattedText, setFormattedText] = useState('')
  const [filesBySection, setFilesBySection] = useState({})
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const [note, setNote] = useState('')
  const [proposalTitle, setProposalTitle] = useState(proposal?.content?.meta?.title || '')
  const [me, setMe] = useState(null)
  const [generationStatus, setGenerationStatus] = useState({ action: '', state: '' })
  const [evidenceBySection, setEvidenceBySection] = useState({})
  const [humanTasks, setHumanTasks] = useState([])

  const sections = plan?.sections || []
  const current = sections[sectionIndex]
  const persistedSections = proposal?.sections || []
  const persistedByKey = Object.fromEntries(persistedSections.map(section => [section.key, section]))
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
  const prevText = currentSection?.approved_content
    || currentSection?.draft_content
    || approvedById?.[current?.id]?.content
    || ''
  const approvedSectionCount = sections.filter(
    section => persistedByKey[section.id]?.state === 'approved'
  ).length
  const allApproved = sections.length > 0 && approvedSectionCount === sections.length
  const currentEvidence = current ? (evidenceBySection[current.id] || []) : []

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
  }, [proposal?.id, proposal?.sections])

  useEffect(() => {
    if (!currentSection?.id || !current) return
    api(`/ai/sections/${currentSection.id}/evidence`, { token, orgId: orgId || undefined })
      .then(result => setEvidenceBySection(previous => ({ ...previous, [current.id]: result.evidence || [] })))
      .catch(() => {})
  }, [current?.id, currentSection?.id, orgId, token])

  useEffect(() => {
    // Initialize note from proposal.content.meta.note
    const n = proposal?.content?.meta?.note
    setNote(typeof n === 'string' ? n : '')
    setProposalTitle(proposal?.content?.meta?.title || '')
  }, [proposal?.id])

  useEffect(() => {
    setFormattedText(proposal?.final_markdown || '')
  }, [proposal?.id, proposal?.final_markdown])

  const refreshHumanTasks = async () => {
    if (!proposal?.id) return
    try {
      const result = await api(`/ai/human-tasks?proposal_id=${proposal.id}`, { token, orgId: orgId || undefined })
      setHumanTasks(result.tasks || [])
    } catch {}
  }

  useEffect(() => { refreshHumanTasks() }, [proposal?.id, token, orgId])

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
      const info = await apiUpload('/files', { token, orgId: orgId || undefined, file })
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

  const startPlan = async () => {
    setLoading(true)
    setError('')
    setGenerationStatus({ action: 'plan', state: 'loading' })
    try {
      const body = grantUrl
    ? { proposal_id: proposal.id, grant_url: grantUrl }
    : { proposal_id: proposal.id, text_spec: textSpec || 'General grant' } // fallback literal stays internal
      const p = await apiMaybeAsync('/ai/plan', { method: 'POST', token, orgId: orgId || undefined, body })
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
      setGenerationStatus({ action: 'plan', state: 'done' })
  } catch {
  setGenerationStatus({ action: 'plan', state: 'error' })
  setError(t('ui.errors.plan_load_failed'))
    } finally {
      setLoading(false)
    }
  }

  const writeDraft = async () => {
    if (!current) return
    setLoading(true)
    setError('')
    setGenerationStatus({ action: 'write', state: 'loading' })
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
      setDraft(res?.draft_text || '')
      if (res?.evidence) setEvidenceBySection(previous => ({ ...previous, [current.id]: res.evidence }))
      await onSaved?.()
      setActiveStage(3)
      setGenerationStatus({ action: 'write', state: 'done' })
  } catch {
  setGenerationStatus({ action: 'write', state: 'error' })
  setError(t('ui.errors.write_failed'))
    } finally { setLoading(false) }
  }

  const applyChanges = async () => {
    if (!current) return
    setLoading(true)
    setError('')
    setGenerationStatus({ action: 'revise', state: 'loading' })
    try {
      const res = await apiMaybeAsync('/ai/revise', {
        method: 'POST',
        token,
        orgId: orgId || undefined,
        body: {
          proposal_id: proposal.id,
          section_id: current.id,
          base_text: draft || prevText,
          change_request: changeReq,
          file_refs: (current && filesBySection[current.id]) ? filesBySection[current.id] : [],
        },
      })
      setDraft(res?.draft_text || draft)
      await onSaved?.()
      setGenerationStatus({ action: 'revise', state: 'done' })
  } catch {
  setGenerationStatus({ action: 'revise', state: 'error' })
  setError(t('ui.errors.revise_failed'))
    } finally { setLoading(false) }
  }

  const approveAndSave = async () => {
    if (!currentSection?.id) return
    setLoading(true)
    setError('')
    try {
      await api(`/sections/${currentSection.id}/promote`, {
        method: 'POST',
        token,
        orgId: orgId || undefined,
      })
      setLastSavedAt(new Date())
      await onSaved?.()
      if (sectionIndex < sections.length - 1) {
        selectSection(sectionIndex + 1)
        setActiveStage(2)
      } else {
        setActiveStage(4)
      }
  } catch {
  setError(t('ui.errors.save_failed'))
    } finally { setLoading(false) }
  }

  const saveNote = async () => {
    // Patch proposal content.meta.note without touching sections
    const content = { ...(proposal.content || {}) }
    content.meta = { ...(content.meta || {}), note }
    const body = { content, schema_version: proposal.schema_version || plan?.schema_version || 'v1' }
    setLoading(true)
    setError('')
    try {
      await api(`/proposals/${proposal.id}/`, { method: 'PATCH', token, orgId: orgId || undefined, body })
      setLastSavedAt(new Date())
      await onSaved?.()
    } catch {
  setError(t('ui.errors.save_note_failed'))
    } finally { setLoading(false) }
  }

  const saveTitle = async () => {
    const title = proposalTitle.trim()
    if (!title) {
      setError('项目标题不能为空')
      return
    }
    const content = { ...(proposal.content || {}) }
    content.meta = { ...(content.meta || {}), title }
    setLoading(true)
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
      setLoading(false)
    }
  }

  const runFinalFormatting = async () => {
    if (!allApproved) return
    setLoading(true)
    setError('')
    setGenerationStatus({ action: 'format', state: 'loading' })
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
      setGenerationStatus({ action: 'format', state: 'done' })
  } catch {
  setGenerationStatus({ action: 'format', state: 'error' })
  setError(t('ui.errors.final_format_failed'))
    } finally { setLoading(false) }
  }

  const decideHumanTask = async (task, action, editedInput = {}) => {
    setLoading(true)
    setError('')
    try {
      await api(`/ai/human-tasks/${task.id}/decision`, {
        method: 'POST',
        token,
        orgId: orgId || undefined,
        body: { thread_id: task.thread_id, action, edited_input: editedInput },
      })
      await refreshHumanTasks()
    } catch {
      setError('人工决策提交失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fund-author-panel" style={{ marginTop: 16, padding: 20, border: '1px solid #d8dee9', borderRadius: 12, background: '#f7f9fc' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
        <div>
          <h3 style={{ margin: 0 }}>基金申请书工作区</h3>
          <div className="fund-title-editor">
            <input
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
          <div>内部备注</div>
          <textarea style={{ width: '100%' }} data-testid="note-text" rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="添加供自己或协作者查看的备注" />
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
      <HumanTaskPanel tasks={humanTasks} onDecision={decideHumanTask} loading={loading} />
      {generationStatus.state === 'done' && (
        (generationStatus.action === 'plan' && activeStage !== 1)
        || (generationStatus.action === 'write' && activeStage !== 2)
        || (generationStatus.action === 'revise' && activeStage !== 3)
        || (generationStatus.action === 'format' && activeStage !== 4)
      ) && (
        <div className="fund-generation-summary">
          <GenerationFeedback action={generationStatus.action} status={generationStatus} />
        </div>
      )}

      {activeStage === 1 && (
        <div style={{ padding: 16, background: '#fff', borderRadius: 8 }}>
          <h4>规划申请书章节</h4>
          <input style={{ width: '100%', marginBottom: 8 }} value={grantUrl} onChange={(e) => setGrantUrl(e.target.value)} placeholder="基金指南网址，可选" />
          <textarea style={{ width: '100%' }} rows={5} value={textSpec} onChange={(e) => setTextSpec(e.target.value)} placeholder="粘贴基金指南、申报要求或研究方向说明" />
          <GrillPanel mode="planning" proposal={proposal} token={token} orgId={orgId} />
          <div className="fund-generation-action">
            <button onClick={startPlan} disabled={loading}>生成章节规划</button>
            <GenerationFeedback action="plan" status={generationStatus} />
          </div>
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
              {(current?.inputs || []).length === 0 && <p>当前章节没有规划问题，可以直接生成基础草稿。</p>}
              {(current?.inputs || []).slice(0, 20).map((key, index) => (
                <div key={`${index}-${key}`} style={{ marginBottom: 14 }}>
                  <label style={{ display: 'block', fontWeight: 600, marginBottom: 4 }}>{index + 1}. {key}</label>
                  <textarea
                    style={{ width: '100%' }}
                    rows={3}
                    value={answers[key] || ''}
                    onChange={(e) => setAnswers(previous => ({ ...previous, [key]: e.target.value }))}
                  />
                </div>
              ))}
              <div style={{ margin: '16px 0' }}>
                <label htmlFor={`file-${current?.id || 'section'}`}>上传本章参考材料</label>
                <input id={`file-${current?.id || 'section'}`} type="file" accept=".pdf,.docx,.txt,image/*" onChange={onUploadFile} />
                {uploading && <span> 正在上传</span>}
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
                <GenerationFeedback action="write" status={generationStatus} />
              </div>
              {currentSection?.locked && <span> 当前章节已审批锁定</span>}
              <h4>当前草稿</h4>
              <MarkdownPreview value={draft || prevText} testId="draft-text" />
              <EvidencePanel evidence={currentEvidence} />
            </div>
          )}

          {activeStage === 3 && (
            <div>
              <h4>人工审核修改要求</h4>
              <textarea style={{ width: '100%' }} rows={3} placeholder="请输入需要修改、补充或删减的具体要求" value={changeReq} onChange={(e) => setChangeReq(e.target.value)} />
              <details style={{ marginTop: 8 }}>
                <summary>针对本章节澄清修改目标</summary>
                <GrillPanel
                  mode="revision"
                  proposal={proposal}
                  section={current}
                  token={token}
                  orgId={orgId}
                  onImport={(suggestion) => setChangeReq(suggestion)}
                />
              </details>
              <div style={{ display: 'flex', gap: 8, margin: '8px 0 16px' }}>
                <button onClick={applyChanges} disabled={loading || currentSection?.locked || !(draft || prevText)}>按要求修订</button>
                <GenerationFeedback action="revise" status={generationStatus} />
                <button onClick={approveAndSave} disabled={loading || currentSection?.locked || !(draft || prevText)}>审批并保存</button>
                <button onClick={() => setActiveStage(2)}>返回问答</button>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
                <div>
                  <h4>修改前</h4>
                  <MarkdownPreview value={prevText} />
                </div>
                <div>
                  <h4>修订后</h4>
                  <MarkdownPreview value={draft || prevText} testId="draft-text" />
                </div>
              </div>
            </div>
          )}

          {activeStage === 4 && (
            <div>
              <h4>最终定稿</h4>
              <div>已审批章节：{approvedSectionCount} / {sections.length}</div>
              {!allApproved && <p>所有章节完成人工审批后才能生成最终稿。</p>}
              {allApproved && (
                <>
                  <input style={{ width: '100%', margin: '12px 0' }} placeholder="排版模板要求，可选" value={templateHint} onChange={(e) => setTemplateHint(e.target.value)} />
                  <div className="fund-generation-action">
                    <button onClick={runFinalFormatting} disabled={loading}>生成最终定稿</button>
                    <GenerationFeedback action="format" status={generationStatus} />
                  </div>
                </>
              )}
              {formattedText && (
                <div style={{ marginTop: 16 }}>
                  <h4>定稿预览</h4>
                  <MarkdownPreview value={formattedText} />
                  <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                    <button onClick={() => onExport?.(proposal.id, 'md')} disabled={exporting}>下载 Markdown</button>
                    <button onClick={() => onExport?.(proposal.id, 'docx')} disabled={exporting}>下载 DOCX</button>
                    <button onClick={() => onExport?.(proposal.id, 'pdf')} disabled={exporting}>下载 PDF</button>
                  </div>
                </div>
              )}
            </div>
          )}

          {error && <div style={{ color: '#b42318', marginTop: 12 }}>{error}</div>}
        </div>
      )}
    </div>
  )
}

export function Proposals({ token, selectedOrgId }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [creating, setCreating] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [exporting, setExporting] = useState(null)
  const [fmtById, setFmtById] = useState({})
  const [openAuthorForId, setOpenAuthorForId] = useState(null)
  const [showTrash, setShowTrash] = useState(false)
  const [actionMessage, setActionMessage] = useState('')
  const orgId = selectedOrgId !== undefined
    ? String(selectedOrgId || '')
    : (localStorage.getItem('orgId') || '')
  const archive = async (p) => {
    try {
      await api(`/proposals/${p.id}/`, { method: 'PATCH', token, orgId: orgId || undefined, body: { state: 'archived' } })
      await refresh()
      setActionMessage(`项目 ${p.content?.meta?.title || p.id} 已移入回收站`)
  } catch (e) {
      setActionMessage(`归档失败：${e?.data?.error || e.message}`)
    }
  }
  const unarchive = async (p) => {
    try {
      await api(`/proposals/${p.id}/`, { method: 'PATCH', token, orgId: orgId || undefined, body: { state: 'draft' } })
      await refresh()
      setActionMessage(`项目 ${p.content?.meta?.title || p.id} 已恢复`)
  } catch (e) {
      if (e.status === 402) setActionMessage('当前申请书数量已达到限制，请先归档其他项目')
      else setActionMessage(`恢复失败：${e?.data?.error || e.message}`)
    }
  }
  const refresh = async () => {
    setLoading(true)
    try {
      const data = await api('/proposals/', { token, orgId: orgId || undefined })
      const nextItems = Array.isArray(data) ? data : data.results || []
      setItems(nextItems)
      setOpenAuthorForId(currentId => {
        if (currentId && nextItems.some(item => item.id === currentId)) return currentId
        return nextItems.find(item => item.state !== 'archived')?.id || null
      })
    } finally {
      setLoading(false)
    }
  }
  const doExport = async (proposalId, fmt='pdf') => {
    setExporting(proposalId)
    try {
      const job = await api('/exports', { method: 'POST', token, orgId: orgId || undefined, body: { proposal_id: proposalId, format: fmt } })
      if (job.url) {
        safeOpenExternal(job.url)
        return
      }
      const id = job.id
      for (let i = 0; i < 20; i++) {
        await new Promise(r => setTimeout(r, 500))
        const status = await api(`/exports/${id}`, { token, orgId: orgId || undefined })
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
    setCreating(true)
    try {
      const created = await api('/proposals/', {
        method: 'POST',
        token,
        orgId: orgId || undefined,
        body: {
          content: { meta: { title }, sections: {} },
          schema_version: 'v1',
        },
      })
      if (created?.id) setOpenAuthorForId(created.id)
      setNewTitle('')
      await refresh()
  } catch (e) {
      if (e.status === 402 && e.data) {
        alert('当前申请书数量已达到限制，请先归档旧项目后再创建')
      } else {
        alert('Create failed: ' + e.message) // keep literal for dev error
      }
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
  const activeProposal = items.find(item => item.id === openAuthorForId)
  const activeItems = items.filter(item => item.state !== 'archived')
  const archivedItems = items.filter(item => item.state === 'archived')
  return (
    <section className="fund-workspace">
      <aside className="fund-project-sidebar">
        <div className="fund-sidebar-heading">
          <div>
            <h2>我的基金申请</h2>
            <p>选择申请书后直接进入撰写流程</p>
          </div>
          <button className="fund-primary-button fund-new-button" disabled={creating} onClick={createOne}>新建申请</button>
        </div>

        <input
          className="fund-new-title"
          value={newTitle}
          onChange={(e) => setNewTitle(e.target.value)}
          placeholder="输入新项目标题"
        />

        {loading && <div className="fund-loading">正在加载</div>}
        {actionMessage && <div className="fund-action-message" role="status">{actionMessage}</div>}
        <div className="fund-project-list">
          {activeItems.map(p => (
            <article className={`fund-project-card ${openAuthorForId === p.id ? 'is-active' : ''}`} key={p.id}>
              <button className="fund-project-open" onClick={() => setOpenAuthorForId(p.id)}>
                <strong>{(p.content?.meta?.title) || t('ui.common.untitled')}</strong>
                <span>编号 {p.id} · {p.state === 'archived' ? '已归档' : '草稿'}</span>
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
                  {exporting === p.id ? '正在导出' : '导出'}
                </button>
                <button onClick={() => setOpenAuthorForId(p.id)}>打开撰写区</button>
                {p.state !== 'archived' ? (
                  <button onClick={() => archive(p)}>归档</button>
                ) : (
                  <button onClick={() => unarchive(p)}>取消归档</button>
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
                    <button onClick={() => unarchive(p)}>恢复项目</button>
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
              新建第一份申请
            </button>
          </div>
        )}
      </main>
    </section>
  )
}

export function Orgs({ token, onSelectOrg }) {
  const [items, setItems] = useState([])
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [selectedId, setSelectedId] = useState('')
  const [membersByOrg, setMembersByOrg] = useState({})
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteRole, setInviteRole] = useState('member')
  const [invitesByOrg, setInvitesByOrg] = useState({})
  const [transferUserId, setTransferUserId] = useState('')

  const refresh = async () => { try { setItems(await api('/orgs/', { token })) } catch {} }
  const loadMembers = async (orgId) => { try { const m = await api(`/orgs/${orgId}/members/`, { token }); setMembersByOrg(s => ({ ...s, [orgId]: m })) } catch {} }
  const loadInvites = async (orgId) => { try { const m = await api(`/orgs/${orgId}/invites/`, { token }); setInvitesByOrg(s => ({ ...s, [orgId]: m })) } catch {} }
  useEffect(() => { refresh() }, [token])
  const createOrg = async () => { await api('/orgs/', { method: 'POST', token, body: { name, description: desc } }); setName(''); setDesc(''); refresh() }
  const removeOrg = async (orgId) => { if (!confirm('Delete this organization?')) return; await api(`/orgs/${orgId}/`, { method: 'DELETE', token }); refresh() }
  const inviteMember = async (orgId) => { if (!inviteEmail) return; const inv = await api(`/orgs/${orgId}/invites/`, { method: 'POST', token, body: { email: inviteEmail, role: inviteRole } }); setInviteEmail(''); await loadInvites(orgId); alert(`Invite created. Token (dev): ${inv.token}`) }
  const removeMember = async (orgId, userId) => { await api(`/orgs/${orgId}/members/`, { method: 'DELETE', token, body: { user_id: userId } }); loadMembers(orgId) }
  const revokeInvite = async (orgId, id) => { await api(`/orgs/${orgId}/invites/`, { method: 'DELETE', token, body: { id } }); await loadInvites(orgId) }
  const transfer = async (orgId) => { if (!transferUserId) return; await api(`/orgs/${orgId}/transfer/`, { method: 'POST', token, body: { user_id: Number(transferUserId) } }); setTransferUserId(''); refresh() }
  const acceptInvite = async () => {
    if (!import.meta.env.VITE_UI_EXPERIMENTS) return
    const tokenStr = typeof window !== 'undefined' ? window.prompt('Paste invite token (dev flow)') : ''
    if (!tokenStr) return
    const res = await api('/orgs/invites/accept', { method: 'POST', token, body: { token: tokenStr } })
    alert('Joined organization #' + res.org_id)
    await refresh()
  }

  return (
    <section>
      <div>
        <h2>{t('ui.orgs.heading')}</h2>
        <div>
          <input placeholder="工作区名称，留空自动编号" value={name} onChange={e => setName(e.target.value)} />
          <input placeholder={t('ui.orgs.description_placeholder')} value={desc} onChange={e => setDesc(e.target.value)} />
          <button onClick={createOrg}>{t('ui.orgs.create_button')}</button>
        </div>
      </div>
      <ul>
        {items.map(org => (
          <li key={org.id}>
            <div>
              <strong>#{org.id}</strong> {org.name}
              <span> {org.description}</span>
              <span> admin: {org.admin?.username}</span>
              <button onClick={() => onSelectOrg(String(org.id))}>{t('ui.orgs.use_button')}</button>
              <button onClick={() => { const open = selectedId === String(org.id); setSelectedId(open ? '' : String(org.id)); if (!open) { loadMembers(org.id); loadInvites(org.id) } }}>{selectedId === String(org.id) ? t('ui.orgs.hide_button') : t('ui.orgs.manage_button')}</button>
              <button onClick={() => removeOrg(org.id)}>{t('ui.orgs.delete_button')}</button>
            </div>
            {selectedId === String(org.id) && (
              <div>
                <div>
                  <div>{t('ui.orgs.members_heading')}</div>
                  <div>{t('ui.orgs.invite_heading')}</div>
                  <input placeholder={t('ui.orgs.invite_email_placeholder')} value={inviteEmail} onChange={e => setInviteEmail(e.target.value)} />
                  <select value={inviteRole} onChange={e => setInviteRole(e.target.value)}>
                    <option value="member">{t('ui.orgs.member_role_member')}</option>
                    <option value="admin">{t('ui.orgs.member_role_admin')}</option>
                  </select>
                  <button onClick={() => inviteMember(org.id)}>{t('ui.orgs.invite_button')}</button>
                </div>
                <ul>
                  {(membersByOrg[org.id] || []).map(m => (
                    <li key={m.user.id}>
                      {m.user.username} ({m.user.id}) — {m.role}
                      <button onClick={() => removeMember(org.id, m.user.id)}>Remove</button>
                    </li>
                  ))}
                </ul>
                <div>
                  <div>{t('ui.orgs.pending_invites_heading')}</div>
                  <ul>
                    {(invitesByOrg[org.id] || []).map(inv => (
                      <li key={inv.id}>
                        {inv.email} — {inv.role} {inv.accepted_at ? t('ui.orgs.accepted') : inv.revoked_at ? t('ui.orgs.revoked') : t('ui.orgs.pending')}
                        {!inv.accepted_at && !inv.revoked_at && (
                          <>
                            <button onClick={() => revokeInvite(org.id, inv.id)}>{t('ui.orgs.revoke_button')}</button>
                            <span> {t('ui.orgs.token_label',{value: inv.token})}</span>
                          </>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <div>{t('ui.orgs.transfer_heading')}</div>
                  <input placeholder={t('ui.orgs.new_admin_placeholder')} value={transferUserId} onChange={e => setTransferUserId(e.target.value)} />
                  <button onClick={() => transfer(org.id)}>{t('ui.orgs.transfer_button')}</button>
                </div>
              </div>
            )}
          </li>
        ))}
      </ul>
      <div>
        <button onClick={acceptInvite}>{t('ui.orgs.accept_invite_button')}</button>
      </div>
    </section>
  )
}

export default function Dashboard({ token, selectedOrgId, onSelectOrg }) {
  return (
    <div>
      <div>
        <Proposals token={token} selectedOrgId={selectedOrgId} />
        <Orgs token={token} onSelectOrg={onSelectOrg} />
      </div>
    </div>
  )
}

// Named exports for tests
export { AuthorPanel }
export { default as SectionDiff } from '../components/SectionDiff.jsx'
