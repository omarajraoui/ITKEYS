import { useState, useEffect, useMemo } from 'react'
import { useAuth } from './Auth.jsx'
import { supabase } from './supabase'

// ─── API helper ─────────────────────────────────────────────────────────────

async function apiFetch(url, options = {}, _retry = false) {
  // Get fresh session — refreshSession() is the most reliable way
  let token
  try {
    const { data } = await supabase.auth.refreshSession()
    token = data?.session?.access_token
  } catch {}
  if (!token) {
    try {
      const { data: { session } } = await supabase.auth.getSession()
      token = session?.access_token
    } catch {}
  }
  const headers = { ...options.headers }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  // Don't set Content-Type for FormData (browser handles multipart boundary)
  if (options.body && !headers['Content-Type'] && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
  }
  const res = await fetch(url, { ...options, headers })
  // If 401 and we haven't retried yet, force token refresh and retry once
  if (res.status === 401 && !_retry) {
    // 401 — retry with refreshed token
    try {
      const { data } = await supabase.auth.refreshSession()
      if (data?.session?.access_token) {
        return apiFetch(url, options, true)
      }
    } catch {}
  }
  return res
}

// ─── Constants ───────────────────────────────────────────────────────────────

const SOURCE_LABELS = {
  wttj:         'WTTJ',
  francetravail:'France Travail',
  linkedin:     'LinkedIn',
  csp:          'Service Public',
  adzuna:       'Adzuna',
  indeed:       'Indeed',
  apec:         'APEC',
  pmejob:       'PMEjob',
  hellowork:    'HelloWork',
}

const STATUS_CONFIG = {
  to_apply:  { label: 'Généré',    color: 'var(--accent)' },
  applied:   { label: 'Postulé',   color: 'var(--blue)' },
  followup:  { label: 'Relance',   color: 'var(--orange)' },
  interview: { label: 'Entretien', color: 'var(--green)' },
  rejected:  { label: 'Refus',     color: 'var(--red)' },
  offer:     { label: 'Offre',     color: 'var(--green)' },
}

const KANBAN_COLS = ['to_apply', 'applied', 'followup', 'interview', 'rejected', 'offer']

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getPostingDate(scanDate, daysAgo) {
  if (!scanDate) return null
  const d = new Date(scanDate)
  d.setDate(d.getDate() - (daysAgo ?? 0))
  return d
}

function formatDate(date) {
  if (!date) return ''
  return date.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })
}

function daysLabel(days) {
  if (days === 0) return "Aujourd'hui"
  if (days === 1) return 'Hier'
  if (days <= 3) return `${days} jours`
  return `${days}j`
}

function expLabel(exp) {
  if (exp == null) return null
  if (exp === 0) return 'Débutant'
  if (exp < 1) return '< 1 an'
  if (exp < 2) return '1–2 ans'
  if (exp < 3) return '2–3 ans'
  return `${exp}+ ans`
}

const REMOTE_LABELS = { full: 'Full remote', partial: 'Hybride', punctual: 'Sur site +', none: 'Sur site' }

const REC_CONFIG = {
  STRONG_APPLY: { label: 'Top Match', color: 'var(--green)', bg: 'var(--green-dim)' },
  APPLY:        { label: 'Postuler', color: 'var(--blue)', bg: 'var(--blue-dim)' },
  STRETCH:      { label: 'Stretch', color: 'var(--yellow)', bg: 'var(--yellow-dim)' },
  LOW_PRIORITY: { label: 'Faible', color: 'var(--text-muted)', bg: 'var(--bg-active)' },
}

// ─── Métier detection ────────────────────────────────────────────────────────

const METIER_RULES = [
  { label: 'DevOps / Cloud', keys: ['devops', 'kubernetes', 'docker', 'terraform', 'ansible', 'ci/cd', 'openshift', 'cloud', 'azure', 'gcp'] },
  { label: 'IA / GenAI',     keys: ['ia', 'llm', 'rag', 'genai', 'machine learning', 'mlops', 'nlp', 'ai'] },
  { label: 'Fullstack',      keys: ['react', 'angular', 'typescript', 'fullstack', 'vue', 'frontend', 'graphql'] },
  { label: 'Java / Backend', keys: ['java', 'spring boot', 'spring', 'jpa', 'microservices'] },
  { label: 'Python',         keys: ['python', 'django', 'fastapi', 'flask'] },
  { label: 'Consulting / SI',keys: ['si', 'architecture', 'erp', 'sap', 'conseil', 'consulting'] },
]

function detectMetier(offer) {
  const text = [offer.title, ...(offer.matched_skills || []), offer.description?.slice(0, 200) || ''].join(' ').toLowerCase()
  for (const m of METIER_RULES) {
    if (m.keys.some(k => text.includes(k))) return m
  }
  return { label: 'Autre' }
}

// ─── Design tokens ───────────────────────────────────────────────────────────

function scoreColor(s) {
  if (s >= 40) return 'var(--green)'
  if (s >= 20) return 'var(--yellow)'
  return 'var(--text-muted)'
}

function Tag({ children, active, style = {} }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      fontSize: 11, fontWeight: 500, padding: '3px 8px',
      borderRadius: 6, border: '1px solid var(--border)',
      background: active ? 'var(--bg-active)' : 'transparent',
      color: active ? 'var(--text-primary)' : 'var(--text-secondary)',
      lineHeight: 1, whiteSpace: 'nowrap', ...style,
    }}>
      {children}
    </span>
  )
}

// ─── Download Button ─────────────────────────────────────────────────────────

function DownloadBtn({ url, label }) {
  const [loading, setLoading] = useState(false)

  const handleDownload = async () => {
    setLoading(true)
    try {
      const res = await apiFetch(url)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const blob = await res.blob()
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = url.split('/').pop()
      a.click()
      URL.revokeObjectURL(a.href)
    } catch (e) { alert(`Erreur: ${e.message}`) }
    finally { setLoading(false) }
  }

  const handlePreview = async () => {
    setLoading(true)
    try {
      const res = await apiFetch(url)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const blob = await res.blob()
      const blobUrl = URL.createObjectURL(blob)
      window.open(blobUrl, '_blank')
    } catch (e) { alert(`Erreur: ${e.message}`) }
    finally { setLoading(false) }
  }

  return (
    <div style={{ display: 'flex', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)', overflow: 'hidden' }}>
      <button onClick={handlePreview} disabled={loading} title={`Voir ${label}`} style={{
        background: 'var(--bg-surface)', color: 'var(--text-secondary)',
        fontSize: 11, fontWeight: 500, padding: '5px 8px', border: 'none',
        cursor: loading ? 'wait' : 'pointer', display: 'flex', alignItems: 'center', gap: 4,
        borderRight: '1px solid var(--border)',
      }}>
        {loading
          ? <span style={{ width: 10, height: 10, border: '2px solid var(--text-muted)', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 0.7s linear infinite', display: 'inline-block' }} />
          : <svg width="11" height="11" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /><path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" /></svg>
        }
        {label}
      </button>
      <button onClick={handleDownload} disabled={loading} title={`Telecharger ${label}`} style={{
        background: 'var(--bg-surface)', color: 'var(--text-muted)',
        fontSize: 11, padding: '5px 6px', border: 'none',
        cursor: loading ? 'wait' : 'pointer', display: 'flex', alignItems: 'center',
      }}>
        <svg width="10" height="10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
      </button>
    </div>
  )
}

// ─── Preview Modal ───────────────────────────────────────────────────────────

function PreviewModal({ preview, onConfirm, onRecompile, onClose, onRegenerate }) {
  const { offer, result } = preview
  const [cvUrl, setCvUrl] = useState(null)
  const [letterUrl, setLetterUrl] = useState(null)
  const [loadingPdfs, setLoadingPdfs] = useState(true)
  const [prompt, setPrompt] = useState('')
  const [sending, setSending] = useState(false)
  const [messages, setMessages] = useState([])
  const [pdfKey, setPdfKey] = useState(0)

  // Escape key + browser back to close
  useEffect(() => {
    const handleKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handleKey)
    window.history.pushState({ preview: true }, '')
    const handlePop = () => onClose()
    window.addEventListener('popstate', handlePop)
    return () => { window.removeEventListener('keydown', handleKey); window.removeEventListener('popstate', handlePop) }
  }, [])

  // Load PDF blobs for preview
  const loadPdfs = async () => {
    setLoadingPdfs(true)
    try {
      const bust = `?t=${Date.now()}`
      const [cvRes, ltRes] = await Promise.all([
        apiFetch(result.cv_url + bust), apiFetch(result.letter_url + bust),
      ])
      if (cvUrl) URL.revokeObjectURL(cvUrl)
      if (letterUrl) URL.revokeObjectURL(letterUrl)
      const cvBlob = await cvRes.blob()
      const ltBlob = await ltRes.blob()
      setCvUrl(URL.createObjectURL(cvBlob))
      setLetterUrl(URL.createObjectURL(ltBlob))
      setPdfKey(k => k + 1)
    } catch {}
    setLoadingPdfs(false)
  }
  useEffect(() => { loadPdfs() }, [result.cv_url, result.letter_url])

  const handleSend = async () => {
    if (!prompt.trim() || sending) return
    const msg = prompt.trim()
    setMessages(m => [...m, { role: 'user', text: msg }])
    setPrompt('')
    setSending(true)
    setMessages(m => [...m, { role: 'assistant', text: 'Sonnet redige les modifications...' }])

    try {
      await onRegenerate({ ...offer, _prompt: msg })
      setMessages(m => m.slice(0, -1).concat({ role: 'assistant', text: 'Modifications appliquees. Rechargement des PDFs...' }))
      // Wait for generation to finish, then reload PDFs multiple times
      const reload = async (delay) => { await new Promise(r => setTimeout(r, delay)); await loadPdfs() }
      await reload(5000)  // first try after 5s
      await reload(10000) // retry after 10 more seconds
      setMessages(m => [...m, { role: 'assistant', text: 'PDFs mis a jour.' }])
    } catch (e) {
      setMessages(m => m.slice(0, -1).concat({ role: 'assistant', text: `Erreur: ${e.message}` }))
    }
    setSending(false)
  }

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 200, background: 'var(--bg-base)', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{ padding: '14px 24px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0 }}>
        <div>
          <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>{offer.company}</div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>{offer.title}</div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <DownloadBtn url={result.cv_url} label="CV" />
          <DownloadBtn url={result.letter_url} label="Lettre" />
          <button onClick={onClose} style={{ background: 'var(--bg-active)', border: 'none', color: 'var(--text-secondary)', borderRadius: 'var(--radius-sm)', padding: '8px 16px', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>Fermer</button>
        </div>
      </div>

      {/* Main content: PDFs + Chat */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* PDF Previews */}
        <div style={{ flex: 1, display: 'flex', gap: 1, background: 'var(--border)', overflow: 'hidden' }}>
          <div style={{ flex: 1, background: 'var(--bg-base)', display: 'flex', flexDirection: 'column' }}>
            <div style={{ padding: '8px 14px', fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', borderBottom: '1px solid var(--border)' }}>CV</div>
            {loadingPdfs ? (
              <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <div style={{ width: 20, height: 20, border: '2px solid var(--border)', borderTopColor: 'var(--text-muted)', borderRadius: '50%', animation: 'spin 0.7s linear infinite' }} />
              </div>
            ) : cvUrl ? (
              <iframe key={`cv-${pdfKey}`} src={`${cvUrl}#toolbar=0&navpanes=0&zoom=67`} style={{ flex: 1, border: 'none', background: '#fff' }} title="CV Preview" />
            ) : <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 12 }}>PDF non disponible</div>}
          </div>
          <div style={{ flex: 1, background: 'var(--bg-base)', display: 'flex', flexDirection: 'column' }}>
            <div style={{ padding: '8px 14px', fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', borderBottom: '1px solid var(--border)' }}>Lettre de motivation</div>
            {loadingPdfs ? (
              <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <div style={{ width: 20, height: 20, border: '2px solid var(--border)', borderTopColor: 'var(--text-muted)', borderRadius: '50%', animation: 'spin 0.7s linear infinite' }} />
              </div>
            ) : letterUrl ? (
              <iframe key={`lt-${pdfKey}`} src={`${letterUrl}#toolbar=0&navpanes=0&zoom=67`} style={{ flex: 1, border: 'none', background: '#fff' }} title="Letter Preview" />
            ) : <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 12 }}>PDF non disponible</div>}
          </div>
        </div>
      </div>

      {/* Chat panel */}
      <div style={{ borderTop: '1px solid var(--border)', flexShrink: 0, background: 'var(--bg-raised)' }}>
        {/* Welcome message if no messages yet */}
        {messages.length === 0 && (
          <div style={{ padding: '14px 24px', display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ width: 28, height: 28, borderRadius: '50%', background: 'var(--accent-glow)', border: '1px solid var(--accent-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
              <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="var(--accent)" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 }}>
              Demandez une modification : changer le titre, raccourcir la lettre, mettre en avant une experience...
            </div>
          </div>
        )}
        {/* Messages */}
        {messages.length > 0 && (
          <div style={{ maxHeight: 180, overflowY: 'auto', padding: '14px 24px', display: 'flex', flexDirection: 'column', gap: 8 }}>
            {messages.map((m, i) => (
              <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                {m.role === 'assistant' && (
                  <div style={{ width: 24, height: 24, borderRadius: '50%', background: 'var(--accent-glow)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, marginTop: 2 }}>
                    <svg width="10" height="10" fill="none" viewBox="0 0 24 24" stroke="var(--accent)" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>
                  </div>
                )}
                <div style={{
                  maxWidth: '80%', padding: '8px 14px', fontSize: 12, lineHeight: 1.5,
                  borderRadius: m.role === 'user' ? '12px 12px 4px 12px' : '12px 12px 12px 4px',
                  background: m.role === 'user' ? 'var(--bg-active)' : 'var(--bg-base)',
                  color: m.role === 'user' ? 'var(--text-primary)' : 'var(--text-secondary)',
                  marginLeft: m.role === 'user' ? 'auto' : 0,
                }}>{m.text}</div>
              </div>
            ))}
          </div>
        )}
        {/* Input */}
        <div style={{ padding: '12px 24px 16px', display: 'flex', gap: 8, alignItems: 'center' }}>
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', background: 'var(--bg-base)', border: '2px solid var(--border-light)', borderRadius: 24, padding: '4px 6px 4px 16px', transition: 'border-color 0.2s' }}
            onFocus={e => e.currentTarget.style.borderColor = 'var(--accent)'}
            onBlur={e => e.currentTarget.style.borderColor = 'var(--border-light)'}>
            <input value={prompt} onChange={e => setPrompt(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleSend() }}
              placeholder="Ex: raccourcis la lettre, mets en avant les JO, change le titre..."
              disabled={sending}
              style={{ flex: 1, padding: '8px 0', background: 'transparent', border: 'none', color: 'var(--text-primary)', fontSize: 13, outline: 'none' }} />
            <button onClick={handleSend} disabled={sending || !prompt.trim()} style={{
              padding: '8px 16px', background: sending ? 'var(--bg-active)' : 'var(--accent)',
              color: sending ? 'var(--text-muted)' : '#fff', border: 'none',
              borderRadius: 20, fontSize: 12, fontWeight: 600, cursor: sending ? 'wait' : 'pointer', flexShrink: 0,
            }}>
              {sending ? '...' : '→'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Kanban ──────────────────────────────────────────────────────────────────

function KanbanCard({ app, onStatusChange, onNotesChange }) {
  const cfg = STATUS_CONFIG[app.status] || STATUS_CONFIG.to_apply
  const nextStatuses = KANBAN_COLS.filter(s => s !== app.status)
  const [open, setOpen] = useState(false)
  const [editingNotes, setEditingNotes] = useState(false)
  const [notes, setNotes] = useState(app.notes || '')

  return (
    <div style={{ background: 'var(--bg-raised)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: 16, display: 'flex', flexDirection: 'column', gap: 10, transition: 'box-shadow 0.15s' }}>
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
          <span style={{ color: 'var(--text-muted)', fontSize: 10, fontWeight: 600 }}>#{app.id}</span>
          <span style={{ color: 'var(--text-primary)', fontSize: 13, fontWeight: 600 }}>{app.company}</span>
        </div>
        <div style={{ color: 'var(--text-secondary)', fontSize: 11 }}>{app.role}</div>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{app.apply_date}</span>
        <span style={{ fontSize: 10, fontWeight: 600, color: cfg.color, background: `color-mix(in srgb, ${cfg.color} 12%, transparent)`, padding: '3px 8px', borderRadius: 5 }}>{cfg.label}</span>
      </div>

      {(app.cv_url || app.letter_url) && (
        <div style={{ display: 'flex', gap: 6 }}>
          {app.cv_url && <DownloadBtn url={app.cv_url} label="CV" />}
          {app.letter_url && <DownloadBtn url={app.letter_url} label="Lettre" />}
        </div>
      )}

      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
        {app.apply_link && (
          <a href={app.apply_link} target="_blank" rel="noopener noreferrer" style={{ fontSize: 11, color: 'var(--accent)', textDecoration: 'none', fontWeight: 500 }}>Voir l'offre ↗</a>
        )}
        <div style={{ position: 'relative', marginLeft: 'auto' }}>
          <button onClick={() => setOpen(v => !v)} style={{ fontSize: 11, color: 'var(--text-muted)', background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 6, padding: '4px 8px', cursor: 'pointer' }}>Statut ▾</button>
          {open && (
            <div style={{ position: 'absolute', bottom: '110%', right: 0, background: 'var(--bg-raised)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', overflow: 'hidden', zIndex: 50, minWidth: 130, boxShadow: 'var(--shadow-md)' }}>
              {nextStatuses.map(s => {
                const c = STATUS_CONFIG[s]
                return <button key={s} onClick={() => { onStatusChange(app.id, s); setOpen(false) }} style={{ width: '100%', display: 'block', padding: '8px 12px', background: 'none', border: 'none', color: c.color, fontSize: 12, textAlign: 'left', cursor: 'pointer' }}>{c.label}</button>
              })}
            </div>
          )}
        </div>
      </div>

      {editingNotes ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <textarea value={notes} onChange={e => setNotes(e.target.value)} placeholder="Notes…" rows={2} style={{ background: 'var(--bg-base)', border: '1px solid var(--border)', borderRadius: 6, padding: '6px 8px', fontSize: 11, color: 'var(--text-primary)', resize: 'vertical', outline: 'none' }} />
          <div style={{ display: 'flex', gap: 4 }}>
            <button onClick={() => { onNotesChange(app.id, notes); setEditingNotes(false) }} style={{ fontSize: 10, color: 'var(--green)', background: 'var(--green-dim)', border: 'none', borderRadius: 4, padding: '4px 8px', cursor: 'pointer', fontWeight: 500 }}>Sauver</button>
            <button onClick={() => { setNotes(app.notes || ''); setEditingNotes(false) }} style={{ fontSize: 10, color: 'var(--text-secondary)', background: 'none', border: '1px solid var(--border)', borderRadius: 4, padding: '4px 8px', cursor: 'pointer' }}>Annuler</button>
          </div>
        </div>
      ) : (
        <div onClick={() => setEditingNotes(true)} style={{ cursor: 'pointer', fontSize: 11, color: notes ? 'var(--text-secondary)' : 'var(--text-muted)', fontStyle: notes ? 'normal' : 'italic', borderTop: '1px solid var(--border)', paddingTop: 8 }}>
          {notes || '+ Notes…'}
        </div>
      )}
    </div>
  )
}

function TemplateCard({ label, icon, activeVariant, defaultContent, customContent, hasCustom, onActivate, onUpload, onCustomChange, onSave, saving }) {
  const isDefault = activeVariant === 'default'
  const isCustom = activeVariant === 'custom'
  const [expanded, setExpanded] = useState(null) // null | 'default' | 'custom'

  return (
    <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Card header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
        <div style={{ width: 36, height: 36, borderRadius: 'var(--radius-sm)', background: 'var(--accent-glow)', border: '1px solid var(--accent-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16 }}>{icon}</div>
        <div>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>{label}</div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 1 }}>
            Actif : <span style={{ color: isCustom ? 'var(--accent)' : 'var(--text-secondary)', fontWeight: 600 }}>{isCustom ? 'Personnalisé' : 'Par défaut'}</span>
          </div>
        </div>
      </div>

      {/* Default option */}
      <div onClick={() => { onActivate('default'); setExpanded(null) }}
        style={{
          background: isDefault ? 'var(--bg-surface)' : 'var(--bg-raised)',
          border: isDefault ? '2px solid var(--green)' : '1px solid var(--border)',
          borderRadius: 'var(--radius-md)', padding: '14px 16px', cursor: 'pointer',
          transition: 'all 0.2s', position: 'relative',
        }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ width: 18, height: 18, borderRadius: '50%', border: isDefault ? '2px solid var(--green)' : '2px solid var(--border-light)', display: 'flex', alignItems: 'center', justifyContent: 'center', transition: 'all 0.2s' }}>
              {isDefault && <div style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--green)' }} />}
            </div>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: isDefault ? 'var(--text-primary)' : 'var(--text-secondary)' }}>Par défaut</div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{defaultContent.split('\n').length} lignes · Template intégré</div>
            </div>
          </div>
          <button onClick={(e) => { e.stopPropagation(); setExpanded(expanded === 'default' ? null : 'default') }} style={{ background: 'var(--bg-hover)', border: '1px solid var(--border)', borderRadius: 6, padding: '4px 10px', fontSize: 11, color: 'var(--text-secondary)', cursor: 'pointer', fontWeight: 500 }}>
            {expanded === 'default' ? 'Fermer' : 'Voir'}
          </button>
        </div>
        {expanded === 'default' && (
          <div style={{ marginTop: 12, borderTop: '1px solid var(--border)', paddingTop: 12 }}>
            <pre style={{ margin: 0, padding: 12, background: 'var(--bg-base)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)', fontSize: 11, lineHeight: 1.6, color: 'var(--text-secondary)', fontFamily: 'ui-monospace, "SF Mono", Menlo, monospace', overflow: 'auto', maxHeight: 300, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
              {defaultContent}
            </pre>
          </div>
        )}
      </div>

      {/* Custom option */}
      <div style={{
        background: hasCustom && isCustom ? 'var(--bg-surface)' : 'var(--bg-raised)',
        border: hasCustom && isCustom ? '2px solid var(--accent)' : hasCustom ? '1px solid var(--border)' : '1px dashed var(--border-light)',
        borderRadius: 'var(--radius-md)', padding: '14px 16px',
        transition: 'all 0.2s', position: 'relative',
      }}>
        {hasCustom ? (
          <>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div onClick={() => { onActivate('custom'); setExpanded(null) }} style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', flex: 1 }}>
                <div style={{ width: 18, height: 18, borderRadius: '50%', border: isCustom ? '2px solid var(--accent)' : '2px solid var(--border-light)', display: 'flex', alignItems: 'center', justifyContent: 'center', transition: 'all 0.2s' }}>
                  {isCustom && <div style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--accent)' }} />}
                </div>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: isCustom ? 'var(--text-primary)' : 'var(--text-secondary)' }}>Personnalisé</div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{customContent.split('\n').length} lignes · Importé par l'utilisateur</div>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 6 }}>
                <button onClick={() => setExpanded(expanded === 'custom' ? null : 'custom')} style={{ background: 'var(--bg-hover)', border: '1px solid var(--border)', borderRadius: 6, padding: '4px 10px', fontSize: 11, color: 'var(--text-secondary)', cursor: 'pointer', fontWeight: 500 }}>
                  {expanded === 'custom' ? 'Fermer' : 'Éditer'}
                </button>
                <label style={{ background: 'var(--bg-hover)', border: '1px solid var(--border)', borderRadius: 6, padding: '4px 10px', fontSize: 11, color: 'var(--text-secondary)', cursor: 'pointer', fontWeight: 500 }}>
                  Remplacer
                  <input type="file" accept=".tex,.txt" onChange={onUpload} style={{ display: 'none' }} />
                </label>
              </div>
            </div>
            {expanded === 'custom' && (
              <div style={{ marginTop: 12, borderTop: '1px solid var(--border)', paddingTop: 12 }}>
                <textarea
                  value={customContent}
                  onChange={e => onCustomChange(e.target.value)}
                  spellCheck={false}
                  style={{
                    width: '100%', minHeight: 280, padding: 12,
                    background: 'var(--bg-base)', borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--accent-dim)', color: 'var(--text-primary)',
                    fontFamily: 'ui-monospace, "SF Mono", Menlo, monospace',
                    fontSize: 11.5, lineHeight: 1.6, resize: 'vertical', tabSize: 2,
                    outline: 'none',
                  }}
                />
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
                  <button onClick={onSave} disabled={saving} style={{ background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 6, padding: '6px 18px', fontSize: 12, fontWeight: 600, cursor: saving ? 'wait' : 'pointer', opacity: saving ? 0.6 : 1 }}>
                    {saving ? 'Sauvegarde…' : 'Sauvegarder'}
                  </button>
                </div>
              </div>
            )}
          </>
        ) : (
          <label style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, padding: '20px 0', cursor: 'pointer' }}>
            <div style={{ width: 44, height: 44, borderRadius: 'var(--radius-md)', background: 'var(--accent-glow)', border: '1px dashed var(--accent-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="var(--accent)" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" /></svg>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)' }}>Ajouter un template personnalisé</div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 3 }}>Importez un fichier .tex pour remplacer le template par défaut</div>
            </div>
            <input type="file" accept=".tex,.txt" onChange={onUpload} style={{ display: 'none' }} />
          </label>
        )}
      </div>
    </div>
  )
}

function TemplatePreview({ kind }) {
  const [url, setUrl] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [key, setKey] = useState(0)

  const loadPreview = async () => {
    setLoading(true); setError(null)
    try {
      const { data: { session } } = await supabase.auth.getSession()
      const headers = {}
      if (session?.access_token) headers['Authorization'] = `Bearer ${session.access_token}`
      const r = await fetch(`/api/templates/preview/${kind}?t=${Date.now()}`, { headers })
      if (!r.ok) { const d = await r.json().catch(() => ({})); throw new Error(d.error || 'Erreur de compilation') }
      const blob = await r.blob()
      if (url) URL.revokeObjectURL(url)
      setUrl(URL.createObjectURL(blob))
      setKey(k => k + 1)
    } catch (e) { setError(e.message) }
    finally { setLoading(false) }
  }

  useEffect(() => { loadPreview() }, [kind])

  return (
    <div style={{ background: 'var(--bg-base)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', overflow: 'hidden', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      <div style={{ padding: '10px 14px', width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border)' }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)' }}>Apercu {kind === 'cv' ? 'CV' : 'Lettre'}</span>
        <button onClick={loadPreview} disabled={loading} style={{ background: 'none', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: '3px 10px', fontSize: 11, color: 'var(--text-muted)', cursor: loading ? 'wait' : 'pointer' }}>
          {loading ? 'Compilation...' : 'Rafraichir'}
        </button>
      </div>
      {loading ? (
        <div style={{ padding: '60px 0', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 20, height: 20, border: '2px solid var(--border)', borderTopColor: 'var(--text-muted)', borderRadius: '50%', animation: 'spin 0.7s linear infinite' }} />
          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Compilation du PDF...</span>
        </div>
      ) : error ? (
        <div style={{ padding: '40px 20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>{error}</div>
      ) : url ? (
        <iframe key={key} src={`${url}#toolbar=0&navpanes=0&zoom=67`} style={{ width: '100%', height: 600, border: 'none', background: '#fff' }} title={`Preview ${kind}`} />
      ) : null}
    </div>
  )
}

// ─── Profile Page ────────────────────────────────────────────────────────────

function ProfilePage({ onRescan, onCreateProfile, onProfileChange }) {
  const [prefs, setPrefs] = useState(null)
  const [truth, setTruth] = useState(null)
  const [profiles, setProfiles] = useState([])
  const [activeProfile, setActiveProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState(null)
  const [editPrefs, setEditPrefs] = useState(null)
  const [inputVals, setInputVals] = useState({ skills_core: '', skills_exclude: '', titles_target: '' })
  const [editSection, setEditSection] = useState(null)
  const [editTruth, setEditTruth] = useState(null)
  const [expandedExp, setExpandedExp] = useState({})
  const [prefsOpen, setPrefsOpen] = useState(false)
  const [showNewProfile, setShowNewProfile] = useState(false)
  const [newProfileName, setNewProfileName] = useState('')
  const [creatingProfile, setCreatingProfile] = useState(false)
  const [newProfileCv, setNewProfileCv] = useState(null)
  const [newProfileParsing, setNewProfileParsing] = useState(false)
  const [newProfileParsed, setNewProfileParsed] = useState(null)
  const [profileDropOpen, setProfileDropOpen] = useState(false)

  // Close dropdown on outside click
  useEffect(() => {
    if (!profileDropOpen) return
    const close = () => setProfileDropOpen(false)
    const t = setTimeout(() => document.addEventListener('click', close), 0)
    return () => { clearTimeout(t); document.removeEventListener('click', close) }
  }, [profileDropOpen])

  const loadAll = async () => {
    try {
      const [p, t, prof] = await Promise.all([
        apiFetch('/api/profile/preferences').then(r => r.json()).catch(() => ({})),
        apiFetch('/api/profile/truth').then(r => r.ok ? r.json() : null).catch(() => null),
        apiFetch('/api/profiles').then(r => r.json()).catch(() => ({ profiles: [], active: null })),
      ])
      setPrefs(p); setEditPrefs(p); setTruth(t)
      setProfiles(prof.profiles || []); setActiveProfile(prof.active)
    } catch (e) { console.error('[loadAll] unexpected error:', e) }
    setLoading(false)
  }
  useEffect(() => { loadAll() }, [])

  const savePrefs = async () => {
    setSaving(true); setMsg(null)
    try {
      await apiFetch('/api/profile/preferences', { method: 'PUT', body: JSON.stringify(editPrefs) })
      setPrefs(editPrefs)
      setMsg({ type: 'ok', text: 'Preferences sauvegardees' })
    } catch (e) { setMsg({ type: 'err', text: e.message }) }
    setSaving(false)
  }

  const saveTruth = async () => {
    setSaving(true); setMsg(null)
    try {
      await apiFetch('/api/profile/truth', { method: 'PUT', body: JSON.stringify(editTruth) })
      setTruth(editTruth); setEditSection(null)
      setMsg({ type: 'ok', text: 'Profil mis a jour' })
    } catch (e) { setMsg({ type: 'err', text: e.message }) }
    setSaving(false)
  }

  const createNewProfile = async () => {
    if (!newProfileName.trim()) return
    setCreatingProfile(true); setMsg(null)
    try {
      const truth = newProfileParsed
        ? JSON.parse(JSON.stringify(newProfileParsed))
        : { profile: { name: newProfileName.trim() }, experiences: [], education: [], skills: {}, certifications: [], summaries: {} }
      if (!truth.profile) truth.profile = {}
      if (!truth.profile.name) truth.profile.name = newProfileName.trim()
      const r = await apiFetch('/api/profiles', { method: 'POST', body: JSON.stringify({ profile_name: newProfileName.trim(), truth }) })
      if (!r.ok) {
        const d = await r.json().catch(() => ({}))
        setMsg({ type: 'err', text: d.error || `Erreur serveur (${r.status})` })
        setCreatingProfile(false)
        return
      }
      const d = await r.json()
      if (!d.ok) {
        setMsg({ type: 'err', text: d.error || 'Le serveur n\'a pas pu créer le profil' })
        setCreatingProfile(false)
        return
      }
      // Success — clear form and refresh everything
      const name = newProfileName.trim()
      setNewProfileName(''); setShowNewProfile(false); setNewProfileCv(null); setNewProfileParsed(null)
      setMsg({ type: 'ok', text: `Profil "${name}" créé` })
      await loadAll()
      if (onProfileChange) onProfileChange()
      if (onRescan) onRescan()
    } catch (e) {
      console.error('[createProfile] error:', e)
      setMsg({ type: 'err', text: `Erreur création: ${e.message || 'connexion serveur'}` })
    }
    setCreatingProfile(false)
  }

  const handleNewProfileCv = async (e) => {
    const file = e.target?.files?.[0]
    if (!file) return
    setNewProfileCv(file); setMsg(null)
    setNewProfileParsing(true)
    try {
      const fd = new FormData(); fd.append('file', file)
      const r = await apiFetch('/api/parse-cv', { method: 'POST', body: fd, headers: {} })
      const d = await r.json()
      if (d.ok && d.truth) {
        setNewProfileParsed(d.truth)
        if (!newProfileName.trim() && d.truth.profile?.name) setNewProfileName(d.truth.profile.name)
        const exp = d.truth.experiences?.length || 0
        const edu = d.truth.education?.length || 0
        setMsg({ type: 'ok', text: `CV analysé: ${exp} expériences, ${edu} formations extraites` })
      } else {
        setNewProfileCv(null)
        setMsg({ type: 'err', text: d.error || 'Impossible d\'analyser le CV' })
      }
    } catch (e) {
      setNewProfileCv(null)
      console.error('handleNewProfileCv error:', e)
      setMsg({ type: 'err', text: `Erreur analyse CV: ${e.message || 'connexion serveur'}` })
    }
    setNewProfileParsing(false)
    if (e.target) e.target.value = ''
  }

  const switchProfile = async (profileId) => {
    if (profileId === activeProfile) return
    setSaving(true); setMsg(null)
    try {
      await apiFetch(`/api/profiles/${profileId}/activate`, { method: 'POST' })
      await loadAll()
      if (onProfileChange) onProfileChange()
      if (onRescan) onRescan()
      setMsg({ type: 'ok', text: 'Profil activé' })
    } catch { setMsg({ type: 'err', text: 'Erreur changement de profil' }) }
    setSaving(false)
  }

  const toggleArr = (key, val) => setEditPrefs(p => ({ ...p, [key]: (p[key] || []).includes(val) ? p[key].filter(v => v !== val) : [...(p[key] || []), val] }))
  const addToArr = (key) => { const v = inputVals[key]?.trim(); if (v && !(editPrefs[key] || []).includes(v)) setEditPrefs(p => ({ ...p, [key]: [...(p[key] || []), v] })); setInputVals(iv => ({ ...iv, [key]: '' })) }
  const rmFromArr = (key, val) => setEditPrefs(p => ({ ...p, [key]: (p[key] || []).filter(v => v !== val) }))

  const chip = (label, active, onClick) => (
    <button key={label} onClick={onClick} style={{ padding: '5px 12px', borderRadius: 20, fontSize: 11, fontWeight: 600, cursor: 'pointer', background: active ? 'var(--bg-active)' : 'transparent', color: active ? 'var(--text-primary)' : 'var(--text-muted)', border: active ? '1px solid var(--text-muted)' : '1px solid var(--border)', transition: 'all 0.15s' }}>{label}</button>
  )

  const tagInput = (key, placeholder) => (
    <div>
      <div style={{ display: 'flex', gap: 6, marginBottom: 6 }}>
        <input value={inputVals[key] || ''} onChange={e => setInputVals(v => ({ ...v, [key]: e.target.value }))} onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addToArr(key))} placeholder={placeholder} style={{ flex: 1, padding: '7px 10px', background: 'var(--bg-base)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-primary)', fontSize: 12, outline: 'none' }} />
        <button onClick={() => addToArr(key)} style={{ padding: '7px 10px', background: 'var(--bg-base)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-secondary)', fontSize: 12, fontWeight: 700, cursor: 'pointer' }}>+</button>
      </div>
      {(editPrefs?.[key] || []).length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {(editPrefs[key] || []).map(k => (
            <span key={k} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '3px 8px', background: 'var(--bg-active)', color: 'var(--text-primary)', borderRadius: 12, fontSize: 11, border: '1px solid var(--border)' }}>
              {k}<button onClick={() => rmFromArr(key, k)} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 12, padding: 0 }}>x</button>
            </span>
          ))}
        </div>
      )}
    </div>
  )

  // ── Edit helpers ──────────────────────────────────────────────────────────
  const INP = { padding: '7px 10px', background: 'var(--bg-base)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-primary)', fontSize: 12, outline: 'none', width: '100%' }
  const LBL = { fontSize: 10, color: 'var(--text-muted)', marginBottom: 3, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', display: 'block' }
  const startEdit = (section) => { setEditSection(section); setEditTruth(JSON.parse(JSON.stringify(truth))) }
  const cancelEdit = () => setEditSection(null)

  const setExp = (i, patch) => setEditTruth(t => { const a = [...t.experiences]; a[i] = { ...a[i], ...patch }; return { ...t, experiences: a } })
  const setExpTitle = (i, track, v) => setEditTruth(t => { const a = [...t.experiences]; a[i] = { ...a[i], titles: { ...a[i].titles, [track]: v } }; return { ...t, experiences: a } })
  const setExpStack = (i, stack) => setExp(i, { stack })
  const setExpBullets = (i, bullets) => setEditTruth(t => { const a = [...t.experiences]; a[i] = { ...a[i], bullets_pool: { ...(a[i].bullets_pool || {}), tech: bullets } }; return { ...t, experiences: a } })

  const setEdu = (i, patch) => setEditTruth(t => { const a = [...t.education]; a[i] = { ...a[i], ...patch }; return { ...t, education: a } })

  const setSkill = (track, cat, val) => setEditTruth(t => ({ ...t, skills: { ...t.skills, [track]: { ...(t.skills?.[track] || {}), [cat]: val } } }))
  const renameSkill = (track, old, newKey) => setEditTruth(t => {
    const cats = t.skills?.[track] || {}
    const rebuilt = {}
    Object.entries(cats).forEach(([k, v]) => { rebuilt[k === old ? newKey : k] = v })
    return { ...t, skills: { ...t.skills, [track]: rebuilt } }
  })
  const removeSkillCat = (track, cat) => setEditTruth(t => { const c = { ...(t.skills?.[track] || {}) }; delete c[cat]; return { ...t, skills: { ...t.skills, [track]: c } } })

  const [newStackVal, setNewStackVal] = useState({})
  const [skillTrack, setSkillTrack] = useState('tech')

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>Chargement...</div>

  const activeP = profiles.find(p => p.id === activeProfile)
  const CARD = { background: 'var(--bg-raised)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '14px 16px' }
  const SECTION_HDR = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }
  const SECTION_TITLE = { fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }
  const EDIT_BTN = { fontSize: 10, padding: '3px 8px', background: 'var(--bg-base)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-muted)', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 3 }
  const SAVE_BTN = { fontSize: 10, padding: '3px 10px', background: 'var(--accent)', border: 'none', borderRadius: 'var(--radius-sm)', color: '#fff', cursor: 'pointer', fontWeight: 700 }
  const CANCEL_BTN = { fontSize: 10, padding: '3px 8px', background: 'var(--bg-base)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-muted)', cursor: 'pointer' }
  const EditPencil = () => <svg width="10" height="10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
  const SectionActions = ({ section }) => editSection !== section ? (
    <button onClick={() => startEdit(section)} style={EDIT_BTN}><EditPencil /> Modifier</button>
  ) : (
    <div style={{ display: 'flex', gap: 4 }}>
      <button onClick={saveTruth} disabled={saving} style={SAVE_BTN}>{saving ? '...' : 'Sauvegarder'}</button>
      <button onClick={cancelEdit} style={CANCEL_BTN}>Annuler</button>
    </div>
  )

  return (
    <div style={{ padding: '16px 20px' }}>

      {/* Profile dropdown + new profile button */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <div style={{ position: 'relative', flex: 1, maxWidth: 360 }}>
          <button onClick={() => setProfileDropOpen(v => !v)}
            style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', background: 'var(--bg-raised)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', cursor: 'pointer', transition: 'border-color 0.15s', borderColor: profileDropOpen ? 'var(--accent)' : 'var(--border)' }}>
            <div style={{ width: 22, height: 22, borderRadius: '50%', background: 'var(--accent)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 9, fontWeight: 700, color: '#fff', flexShrink: 0 }}>
              {activeP?.completeness || 0}%
            </div>
            <div style={{ flex: 1, textAlign: 'left', minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{activeP?.name || 'Aucun profil'}</div>
              <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{activeP?.type || 'EMPLOYEE'} · {activeP?.experiences_count || 0} exp</div>
            </div>
            <svg width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="var(--text-muted)" strokeWidth={2.5} style={{ flexShrink: 0, transform: profileDropOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s' }}><path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" /></svg>
          </button>
          {profileDropOpen && (
            <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, marginTop: 4, background: 'var(--bg-raised)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', zIndex: 100, boxShadow: '0 8px 24px rgba(0,0,0,0.35)', overflow: 'hidden' }}>
              {[...profiles].sort((a, b) => (a.created || '').localeCompare(b.created || '')).map((p, i) => (
                <button key={p.id} onClick={async () => { setProfileDropOpen(false); if (p.id !== activeProfile) await switchProfile(p.id) }}
                  style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 8, padding: '9px 12px', background: p.id === activeProfile ? 'var(--bg-active)' : 'transparent', border: 'none', cursor: 'pointer', textAlign: 'left', borderBottom: i < profiles.length - 1 ? '1px solid var(--border)' : 'none' }}
                  onMouseEnter={e => { if (p.id !== activeProfile) e.currentTarget.style.background = 'var(--bg-surface)' }}
                  onMouseLeave={e => { if (p.id !== activeProfile) e.currentTarget.style.background = 'transparent' }}>
                  <div style={{ width: 18, height: 18, borderRadius: '50%', background: p.id === activeProfile ? 'var(--accent)' : 'var(--bg-base)', border: p.id === activeProfile ? 'none' : '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 8, fontWeight: 700, color: p.id === activeProfile ? '#fff' : 'var(--text-muted)', flexShrink: 0 }}>
                    {p.completeness}%
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: p.id === activeProfile ? 'var(--text-primary)' : 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {p.name}{i === 0 && <span style={{ fontSize: 9, color: 'var(--text-muted)', fontWeight: 400, marginLeft: 6 }}>défaut</span>}
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{p.type} · {p.experiences_count || 0} exp · {p.education_count || 0} form</div>
                  </div>
                  {p.id === activeProfile && <svg width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="var(--green)" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>}
                </button>
              ))}
            </div>
          )}
        </div>
        <button onClick={() => { setShowNewProfile(v => !v); setProfileDropOpen(false) }}
          style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '8px 14px', borderRadius: 'var(--radius-sm)', background: showNewProfile ? 'var(--bg-active)' : 'var(--bg-raised)', border: '1px solid var(--border)', cursor: 'pointer', color: 'var(--text-secondary)', fontSize: 11, fontWeight: 600, transition: 'all 0.15s', flexShrink: 0 }}
          onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-active)'}
          onMouseLeave={e => { if (!showNewProfile) e.currentTarget.style.background = 'var(--bg-raised)' }}>
          <svg width="10" height="10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" /></svg>
          Nouveau profil
        </button>
      </div>

      {/* New profile form */}
      {showNewProfile && (
        <div style={{ background: 'var(--bg-raised)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '16px', marginBottom: 12 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 10 }}>Créer un nouveau profil</div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
            <input autoFocus value={newProfileName} onChange={e => setNewProfileName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && !newProfileParsing && createNewProfile()}
              placeholder="Nom du profil (ex: Dev Fullstack, Data Engineer...)"
              style={{ flex: 1, padding: '8px 12px', background: 'var(--bg-base)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-primary)', fontSize: 12, outline: 'none' }} />
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '7px 12px', background: 'var(--bg-base)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontSize: 11, color: 'var(--text-secondary)', transition: 'background 0.15s' }}
              onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-active)'}
              onMouseLeave={e => e.currentTarget.style.background = 'var(--bg-base)'}>
              <svg width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" /></svg>
              {newProfileParsing && <div style={{ width: 10, height: 10, border: '2px solid var(--accent)', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 0.7s linear infinite' }} />}
              {newProfileParsing ? 'Analyse du CV...' : 'Importer un CV (PDF)'}
              <input type="file" accept=".pdf,.doc,.docx,.txt" onChange={handleNewProfileCv} disabled={newProfileParsing} style={{ display: 'none' }} />
            </label>
            {newProfileCv && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{newProfileCv.name}</span>}
            {newProfileParsed && (
              <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 8, background: 'var(--green-dim)', color: 'var(--green)', border: '1px solid var(--green)', fontWeight: 600 }}>
                CV analysé · {newProfileParsed.experiences?.length || 0} exp · {newProfileParsed.education?.length || 0} form
              </span>
            )}
            <span style={{ flex: 1 }} />
            <span style={{ fontSize: 10, color: 'var(--text-muted)', fontStyle: 'italic' }}>CV optionnel, vous pourrez compléter après</span>
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button onClick={createNewProfile} disabled={creatingProfile || newProfileParsing || !newProfileName.trim()}
              style={{ padding: '8px 18px', background: 'var(--accent)', border: 'none', borderRadius: 'var(--radius-sm)', color: '#fff', fontSize: 12, fontWeight: 700, cursor: 'pointer', opacity: (!newProfileName.trim() || creatingProfile || newProfileParsing) ? 0.5 : 1 }}>
              {creatingProfile ? 'Création...' : 'Créer le profil'}
            </button>
            <button onClick={() => { setShowNewProfile(false); setNewProfileName(''); setNewProfileCv(null); setNewProfileParsed(null) }}
              style={{ padding: '8px 14px', background: 'var(--bg-base)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-muted)', fontSize: 12, cursor: 'pointer' }}>
              Annuler
            </button>
          </div>
        </div>
      )}

      {msg && (
        <div style={{ padding: '8px 12px', borderRadius: 'var(--radius-sm)', fontSize: 11, background: msg.type === 'ok' ? 'var(--green-dim)' : 'var(--red-dim)', color: msg.type === 'ok' ? 'var(--green)' : 'var(--red)', border: `1px solid ${msg.type === 'ok' ? 'var(--green)' : 'var(--red)'}`, marginBottom: 10 }}>
          {msg.text}
        </div>
      )}

      {truth && truth.profile && (
        <div style={{ display: 'grid', gridTemplateColumns: '5fr 7fr', gap: 12, alignItems: 'start' }}>

          {/* ── LEFT COLUMN ── */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {/* Personal Info */}
          <div style={CARD}>
            <div style={SECTION_HDR}>
              <div style={SECTION_TITLE}>Informations personnelles</div>
              <SectionActions section="personal" />
            </div>
            {editSection === 'personal' && editTruth ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  {[['Nom', 'name'], ['Email', 'email'], ['Tel', 'phone'], ['LinkedIn', 'linkedin'], ['GitHub', 'github'], ['Lieu', 'location']].map(([label, key]) => (
                    <div key={key}>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 3, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>{label}</div>
                      <input value={editTruth.profile[key] || ''} onChange={e => setEditTruth(t => ({ ...t, profile: { ...t.profile, [key]: e.target.value } }))}
                        style={{ width: '100%', padding: '7px 10px', background: 'var(--bg-base)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-primary)', fontSize: 12, outline: 'none' }} />
                    </div>
                  ))}
                </div>
                <div>
                  <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Langues</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {(editTruth.profile.languages || []).map((lang, li) => (
                      <div key={li} style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                        <input value={lang.lang || ''} onChange={e => setEditTruth(t => { const l = [...(t.profile.languages || [])]; l[li] = { ...l[li], lang: e.target.value }; return { ...t, profile: { ...t.profile, languages: l } } })}
                          placeholder="Langue" style={{ flex: 1, padding: '6px 8px', background: 'var(--bg-base)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-primary)', fontSize: 11, outline: 'none' }} />
                        <input value={lang.level || ''} onChange={e => setEditTruth(t => { const l = [...(t.profile.languages || [])]; l[li] = { ...l[li], level: e.target.value }; return { ...t, profile: { ...t.profile, languages: l } } })}
                          placeholder="Niveau" style={{ width: 100, padding: '6px 8px', background: 'var(--bg-base)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-primary)', fontSize: 11, outline: 'none' }} />
                        <button onClick={() => setEditTruth(t => ({ ...t, profile: { ...t.profile, languages: (t.profile.languages || []).filter((_, i) => i !== li) } }))} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 14, padding: '0 4px' }}>×</button>
                      </div>
                    ))}
                    <button onClick={() => setEditTruth(t => ({ ...t, profile: { ...t.profile, languages: [...(t.profile.languages || []), { lang: '', level: '' }] } }))} style={{ alignSelf: 'flex-start', fontSize: 11, color: 'var(--text-muted)', background: 'none', border: '1px dashed var(--border)', borderRadius: 'var(--radius-sm)', padding: '4px 10px', cursor: 'pointer' }}>+ Ajouter une langue</button>
                  </div>
                </div>
              </div>
            ) : (
              <>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, fontSize: 12 }}>
                  {[['Nom', truth.profile.name], ['Email', truth.profile.email], ['Tel', truth.profile.phone], ['LinkedIn', truth.profile.linkedin], ['Lieu', truth.profile.location], ['GitHub', truth.profile.github]].map(([l, v]) => v ? (
                    <div key={l}><span style={{ color: 'var(--text-muted)' }}>{l}:</span> <span style={{ color: 'var(--text-primary)' }}>{v}</span></div>
                  ) : <div key={l} style={{ color: 'var(--text-muted)', opacity: 0.4, fontSize: 11 }}>{l}: —</div>)}
                </div>
                {truth.profile.languages?.length > 0 && (
                  <div style={{ marginTop: 8, fontSize: 11, color: 'var(--text-muted)' }}>Langues: {truth.profile.languages.map(l => `${l.lang} (${l.level})`).join(', ')}</div>
                )}
              </>
            )}
          </div>

          {/* ── Compétences ── */}
          <div style={CARD}>
            <div style={SECTION_HDR}>
              <div style={SECTION_TITLE}>Compétences techniques</div>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                {editSection === 'skills' && (
                  <div style={{ display: 'flex', background: 'var(--bg-base)', borderRadius: 4, border: '1px solid var(--border)', padding: 1, gap: 1 }}>
                    {['tech', 'consulting'].map(t => (
                      <button key={t} onClick={() => setSkillTrack(t)} style={{ padding: '2px 8px', borderRadius: 3, fontSize: 10, cursor: 'pointer', background: skillTrack === t ? 'var(--bg-active)' : 'transparent', color: skillTrack === t ? 'var(--text-primary)' : 'var(--text-muted)', border: 'none', fontWeight: 600 }}>{t}</button>
                    ))}
                  </div>
                )}
                {editSection !== 'skills' ? (
                  <button onClick={() => { startEdit('skills'); setSkillTrack('tech') }} style={EDIT_BTN}><EditPencil /> Modifier</button>
                ) : (
                  <div style={{ display: 'flex', gap: 4 }}>
                    <button onClick={saveTruth} disabled={saving} style={SAVE_BTN}>{saving ? '...' : 'Sauvegarder'}</button>
                    <button onClick={cancelEdit} style={CANCEL_BTN}>Annuler</button>
                  </div>
                )}
              </div>
            </div>
            {editSection === 'skills' && editTruth ? (
              <div>
                <div style={{ display: 'flex', background: 'var(--bg-base)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)', padding: 2, gap: 2, marginBottom: 12, width: 'fit-content' }}>
                  {['tech', 'consulting'].map(t => (
                    <button key={t} onClick={() => setSkillTrack(t)} style={{ padding: '5px 14px', borderRadius: 6, fontSize: 11, fontWeight: 600, cursor: 'pointer', background: skillTrack === t ? 'var(--bg-active)' : 'transparent', color: skillTrack === t ? 'var(--text-primary)' : 'var(--text-muted)', border: 'none' }}>{t}</button>
                  ))}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {Object.entries(editTruth.skills?.[skillTrack] || {}).map(([cat, val], i) => (
                    <div key={i} style={{ display: 'flex', gap: 6, alignItems: 'flex-start' }}>
                      <input value={cat} onChange={e => renameSkill(skillTrack, cat, e.target.value)}
                        style={{ ...INP, width: 150, flexShrink: 0, fontSize: 11, fontWeight: 600 }} />
                      <input value={val} onChange={e => setSkill(skillTrack, cat, e.target.value)}
                        style={{ ...INP, flex: 1, fontSize: 11 }} />
                      <button onClick={() => removeSkillCat(skillTrack, cat)} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 16, paddingTop: 6, flexShrink: 0 }}>×</button>
                    </div>
                  ))}
                  <button onClick={() => setEditTruth(t => ({ ...t, skills: { ...t.skills, [skillTrack]: { ...(t.skills?.[skillTrack] || {}), 'Nouvelle categorie': '' } } }))}
                    style={{ alignSelf: 'flex-start', fontSize: 11, color: 'var(--text-muted)', background: 'none', border: '1px dashed var(--border)', borderRadius: 'var(--radius-sm)', padding: '4px 12px', cursor: 'pointer' }}>
                    + Ajouter une catégorie
                  </button>
                </div>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {Object.entries(truth.skills?.tech || {}).map(([cat, val]) => (
                  <div key={cat} style={{ marginBottom: 2 }}>
                    <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>{cat}</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
                      {val.split(',').map((s, si) => (
                        <span key={si} style={{ fontSize: 10, padding: '2px 7px', background: 'var(--bg-active)', color: 'var(--text-secondary)', borderRadius: 10, border: '1px solid var(--border)' }}>{s.trim()}</span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* ── Certifications ── */}
          <div style={CARD}>
            <div style={SECTION_HDR}>
              <div style={SECTION_TITLE}>Certifications ({(editSection === 'certifications' ? editTruth : truth).certifications?.length || 0})</div>
              <SectionActions section="certifications" />
            </div>
            {editSection === 'certifications' && editTruth ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {(editTruth.certifications || []).map((c, i) => (
                  <div key={i} style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                    <input value={c} onChange={e => setEditTruth(t => { const a = [...(t.certifications || [])]; a[i] = e.target.value; return { ...t, certifications: a } })} style={INP} />
                    <button onClick={() => setEditTruth(t => ({ ...t, certifications: (t.certifications || []).filter((_, ci) => ci !== i) }))} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 16, flexShrink: 0 }}>×</button>
                  </div>
                ))}
                <button onClick={() => setEditTruth(t => ({ ...t, certifications: [...(t.certifications || []), ''] }))}
                  style={{ alignSelf: 'flex-start', fontSize: 11, color: 'var(--text-muted)', background: 'none', border: '1px dashed var(--border)', borderRadius: 'var(--radius-sm)', padding: '4px 12px', cursor: 'pointer' }}>
                  + Ajouter une certification
                </button>
              </div>
            ) : (
              <div>
                {(truth.certifications || []).length === 0
                  ? <div style={{ fontSize: 12, color: 'var(--text-muted)', opacity: 0.5 }}>Aucune certification ajoutée.</div>
                  : (truth.certifications || []).map((c, i) => (
                    <div key={i} style={{ fontSize: 11, color: 'var(--text-muted)', padding: '3px 0' }}>• {c}</div>
                  ))
                }
              </div>
            )}
          </div>

          </div>{/* end left col */}

          {/* ── RIGHT COLUMN ── */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>

          {/* ── Experiences ──────────────────────────────────── */}
          <div style={CARD}>
            <div style={SECTION_HDR}>
              <div style={SECTION_TITLE}>Experiences ({(editSection === 'experiences' ? editTruth : truth).experiences?.length || 0})</div>
              <SectionActions section="experiences" />
            </div>

            {editSection === 'experiences' && editTruth ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                {editTruth.experiences.map((exp, i) => (
                  <div key={i} style={{ padding: '14px', background: 'var(--bg-base)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                      <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Experience {i + 1}</div>
                      <button onClick={() => setEditTruth(t => ({ ...t, experiences: t.experiences.filter((_, ei) => ei !== i) }))} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 16, lineHeight: 1 }}>×</button>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 10 }}>
                      {[['Entreprise', 'company'], ['Localisation', 'location'], ['Debut', 'date_start'], ['Fin', 'date_end']].map(([label, key]) => (
                        <div key={key}>
                          <label style={LBL}>{label}</label>
                          <input value={exp[key] || ''} onChange={e => setExp(i, { [key]: e.target.value })} style={INP} />
                        </div>
                      ))}
                      <div>
                        <label style={LBL}>Titre (tech)</label>
                        <input value={exp.titles?.tech || ''} onChange={e => setExpTitle(i, 'tech', e.target.value)} style={INP} />
                      </div>
                      <div>
                        <label style={LBL}>Titre (consulting)</label>
                        <input value={exp.titles?.consulting || ''} onChange={e => setExpTitle(i, 'consulting', e.target.value)} style={INP} />
                      </div>
                    </div>
                    {/* Stack */}
                    <div style={{ marginBottom: 10 }}>
                      <label style={LBL}>Stack</label>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 6 }}>
                        {(exp.stack || []).map((s, si) => (
                          <span key={si} style={{ display: 'inline-flex', alignItems: 'center', gap: 3, padding: '2px 8px', background: 'var(--bg-active)', color: 'var(--text-primary)', borderRadius: 10, fontSize: 11, border: '1px solid var(--border)' }}>
                            {s}
                            <button onClick={() => setExpStack(i, exp.stack.filter((_, xi) => xi !== si))} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 13, padding: 0, lineHeight: 1 }}>×</button>
                          </span>
                        ))}
                      </div>
                      <div style={{ display: 'flex', gap: 6 }}>
                        <input value={newStackVal[i] || ''} onChange={e => setNewStackVal(v => ({ ...v, [i]: e.target.value }))}
                          onKeyDown={e => { if (e.key === 'Enter' && (newStackVal[i] || '').trim()) { setExpStack(i, [...(exp.stack || []), newStackVal[i].trim()]); setNewStackVal(v => ({ ...v, [i]: '' })) } }}
                          placeholder="ex: Docker" style={{ ...INP, width: 'auto', flex: 1 }} />
                        <button onClick={() => { if ((newStackVal[i] || '').trim()) { setExpStack(i, [...(exp.stack || []), newStackVal[i].trim()]); setNewStackVal(v => ({ ...v, [i]: '' })) } }}
                          style={{ padding: '7px 12px', background: 'var(--bg-active)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-secondary)', fontSize: 12, cursor: 'pointer' }}>+</button>
                      </div>
                    </div>
                    {/* Bullets */}
                    <div>
                      <label style={LBL}>Bullets</label>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                        {(exp.bullets_pool?.tech || []).map((b, bi) => (
                          <div key={bi} style={{ display: 'flex', gap: 6, alignItems: 'flex-start' }}>
                            <textarea value={b} onChange={e => { const bullets = [...(exp.bullets_pool?.tech || [])]; bullets[bi] = e.target.value; setExpBullets(i, bullets) }}
                              style={{ flex: 1, padding: '7px 10px', background: 'var(--bg-base)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-primary)', fontSize: 11, lineHeight: 1.5, resize: 'vertical', outline: 'none', fontFamily: 'inherit', minHeight: 60 }} />
                            <button onClick={() => setExpBullets(i, (exp.bullets_pool?.tech || []).filter((_, bi2) => bi2 !== bi))}
                              style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 16, paddingTop: 8, flexShrink: 0 }}>×</button>
                          </div>
                        ))}
                        <button onClick={() => setExpBullets(i, [...(exp.bullets_pool?.tech || []), ''])}
                          style={{ alignSelf: 'flex-start', fontSize: 11, color: 'var(--text-muted)', background: 'none', border: '1px dashed var(--border)', borderRadius: 'var(--radius-sm)', padding: '4px 12px', cursor: 'pointer' }}>+ Ajouter un bullet</button>
                      </div>
                    </div>
                  </div>
                ))}
                <button onClick={() => setEditTruth(t => ({ ...t, experiences: [...(t.experiences || []), { id: `exp_${Date.now()}`, company: '', titles: { tech: '', consulting: '' }, date_start: '', date_end: '', location: '', stack: [], bullets_pool: { tech: [] } }] }))}
                  style={{ padding: '10px', background: 'transparent', border: '1px dashed var(--border-light)', borderRadius: 'var(--radius-sm)', color: 'var(--text-muted)', fontSize: 12, cursor: 'pointer', width: '100%' }}>
                  + Ajouter une experience
                </button>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {(truth.experiences || []).map((exp, i) => {
                  const isExpanded = expandedExp[i]
                  const bullets = exp.bullets_pool?.tech || exp.bullets_pool?.consulting || []
                  return (
                    <div key={i} style={{ padding: '12px 14px', background: 'var(--bg-base)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 4 }}>
                        <div>
                          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{exp.company}</div>
                          <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 1 }}>{exp.titles?.tech || exp.titles?.consulting || ''} {exp.location ? `· ${exp.location}` : ''}</div>
                        </div>
                        <div style={{ fontSize: 10, color: 'var(--text-muted)', flexShrink: 0, marginLeft: 8 }}>{exp.date_start} — {exp.date_end || 'Present'}</div>
                      </div>
                      {exp.stack?.length > 0 && <div style={{ fontSize: 10, color: 'var(--accent)', marginBottom: 6, marginTop: 4, fontFamily: 'monospace' }}>{exp.stack.join(' · ')}</div>}
                      {bullets.length > 0 && (
                        <div>
                          {(isExpanded ? bullets : bullets.slice(0, 3)).map((b, j) => (
                            <div key={j} style={{ fontSize: 11, color: 'var(--text-muted)', paddingLeft: 10, borderLeft: '2px solid var(--border)', lineHeight: 1.5, marginBottom: 3 }}>{b}</div>
                          ))}
                          {bullets.length > 3 && (
                            <button onClick={() => setExpandedExp(e => ({ ...e, [i]: !e[i] }))} style={{ marginTop: 4, fontSize: 10, color: 'var(--text-muted)', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline', padding: 0 }}>
                              {isExpanded ? 'Voir moins' : `+ ${bullets.length - 3} autres bullets`}
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {/* ── Formation ──────────────────────────────────── */}
          <div style={CARD}>
            <div style={SECTION_HDR}>
              <div style={SECTION_TITLE}>Formation ({(editSection === 'education' ? editTruth : truth).education?.length || 0})</div>
              <SectionActions section="education" />
            </div>
            {editSection === 'education' && editTruth ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {editTruth.education.map((edu, i) => (
                  <div key={i} style={{ padding: '14px', background: 'var(--bg-base)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                      <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Formation {i + 1}</div>
                      <button onClick={() => setEditTruth(t => ({ ...t, education: t.education.filter((_, ei) => ei !== i) }))} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 16 }}>×</button>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                      <div style={{ gridColumn: '1 / -1' }}>
                        <label style={LBL}>Etablissement</label>
                        <input value={edu.school || ''} onChange={e => setEdu(i, { school: e.target.value })} style={INP} />
                      </div>
                      <div style={{ gridColumn: '1 / -1' }}>
                        <label style={LBL}>Diplôme / Mention</label>
                        <input value={edu.degree || ''} onChange={e => setEdu(i, { degree: e.target.value })} style={INP} />
                      </div>
                      {[['Debut', 'date_start'], ['Fin', 'date_end'], ['Lieu', 'location']].map(([label, key]) => (
                        <div key={key}>
                          <label style={LBL}>{label}</label>
                          <input value={edu[key] || ''} onChange={e => setEdu(i, { [key]: e.target.value })} style={INP} />
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
                <button onClick={() => setEditTruth(t => ({ ...t, education: [...(t.education || []), { id: `edu_${Date.now()}`, school: '', degree: '', date_start: '', date_end: '', location: '' }] }))}
                  style={{ padding: '10px', background: 'transparent', border: '1px dashed var(--border-light)', borderRadius: 'var(--radius-sm)', color: 'var(--text-muted)', fontSize: 12, cursor: 'pointer', width: '100%' }}>
                  + Ajouter une formation
                </button>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
                {(truth.education || []).map((edu, i) => (
                  <div key={i} style={{ padding: '10px 0', borderBottom: i < (truth.education.length - 1) ? '1px solid var(--border)' : 'none' }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>{edu.school}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 1 }}>{edu.degree} {edu.date_start && `(${edu.date_start}–${edu.date_end || ''})`}</div>
                    {edu.location && <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 1 }}>{edu.location}</div>}
                  </div>
                ))}
              </div>
            )}
          </div>

          </div>
        </div>
      )}

      {/* ── Preferences (collapsible) ── */}
      {editPrefs && (() => {
        const [open, setOpen] = [prefsOpen, setPrefsOpen]
        return (
          <div style={{ ...CARD, marginTop: 10 }}>
            <button onClick={() => setOpen(o => !o)} style={{ width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
              <div style={SECTION_TITLE}>Preferences de recherche</div>
              <svg width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="var(--text-muted)" strokeWidth={2.5} style={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s', flexShrink: 0 }}><path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" /></svg>
            </button>
            {open && (
              <div style={{ marginTop: 12, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
                <div>
                  <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4 }}>Titre actuel</div>
                  <input value={editPrefs.current_title || ''} onChange={e => setEditPrefs(p => ({ ...p, current_title: e.target.value }))} style={INP} />
                </div>
                <div>
                  <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4 }}>Experience max</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {[{ v: 0, l: 'Etudiant' }, { v: 1, l: '0-1 an' }, { v: 3, l: '1-3 ans' }, { v: 5, l: '3-5 ans' }, { v: 8, l: '5-8 ans' }, { v: 10, l: '8-10 ans' }, { v: 15, l: '10+' }].map(c =>
                      chip(c.l, editPrefs.experience_max === c.v, () => setEditPrefs(p => ({ ...p, experience_max: c.v })))
                    )}
                  </div>
                </div>
                <div style={{ gridColumn: '1 / -1' }}>
                  <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4 }}>Titres de poste recherches</div>
                  {tagInput('titles_target', 'ex: Consultant SAP, Developpeur React...')}
                </div>
                <div>
                  <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4 }}>Competences principales</div>
                  {tagInput('skills_core', 'ex: SAP, React, Python...')}
                </div>
                <div>
                  <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4 }}>Technologies a exclure</div>
                  {tagInput('skills_exclude', 'ex: PHP, Salesforce...')}
                </div>
                <div>
                  <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4 }}>Contrats</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {['CDI', 'CDD', 'Alternance', 'Stage', 'Freelance'].map(c => chip(c, (editPrefs.contracts || []).includes(c), () => toggleArr('contracts', c)))}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4 }}>Villes</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {['Paris', 'Lyon', 'Marseille', 'Lille', 'Toulouse', 'Bordeaux', 'Nantes', 'Nice', 'Montpellier', 'Strasbourg', 'Rennes', 'Grenoble', 'Remote'].map(c => chip(c, (editPrefs.cities || []).includes(c), () => toggleArr('cities', c)))}
                  </div>
                </div>
                <div style={{ gridColumn: '1 / -1', display: 'flex', gap: 8, marginTop: 4 }}>
                  <button onClick={savePrefs} disabled={saving} style={{ padding: '8px 18px', background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 'var(--radius-sm)', fontSize: 12, fontWeight: 600, cursor: saving ? 'wait' : 'pointer' }}>
                    {saving ? 'Sauvegarde...' : 'Sauvegarder'}
                  </button>
                  <button onClick={async () => { await savePrefs(); if (onRescan) onRescan() }} disabled={saving} style={{ padding: '8px 18px', background: 'var(--bg-active)', color: 'var(--text-primary)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>
                    Sauvegarder et re-scanner
                  </button>
                </div>
              </div>
            )}
          </div>
        )
      })()}
    </div>
  )
}

// ─── Template Library ────────────────────────────────────────────────────────

function TemplateLibrary({ onSelect }) {
  const [data, setData] = useState(null)
  const [tab, setTab] = useState('letter') // 'cv' | 'letter'
  const [selected, setSelected] = useState(null)
  const [previewUrl, setPreviewUrl] = useState(null)
  const [loadingPreview, setLoadingPreview] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    apiFetch('/api/templates/library').then(r => r.json()).then(setData).catch(() => {})
  }, [])

  const templates = tab === 'cv' ? (data?.cvs || []) : (data?.letters || [])

  // Auto-load first template preview
  useEffect(() => {
    if (templates.length && !selected) {
      loadPreview(templates[0])
    }
  }, [templates.length, tab])

  const loadPreview = async (tpl) => {
    setSelected(tpl.id)
    setLoadingPreview(true)
    try {
      const r = await apiFetch(tpl.preview_url)
      if (previewUrl) URL.revokeObjectURL(previewUrl)
      const blob = await r.blob()
      setPreviewUrl(URL.createObjectURL(blob))
    } catch {}
    setLoadingPreview(false)
  }

  const handleSelect = async (id) => {
    setSaving(true)
    try {
      await apiFetch('/api/templates/library/select', { method: 'POST', body: JSON.stringify({ letter_id: id }) })
      if (onSelect) onSelect(id)
    } catch {}
    setSaving(false)
  }

  if (!data) return <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>Chargement...</div>

  return (
    <div style={{ display: 'flex', gap: 20, minHeight: 500 }}>
      {/* Template grid */}
      <div style={{ width: 300, flexShrink: 0 }}>
        {/* Tab toggle */}
        <div style={{ display: 'flex', background: 'var(--bg-base)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)', padding: 3, gap: 2, marginBottom: 14 }}>
          {[{ v: 'cv', l: 'CV' }, { v: 'letter', l: 'Lettre' }].map(t => (
            <button key={t.v} onClick={() => { setTab(t.v); setSelected(null); setPreviewUrl(null) }} style={{
              flex: 1, background: tab === t.v ? 'var(--bg-active)' : 'transparent',
              color: tab === t.v ? 'var(--text-primary)' : 'var(--text-muted)',
              border: 'none', borderRadius: 6, padding: '7px 12px', cursor: 'pointer', fontSize: 12, fontWeight: 600,
            }}>{t.l}</button>
          ))}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {templates.map(tpl => (
            <button key={tpl.id} onClick={() => loadPreview(tpl)} style={{
              display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px',
              background: selected === tpl.id ? 'var(--bg-active)' : 'var(--bg-raised)',
              border: selected === tpl.id ? '1px solid var(--accent)' : '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)', cursor: 'pointer', textAlign: 'left', transition: 'all 0.15s',
            }}>
              <div style={{ width: 36, height: 44, background: 'var(--bg-base)', border: '1px solid var(--border)', borderRadius: 4, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="var(--text-muted)" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
              </div>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: selected === tpl.id ? 'var(--text-primary)' : 'var(--text-secondary)' }}>{tpl.name}</div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>{tpl.style} — {tpl.desc}</div>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Preview */}
      <div style={{ flex: 1, background: 'var(--bg-raised)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        {!selected ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 10 }}>
            <svg width="32" height="32" fill="none" viewBox="0 0 24 24" stroke="var(--text-muted)" strokeWidth={1}><path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
            <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>Selectionnez un template pour l'apercu</div>
          </div>
        ) : loadingPreview ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ width: 20, height: 20, border: '2px solid var(--border)', borderTopColor: 'var(--text-muted)', borderRadius: '50%', animation: 'spin 0.7s linear infinite' }} />
          </div>
        ) : previewUrl ? (
          <>
            <iframe src={`${previewUrl}#toolbar=0&navpanes=0&zoom=67`} style={{ flex: 1, border: 'none', background: '#fff' }} title="Template preview" />
            <div style={{ padding: '10px 16px', borderTop: '1px solid var(--border)', display: 'flex', justifyContent: 'flex-end' }}>
              <button onClick={() => handleSelect(selected)} disabled={saving} style={{
                padding: '8px 20px', background: 'var(--accent)', color: '#fff', border: 'none',
                borderRadius: 'var(--radius-sm)', fontSize: 13, fontWeight: 600, cursor: saving ? 'wait' : 'pointer',
              }}>{saving ? 'Sauvegarde...' : 'Utiliser ce template'}</button>
            </div>
          </>
        ) : null}
      </div>
    </div>
  )
}

function TemplateEditor() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState(null)
  const [customCv, setCustomCv] = useState('')
  const [customLetter, setCustomLetter] = useState('')

  useEffect(() => {
    apiFetch('/api/templates').then(r => r.json()).then(d => {
      setData(d)
      setCustomCv(d.cv_custom || '')
      setCustomLetter(d.letter_custom || '')
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  const apiPut = async (body) => {
    setSaving(true); setMsg(null)
    try {
      const r = await apiFetch('/api/templates', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      const d = await r.json()
      if (d.ok) {
        setData(prev => ({
          ...prev, ...d.config,
          ...(body.cv_custom != null ? { cv_custom: body.cv_custom } : {}),
          ...(body.letter_custom != null ? { letter_custom: body.letter_custom } : {}),
        }))
        setMsg({ type: 'ok', text: 'Sauvegarde' })
      } else setMsg({ type: 'err', text: d.error || 'Erreur' })
    } catch (e) { setMsg({ type: 'err', text: e.message }) }
    finally { setSaving(false) }
  }

  const makeUploadHandler = (kind) => (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (ev) => {
      const content = ev.target.result
      if (kind === 'cv') { setCustomCv(content); apiPut({ cv_custom: content, cv_active: 'custom' }) }
      else { setCustomLetter(content); apiPut({ letter_custom: content, letter_active: 'custom' }) }
    }
    reader.readAsText(file)
    e.target.value = ''
  }

  if (loading || !data) return <div style={{ textAlign: 'center', padding: '80px 0', color: 'var(--text-muted)', fontSize: 14 }}>Chargement...</div>

  return (
    <div style={{ paddingTop: 24 }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>Templates</div>
        <div style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 4 }}>Visualisez et personnalisez vos templates CV et Lettre de motivation.</div>
      </div>

      {msg && (
        <div style={{ padding: '10px 16px', borderRadius: 'var(--radius-sm)', fontSize: 12, fontWeight: 500, background: msg.type === 'ok' ? 'var(--green-dim)' : 'var(--red-dim)', color: msg.type === 'ok' ? 'var(--green)' : 'var(--red)', border: `1px solid ${msg.type === 'ok' ? 'var(--green)' : 'var(--red)'}`, marginBottom: 16, animation: 'fadeUp 0.2s ease' }}>
          {msg.text}
        </div>
      )}

      {/* Template Library */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 14 }}>Choisir un template</div>
        <TemplateLibrary onSelect={(id) => setMsg({ type: 'ok', text: `Template "${id}" selectionne` })} />
      </div>

      {/* PDF Previews — side by side */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 24 }}>
        <TemplatePreview kind="cv" />
        <TemplatePreview kind="letter" />
      </div>

      {/* Template editors below */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        <TemplateCard
          kind="cv" label="CV" icon=""
          activeVariant={data.cv_active || 'default'}
          defaultContent={data.cv_default || ''}
          customContent={customCv}
          hasCustom={!!data.cv_custom}
          onActivate={(v) => apiPut({ cv_active: v })}
          onUpload={makeUploadHandler('cv')}
          onCustomChange={setCustomCv}
          onSave={() => apiPut({ cv_custom: customCv, cv_active: 'custom' })}
          saving={saving}
        />
        <TemplateCard
          kind="letter" label="Lettre de motivation" icon=""
          activeVariant={data.letter_active || 'default'}
          defaultContent={data.letter_default || ''}
          customContent={customLetter}
          hasCustom={!!data.letter_custom}
          onActivate={(v) => apiPut({ letter_active: v })}
          onUpload={makeUploadHandler('letter')}
          onCustomChange={setCustomLetter}
          onSave={() => apiPut({ letter_custom: customLetter, letter_active: 'custom' })}
          saving={saving}
        />
      </div>
    </div>
  )
}

function KanbanBoard({ applications, onStatusChange, onNotesChange }) {
  const [kanbanSearch, setKanbanSearch] = useState('')
  if (!applications.length) return <div style={{ textAlign: 'center', padding: '80px 0', color: 'var(--text-muted)', fontSize: 14 }}>Aucune candidature.</div>
  const q = kanbanSearch.trim().toLowerCase()
  const idMatch = q.match(/^#?(\d+)$/)
  const filtered = q
    ? applications.filter(a => idMatch ? a.id === Number(idMatch[1]) : (a.company?.toLowerCase().includes(q) || a.role?.toLowerCase().includes(q) || a.notes?.toLowerCase().includes(q)))
    : applications
  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <input type="text" placeholder="Rechercher par #ID, entreprise…" value={kanbanSearch} onChange={e => setKanbanSearch(e.target.value)} style={{ width: '100%', maxWidth: 380, background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: '8px 14px', fontSize: 13, color: 'var(--text-primary)', outline: 'none' }} />
      </div>
      <div style={{ display: 'flex', gap: 14, overflowX: 'auto', paddingBottom: 24, alignItems: 'flex-start' }}>
        {KANBAN_COLS.map(col => {
          const cfg = STATUS_CONFIG[col]
          const cards = filtered.filter(a => (a.status || 'to_apply') === col)
          return (
            <div key={col} style={{ minWidth: 250, flex: '0 0 250px', display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', background: 'var(--bg-surface)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: cfg.color }} />
                  <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>{cfg.label}</span>
                </div>
                <span style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 500 }}>{cards.length}</span>
              </div>
              {cards.map(app => <KanbanCard key={app.id} app={app} onStatusChange={onStatusChange} onNotesChange={onNotesChange} />)}
              {cards.length === 0 && (
                <div style={{ height: 60, border: '1px dashed var(--border)', borderRadius: 'var(--radius-md)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <span style={{ color: 'var(--text-faint)', fontSize: 11 }}>—</span>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─── Offer Card ──────────────────────────────────────────────────────────────

const _GENERIC_COMPANIES = /^(confidentiel|entreprise|cabinet|esn|ssii|consulting|groupe|societe|client|recrutement|non\s*communiqu)/i

function OfferCard({ offer, scanDate, generated, onGenerate, applied, isLiked, onToggleLike, onOpenPreview }) {
  const [open, setOpen] = useState(false)
  const metier   = detectMetier(offer)
  const postDate = getPostingDate(scanDate, offer.days_ago)
  const isNew    = offer.days_ago === 0
  const exp      = expLabel(offer.experience_min)
  const desc     = offer.description || ''
  const hasGen   = generated && generated !== 'loading'
  const isAnon   = !offer.company || offer.company.length < 3 || _GENERIC_COMPANIES.test(offer.company)

  const handleCardClick = () => {
    if (hasGen && onOpenPreview) onOpenPreview(offer, generated)
  }

  return (
    <article onClick={handleCardClick} style={{
      background: 'var(--bg-raised)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius-lg)', display: 'flex', flexDirection: 'column',
      overflow: 'hidden', transition: 'border-color 0.25s ease, box-shadow 0.25s ease, transform 0.25s ease',
      cursor: hasGen ? 'pointer' : 'default',
    }} onMouseEnter={e => { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.10)'; e.currentTarget.style.boxShadow = '0 4px 24px rgba(0,0,0,0.35), 0 0 0 1px rgba(255,255,255,0.04)'; e.currentTarget.style.transform = 'translateY(-1px)' }} onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.boxShadow = 'none'; e.currentTarget.style.transform = 'translateY(0)' }}>
      <div style={{ padding: '22px 24px 18px', display: 'flex', flexDirection: 'column', gap: 14, flex: 1 }}>

        {/* Header: title + like + score */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ color: 'var(--text-primary)', fontWeight: 600, fontSize: 15, lineHeight: 1.45, letterSpacing: '-0.01em' }}>
              {offer.title}
            </div>
            <div style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 5, display: 'flex', alignItems: 'center', gap: 6 }}>
              {offer.company || 'Entreprise'}
              {isAnon && <span style={{ fontSize: 9, padding: '2px 6px', borderRadius: 4, background: 'var(--yellow-dim)', color: 'var(--yellow)', fontWeight: 600, letterSpacing: '0.02em' }}>Non communique</span>}
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
            <button onClick={(e) => { e.stopPropagation(); onToggleLike?.(offer.url) }} style={{
              background: 'none', border: 'none', cursor: 'pointer', padding: 2, display: 'flex', transition: 'transform 0.15s',
            }} onMouseEnter={e => e.currentTarget.style.transform = 'scale(1.2)'} onMouseLeave={e => e.currentTarget.style.transform = 'scale(1)'}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill={isLiked ? 'var(--red)' : 'none'} stroke={isLiked ? 'var(--red)' : 'var(--text-muted)'} strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" /></svg>
            </button>
            {(() => {
              const rec = REC_CONFIG[offer.recommendation] || { label: offer.score, color: 'var(--text-secondary)', bg: 'var(--bg-base)' }
              return <div style={{ background: rec.bg, border: `1px solid ${rec.color}`, borderRadius: 20, padding: '2px 10px', textAlign: 'center' }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: rec.color, lineHeight: 1.3, whiteSpace: 'nowrap' }}>{rec.label}</div>
              </div>
            })()}
          </div>
        </div>

        {/* Meta row */}
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 4, fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.3 }}>
          {offer.contract && <><span style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>{offer.contract}</span><span style={{ opacity: 0.3 }}>/</span></>}
          <span>{offer.location}</span>
          {offer.remote && REMOTE_LABELS[offer.remote] && <><span style={{ opacity: 0.3 }}>/</span><span>{REMOTE_LABELS[offer.remote]}</span></>}
          {exp && <><span style={{ opacity: 0.3 }}>/</span><span style={{
            fontWeight: 600,
            color: offer.experience_min === 0 ? 'var(--green)' : offer.experience_min <= 2 ? 'var(--text-secondary)' : 'var(--yellow)',
          }}>{exp}</span></>}
          <span style={{ marginLeft: 'auto', fontSize: 11, color: isNew ? 'var(--accent)' : 'var(--text-muted)' }}>
            {isNew ? "Aujourd'hui" : <>{formatDate(postDate)} · {daysLabel(offer.days_ago)}</>}
          </span>
        </div>

        {/* Salary */}
        {offer.salary && <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)', letterSpacing: '0.01em' }}>{offer.salary}</div>}

        {/* Tags */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, alignItems: 'center' }}>
          <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 20, background: 'rgba(255,255,255,0.04)', color: 'var(--text-muted)' }}>{SOURCE_LABELS[offer.source] || offer.source}</span>
          <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 20, background: 'rgba(255,255,255,0.04)', color: 'var(--text-muted)' }}>{metier.label}</span>
          {hasGen && <span style={{ fontSize: 9, padding: '2px 8px', borderRadius: 20, background: 'var(--accent-glow)', color: 'var(--accent)', fontWeight: 600, letterSpacing: '0.03em' }}>CV PRET</span>}
          {!hasGen && isNew && <span style={{ fontSize: 9, padding: '2px 8px', borderRadius: 20, background: 'rgba(255,255,255,0.04)', color: 'var(--text-secondary)', fontWeight: 600 }}>NEW</span>}
        </div>

        {/* Skills + Reasoning */}
        {offer.matched_skills?.length > 0 && (
          <div style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.5 }}>
            {offer.matched_skills.slice(0, 6).join(' · ')}
          </div>
        )}
        {offer.reasoning && (
          <div style={{ fontSize: 10, lineHeight: 1.4 }}>
            {(offer.reasoning.whyApply || []).map((r, i) => (
              <span key={i} style={{ color: 'var(--green)', marginRight: 8 }}>+ {r}</span>
            ))}
            {(offer.reasoning.whyNotApply || []).slice(0, 1).map((r, i) => (
              <span key={i} style={{ color: 'var(--text-muted)' }}>- {r}</span>
            ))}
          </div>
        )}

        {/* Description */}
        {desc && (
          <p style={{ color: 'var(--text-muted)', fontSize: 12, lineHeight: 1.6, margin: 0, flex: 1 }}>
            {open ? desc : desc.slice(0, 140)}
            {desc.length > 140 && (
              <button onClick={(e) => { e.stopPropagation(); setOpen(!open) }} style={{ color: 'var(--text-secondary)', background: 'none', border: 'none', cursor: 'pointer', fontSize: 11, padding: 0, marginLeft: 4, fontWeight: 500 }}>
                {open ? 'moins' : '...plus'}
              </button>
            )}
          </p>
        )}
      </div>

      {/* Footer */}
      <div style={{ borderTop: '1px solid var(--border)', padding: '12px 24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          {hasGen ? (
            <>
              <DownloadBtn url={generated.cv_url} label="CV" />
              <DownloadBtn url={generated.letter_url} label="Lettre" />
              <button onClick={(e) => { e.stopPropagation(); if (onOpenPreview) onOpenPreview(offer, generated) }} style={{
                background: 'var(--bg-active)', color: 'var(--text-secondary)',
                fontSize: 12, fontWeight: 600, padding: '7px 14px', borderRadius: 'var(--radius-sm)',
                border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5,
                transition: 'background 0.15s, color 0.15s',
              }}
              onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-hover)'; e.currentTarget.style.color = 'var(--text-primary)' }}
              onMouseLeave={e => { e.currentTarget.style.background = 'var(--bg-active)'; e.currentTarget.style.color = 'var(--text-secondary)' }}>
                <svg width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                Editer
              </button>
            </>
          ) : (
            <button onClick={(e) => { e.stopPropagation(); onGenerate(offer) }} disabled={generated === 'loading'} style={{
              background: generated === 'loading' ? 'var(--bg-active)' : 'var(--accent)',
              color: generated === 'loading' ? 'var(--text-muted)' : '#fff',
              fontSize: 12, fontWeight: 700, padding: '8px 18px', borderRadius: 'var(--radius-sm)',
              border: 'none', cursor: generated === 'loading' ? 'wait' : 'pointer',
              display: 'flex', alignItems: 'center', gap: 6,
              boxShadow: generated === 'loading' ? 'none' : '0 0 12px rgba(224, 119, 51, 0.2)',
              transition: 'box-shadow 0.2s, background 0.2s',
            }}>
              {generated === 'loading'
                ? <><span style={{ width: 10, height: 10, border: '2px solid var(--text-muted)', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 0.7s linear infinite', display: 'inline-block' }} />En cours...</>
                : 'Generer'
              }
            </button>
          )}
        </div>
        <a href={offer.url} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()} style={{
          color: 'var(--text-secondary)', fontSize: 11, fontWeight: 500, textDecoration: 'none',
          background: 'transparent', padding: '6px 12px', borderRadius: 'var(--radius-sm)',
          border: '1px solid var(--border)',
          display: 'flex', alignItems: 'center', gap: 5, transition: 'border-color 0.15s, color 0.15s',
        }} onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--border-light)'; e.currentTarget.style.color = 'var(--text-primary)' }} onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--text-secondary)' }}>
          Voir l'offre <span style={{ fontSize: 10 }}>↗</span>
        </a>
      </div>
    </article>
  )
}

// ─── Offer Row ───────────────────────────────────────────────────────────────

function OfferRow({ offer, scanDate, applied }) {
  const metier   = detectMetier(offer)
  const postDate = getPostingDate(scanDate, offer.days_ago)
  const isNew    = offer.days_ago === 0

  return (
    <a href={offer.url} target="_blank" rel="noopener noreferrer" style={{
      display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px',
      borderBottom: '1px solid var(--border)', textDecoration: 'none',
      transition: 'background 0.1s',
    }} onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-hover)'} onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
      <div style={{ color: scoreColor(offer.score), fontSize: 13, fontWeight: 700, flexShrink: 0, width: 30, textAlign: 'center' }}>{offer.score}</div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ color: 'var(--text-primary)', fontSize: 13, fontWeight: 500, display: 'flex', alignItems: 'center', gap: 6, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {applied && <span style={{ background: 'var(--green-dim)', color: 'var(--green)', fontSize: 9, fontWeight: 600, padding: '1px 5px', borderRadius: 3, flexShrink: 0 }}>Généré</span>}
          {!applied && isNew && <span style={{ background: 'var(--accent-glow)', color: 'var(--accent)', fontSize: 9, fontWeight: 600, padding: '1px 5px', borderRadius: 3, flexShrink: 0 }}>New</span>}
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{offer.title}</span>
        </div>
        <div style={{ color: 'var(--text-muted)', fontSize: 11, marginTop: 2 }}>{offer.company}</div>
      </div>
      <span style={{ color: 'var(--text-muted)', fontSize: 11, flexShrink: 0, display: 'none' }} className="hidden md:inline">{metier.label}</span>
      <span style={{ color: 'var(--text-muted)', fontSize: 11, flexShrink: 0, width: 100, textAlign: 'right', display: 'none' }} className="hidden sm:inline">{offer.location}</span>
      {offer.contract && <Tag style={offer.contract === 'CDI' ? { color: 'var(--accent)', background: 'var(--accent-glow)', display: 'none' } : { display: 'none' }} className="hidden sm:inline-flex">{offer.contract}</Tag>}
      <span style={{ color: 'var(--text-muted)', fontSize: 11, flexShrink: 0, width: 80, textAlign: 'right', display: 'none' }} className="hidden sm:inline">{SOURCE_LABELS[offer.source] || offer.source}</span>
      <div style={{ flexShrink: 0, textAlign: 'right', minWidth: 56 }}>
        <div style={{ fontSize: 11, fontWeight: 500, color: isNew ? 'var(--accent)' : 'var(--text-muted)' }}>{daysLabel(offer.days_ago)}</div>
      </div>
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" style={{ color: 'var(--text-faint)', flexShrink: 0 }}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
    </a>
  )
}

// ─── Onboarding ─────────────────────────────────────────────────────────────

const DOMAIN_PRESETS = {
  'Frontend':      { skills_core: ['React', 'TypeScript', 'JavaScript', 'CSS', 'HTML'], skills_secondary: ['Vue.js', 'Angular', 'Tailwind', 'Next.js', 'GraphQL'], titles: ['Developpeur Frontend', 'Developpeur React', 'Integrateur Web'] },
  'Backend':       { skills_core: ['Java', 'Spring Boot', 'Python', 'SQL', 'API REST'], skills_secondary: ['Node.js', 'PostgreSQL', 'MongoDB', 'Docker', 'Microservices'], titles: ['Developpeur Backend', 'Developpeur Java', 'Ingenieur Backend'] },
  'Fullstack':     { skills_core: ['React', 'Node.js', 'TypeScript', 'Python', 'SQL'], skills_secondary: ['Java', 'Spring Boot', 'Docker', 'GraphQL', 'MongoDB'], titles: ['Developpeur Fullstack', 'Developpeur Full Stack', 'Software Engineer'] },
  'DevOps / Cloud':{ skills_core: ['Docker', 'Kubernetes', 'CI/CD', 'Terraform', 'AWS'], skills_secondary: ['Ansible', 'Linux', 'Prometheus', 'GitLab', 'Azure'], titles: ['Ingenieur DevOps', 'SRE', 'Ingenieur Cloud'] },
  'Data / IA':     { skills_core: ['Python', 'SQL', 'Machine Learning', 'Pandas', 'TensorFlow'], skills_secondary: ['Spark', 'Airflow', 'Docker', 'NLP', 'LLM'], titles: ['Data Scientist', 'Data Engineer', 'Ingenieur IA'] },
  'Mobile':        { skills_core: ['React Native', 'Swift', 'Kotlin', 'Flutter', 'TypeScript'], skills_secondary: ['Firebase', 'REST API', 'CI/CD', 'Git'], titles: ['Developpeur Mobile', 'Developpeur iOS', 'Developpeur Android'] },
  'Consulting / SI': { skills_core: ['Agile', 'Scrum', 'JIRA', 'Architecture SI', 'UML'], skills_secondary: ['SAP', 'ERP', 'ITIL', 'PMO', 'Transformation digitale'], titles: ['Consultant IT', 'Consultant SI', 'Chef de projet IT'] },
  'Design / UX':   { skills_core: ['Figma', 'UI/UX', 'Adobe XD', 'Prototypage', 'Design System'], skills_secondary: ['HTML', 'CSS', 'Illustration', 'Motion Design'], titles: ['UX Designer', 'UI Designer', 'Product Designer'] },
  'Marketing':     { skills_core: ['SEO', 'Google Analytics', 'Social Media', 'Content Marketing', 'CRM'], skills_secondary: ['Google Ads', 'Emailing', 'Hubspot', 'Copywriting'], titles: ['Chef de projet Marketing', 'Growth Manager', 'Community Manager'] },
  'Finance':       { skills_core: ['Excel', 'Analyse financiere', 'Comptabilite', 'Power BI', 'SAP'], skills_secondary: ['VBA', 'Bloomberg', 'Audit', 'Controle de gestion'], titles: ['Analyste Financier', 'Controleur de gestion', 'Auditeur'] },
}

function OnboardingScreen({ user, signOut, onComplete }) {
  const [step, setStep] = useState('intent') // 'intent' | 'profile'
  const [intent, setIntent] = useState(null) // 'generate' | 'search'
  const [saving, setSaving] = useState(false)
  const [parsing, setParsing] = useState(false)
  const [error, setError] = useState(null)
  const [selectedDomain, setSelectedDomain] = useState(null)
  const [cvMode, setCvMode] = useState('upload')
  const [cvText, setCvText] = useState('')
  const [cvFile, setCvFile] = useState(null)
  const [cvParsed, setCvParsed] = useState(null)
  const [profileName, setProfileName] = useState('')
  const [prefs, setPrefs] = useState({
    current_title: '', cities: ['Paris'], contracts: ['CDI'], experience_max: 3,
    skills_core: [], skills_secondary: [], skills_exclude: [], titles_target: [],
    keywords_exclude: [], seniority_block: true,
    sources: ['wttj', 'francetravail', 'linkedin', 'indeed', 'adzuna', 'apec', 'pmejob', 'csp'],
  })
  const [inputValues, setInputValues] = useState({ skills_core: '', skills_exclude: '', titles_target: '' })

  const firstName = user?.user_metadata?.full_name?.split(' ')[0] || ''

  // Parse CV (PDF or text)
  const parseCv = async (body, isFile = false) => {
    setParsing(true); setError(null)
    try {
      const r = isFile
        ? await apiFetch('/api/parse-cv', { method: 'POST', body, headers: {} })
        : await apiFetch('/api/parse-cv', { method: 'POST', body: JSON.stringify({ text: body }) })
      const d = await r.json()
      if (d.ok && d.truth) {
        setCvParsed(d.truth)
        setProfileName(d.truth.profile?.name || profileName || 'Mon profil')
        // Auto-fill prefs from CV skills
        try {
          const sr = await apiFetch('/api/profile/extract-skills', { method: 'POST', body: JSON.stringify(d.truth) })
          const sd = await sr.json()
          if (sd.skills?.length) setPrefs(p => ({ ...p, skills_core: [...new Set([...p.skills_core, ...sd.skills.slice(0, 10)])] }))
          if (sd.titles?.length) setPrefs(p => ({ ...p, titles_target: [...new Set([...p.titles_target, ...sd.titles.slice(0, 5)])] }))
        } catch {}
      } else { setError(d.error || 'Erreur analyse CV') }
    } catch (e) { setError(e.message) }
    finally { setParsing(false) }
  }

  const handleCvFile = (e) => {
    const file = e.target?.files?.[0]
    if (!file) return
    setCvFile(file)
    const formData = new FormData()
    formData.append('file', file)
    parseCv(formData, true)
    if (e.target) e.target.value = ''
  }

  const selectDomain = (name) => {
    const preset = DOMAIN_PRESETS[name]
    if (!preset) return
    if (selectedDomain === name) { setSelectedDomain(null); return }
    setSelectedDomain(name)
    setPrefs(p => ({ ...p, skills_core: [...preset.skills_core], skills_secondary: [...preset.skills_secondary], titles_target: [...preset.titles] }))
  }

  const toggleArray = (key, val) => setPrefs(p => ({ ...p, [key]: (p[key] || []).includes(val) ? p[key].filter(v => v !== val) : [...(p[key] || []), val] }))
  const addToArray = (key) => {
    const val = inputValues[key]?.trim()
    if (val && !(prefs[key] || []).includes(val)) setPrefs(p => ({ ...p, [key]: [...(p[key] || []), val] }))
    setInputValues(v => ({ ...v, [key]: '' }))
  }
  const removeFromArray = (key, val) => setPrefs(p => ({ ...p, [key]: (p[key] || []).filter(v => v !== val) }))

  const finish = async () => {
    if (!prefs.skills_core.length) { setError('Ajoutez au moins une competence principale'); return }
    if (!prefs.cities.length) { setError('Selectionnez au moins une ville'); return }
    setSaving(true); setError(null)
    try {
      // If CV was already parsed, save it
      if (cvParsed) {
        await apiFetch('/api/profile/truth', { method: 'PUT', body: JSON.stringify(cvParsed) })
        const name = profileName.trim() || cvParsed.profile?.name || 'Mon profil'
        await apiFetch('/api/profiles', { method: 'POST', body: JSON.stringify({ profile_name: name, truth: cvParsed }) })
      } else if (cvFile || cvText.trim()) {
        // CV provided but not parsed yet — save minimal truth, parse in background
        const minTruth = { profile: { name: user?.user_metadata?.full_name || '', email: user?.email || '' }, experiences: [], education: [], skills: {} }
        await apiFetch('/api/profile/truth', { method: 'PUT', body: JSON.stringify(minTruth) })
        // Parse CV in background (don't block)
        const formData = cvFile ? (() => { const fd = new FormData(); fd.append('file', cvFile); return fd })() : null
        const parseBody = formData || JSON.stringify({ text: cvText.trim() })
        const parseHeaders = formData ? {} : undefined
        apiFetch('/api/parse-cv', { method: 'POST', body: parseBody, ...(parseHeaders ? { headers: parseHeaders } : {}) })
          .then(r => r.json())
          .then(async d => {
            if (d.ok && d.truth) {
              await apiFetch('/api/profile/truth', { method: 'PUT', body: JSON.stringify(d.truth) })
              const name = profileName.trim() || d.truth.profile?.name || 'Mon profil'
              await apiFetch('/api/profiles', { method: 'POST', body: JSON.stringify({ profile_name: name, truth: d.truth }) })
            }
          }).catch(() => {})
      } else {
        // No CV at all — save minimal
        const minTruth = { profile: { name: user?.user_metadata?.full_name || '', email: user?.email || '' }, experiences: [], education: [], skills: {} }
        await apiFetch('/api/profile/truth', { method: 'PUT', body: JSON.stringify(minTruth) })
      }
      // Save preferences
      await apiFetch('/api/profile/preferences', { method: 'PUT', body: JSON.stringify(prefs) })
      onComplete()
    } catch (e) { setError(e.message); setSaving(false) }
  }

  const chip = (label, active, onClick, size = 'md') => (
    <button key={label} onClick={onClick} style={{
      padding: size === 'sm' ? '4px 10px' : '7px 16px', borderRadius: 20, fontSize: size === 'sm' ? 11 : 13, fontWeight: 600, cursor: 'pointer', transition: 'all 0.15s',
      background: active ? 'var(--bg-active)' : 'transparent', color: active ? 'var(--text-primary)' : 'var(--text-muted)',
      border: active ? '1px solid var(--text-muted)' : '1px solid var(--border)',
    }}>{label}</button>
  )

  const tagList = (key, placeholder, color = 'var(--text-primary)') => (
    <>
      <div style={{ display: 'flex', gap: 6, marginBottom: 6 }}>
        <input value={inputValues[key] || ''} onChange={e => setInputValues(v => ({ ...v, [key]: e.target.value }))}
          onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addToArray(key))}
          placeholder={placeholder}
          style={{ flex: 1, padding: '7px 12px', background: 'var(--bg-base)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-primary)', fontSize: 12, outline: 'none' }} />
        <button onClick={() => addToArray(key)} style={{ padding: '7px 12px', background: 'var(--bg-base)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-secondary)', fontSize: 12, fontWeight: 700, cursor: 'pointer' }}>+</button>
      </div>
      {(prefs[key] || []).length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {(prefs[key] || []).map(k => (
            <span key={k} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '3px 10px', background: 'var(--bg-active)', color, borderRadius: 12, fontSize: 11, fontWeight: 500, border: '1px solid var(--border)' }}>
              {k}
              <button onClick={() => removeFromArray(key, k)} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 13, padding: 0, lineHeight: 1 }}>x</button>
            </span>
          ))}
        </div>
      )}
    </>
  )

  const suggestions = selectedDomain && DOMAIN_PRESETS[selectedDomain]
    ? [...DOMAIN_PRESETS[selectedDomain].skills_core, ...DOMAIN_PRESETS[selectedDomain].skills_secondary].filter(s => !(prefs.skills_core || []).includes(s) && !(prefs.skills_secondary || []).includes(s))
    : []

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'flex-start', justifyContent: 'center', background: 'var(--bg-base)', padding: '40px 24px' }}>
      <div style={{ width: '100%', maxWidth: 620, animation: 'fadeUp 0.3s ease' }}>

        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 32 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ width: 34, height: 34, borderRadius: 'var(--radius-sm)', background: 'var(--accent)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 15, fontWeight: 800, color: '#fff' }}>M</div>
            <span style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>Mass Apply</span>
          </div>
          <button onClick={signOut} style={{ background: 'none', border: '1px solid var(--border)', color: 'var(--text-muted)', borderRadius: 'var(--radius-sm)', padding: '5px 12px', fontSize: 11, cursor: 'pointer' }}>Deconnexion</button>
        </div>

        {/* Step: Intent Selection */}
        {step === 'intent' && (
          <div style={{ textAlign: 'center', paddingTop: 40 }}>
            <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--text-primary)', letterSpacing: '-0.03em', marginBottom: 8 }}>
              {firstName ? `Bienvenue ${firstName}` : 'Bienvenue'}
            </div>
            <div style={{ fontSize: 14, color: 'var(--text-muted)', marginBottom: 36 }}>Que souhaitez-vous faire aujourd'hui ?</div>
            <div style={{ display: 'flex', gap: 16, justifyContent: 'center' }}>
              <button onClick={() => { setIntent('generate'); setStep('profile') }} style={{
                width: 240, padding: '28px 20px', background: 'var(--bg-raised)', border: '1px solid var(--border)',
                borderRadius: 'var(--radius-lg)', cursor: 'pointer', textAlign: 'center', transition: 'all 0.2s',
              }} onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent)'} onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}>
                <div style={{ fontSize: 28, marginBottom: 10 }}>
                  <svg width="32" height="32" fill="none" viewBox="0 0 24 24" stroke="var(--accent)" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                </div>
                <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>Generer un CV</div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 6 }}>Importez votre CV et generez des candidatures adaptees</div>
              </button>
              <button onClick={() => { setIntent('search'); setStep('profile') }} style={{
                width: 240, padding: '28px 20px', background: 'var(--bg-raised)', border: '1px solid var(--border)',
                borderRadius: 'var(--radius-lg)', cursor: 'pointer', textAlign: 'center', transition: 'all 0.2s',
              }} onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent)'} onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}>
                <div style={{ fontSize: 28, marginBottom: 10 }}>
                  <svg width="32" height="32" fill="none" viewBox="0 0 24 24" stroke="var(--accent)" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                </div>
                <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>Trouver des offres</div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 6 }}>Scannez 8 plateformes et trouvez des offres pertinentes</div>
              </button>
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 24 }}>Les deux options necessitent un profil. Vous pourrez tout faire ensuite.</div>
          </div>
        )}

        {/* Step: Profile Creation */}
        {step === 'profile' && (<>

        {/* Welcome */}
        <div style={{ marginBottom: 28 }}>
          <div style={{ fontSize: 26, fontWeight: 800, color: 'var(--text-primary)', letterSpacing: '-0.03em' }}>
            {intent === 'generate' ? 'Creez votre profil' : firstName ? `Salut ${firstName} !` : 'Configurez votre profil'}
          </div>
          <div style={{ fontSize: 14, color: 'var(--text-muted)', marginTop: 6 }}>
            {intent === 'generate' ? 'Importez votre CV pour commencer a generer des candidatures.' : 'Repondez en 30 secondes et decouvrez des offres filtrees pour vous.'}
          </div>
        </div>

        {/* Card */}
        <div style={{ background: 'var(--bg-raised)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '28px 32px', display: 'flex', flexDirection: 'column', gap: 24 }}>

          {/* CV Upload */}
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>Votre CV</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 10 }}>Importez votre CV pour extraire vos experiences et generer des candidatures adaptees.</div>

            {/* Profile name */}
            <input value={profileName} onChange={e => setProfileName(e.target.value)}
              placeholder="Nom du profil (ex: Dev Fullstack, Consultant SAP...)"
              style={{ width: '100%', padding: '8px 12px', background: 'var(--bg-base)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-primary)', fontSize: 12, outline: 'none', marginBottom: 10 }} />

            {parsing ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '20px 0' }}>
                <div style={{ width: 20, height: 20, border: '2px solid var(--accent-dim)', borderTopColor: 'var(--accent)', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
                <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Analyse du CV en cours...</span>
              </div>
            ) : cvParsed ? (
              <div style={{ padding: '12px 14px', background: 'var(--bg-base)', border: '1px solid var(--green)', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                  <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="var(--green)" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>
                  <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{cvParsed.profile?.name || 'CV analyse'}</span>
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  {cvParsed.experiences?.length || 0} experiences · {cvParsed.education?.length || 0} formations · {cvParsed.certifications?.length || 0} certifications
                </div>
                <button onClick={() => { setCvParsed(null); setCvFile(null); setCvText('') }} style={{ marginTop: 6, fontSize: 11, color: 'var(--text-muted)', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}>Changer de CV</button>
              </div>
            ) : (
              <>
                <div style={{ display: 'flex', background: 'var(--bg-base)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)', padding: 2, gap: 2, marginBottom: 10 }}>
                  {[{ v: 'upload', l: 'Fichier PDF' }, { v: 'paste', l: 'Coller le texte' }].map(m => (
                    <button key={m.v} onClick={() => setCvMode(m.v)} style={{ flex: 1, background: cvMode === m.v ? 'var(--bg-active)' : 'transparent', color: cvMode === m.v ? 'var(--text-primary)' : 'var(--text-muted)', border: 'none', borderRadius: 6, padding: '6px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600 }}>{m.l}</button>
                  ))}
                </div>
                {cvMode === 'upload' ? (
                  <label style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, padding: '24px 16px', border: '2px dashed var(--border-light)', borderRadius: 'var(--radius-sm)', cursor: 'pointer', background: 'var(--bg-base)' }}>
                    <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="var(--text-muted)" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" /></svg>
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Glissez votre CV ou cliquez</div>
                    <input type="file" accept=".pdf,.doc,.docx,.txt" onChange={handleCvFile} style={{ display: 'none' }} />
                  </label>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <textarea value={cvText} onChange={e => setCvText(e.target.value)}
                      placeholder="Collez votre CV ici..."
                      style={{ width: '100%', minHeight: 120, padding: '10px 12px', background: 'var(--bg-base)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-primary)', fontSize: 11, lineHeight: 1.5, resize: 'vertical', outline: 'none', fontFamily: 'inherit' }} />
                    <button onClick={() => cvText.trim() && parseCv(cvText.trim())} disabled={!cvText.trim()} style={{
                      alignSelf: 'flex-end', padding: '6px 16px', background: cvText.trim() ? 'var(--accent)' : 'var(--bg-active)', color: cvText.trim() ? '#fff' : 'var(--text-muted)', border: 'none', borderRadius: 'var(--radius-sm)', fontSize: 12, fontWeight: 600, cursor: cvText.trim() ? 'pointer' : 'not-allowed',
                    }}>Analyser</button>
                  </div>
                )}
              </>
            )}
          </div>

          {/* 0. Current title */}
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>Votre titre actuel</div>
            <input value={prefs.current_title || ''} onChange={e => setPrefs(p => ({ ...p, current_title: e.target.value }))}
              placeholder="ex: Etudiant en informatique, Developpeur Java, Chef de projet..."
              style={{ width: '100%', padding: '10px 14px', background: 'var(--bg-base)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-primary)', fontSize: 13, outline: 'none' }} />
          </div>

          {/* 1. Contract type */}
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 10 }}>Que recherchez-vous ?</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {['CDI', 'CDD', 'Alternance', 'Stage', 'Freelance'].map(c =>
                chip(c, (prefs.contracts || []).includes(c), () => toggleArray('contracts', c))
              )}
            </div>
          </div>

          {/* 2. Domain presets */}
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>Votre domaine</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 10 }}>Selectionnez pour pre-remplir vos competences. Vous pourrez tout modifier ensuite.</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))', gap: 6 }}>
              {Object.keys(DOMAIN_PRESETS).map(name => (
                <button key={name} onClick={() => selectDomain(name)} style={{
                  padding: '10px 12px', borderRadius: 'var(--radius-sm)', fontSize: 12, fontWeight: 600, cursor: 'pointer',
                  transition: 'all 0.15s', textAlign: 'left',
                  background: selectedDomain === name ? 'var(--bg-active)' : 'var(--bg-base)',
                  color: selectedDomain === name ? 'var(--text-primary)' : 'var(--text-muted)',
                  border: selectedDomain === name ? '1px solid var(--accent)' : '1px solid var(--border)',
                }}>{name}</button>
              ))}
            </div>
          </div>

          {/* 3. Skills */}
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>Vos mots-cles</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8 }}>Chaque mot-cle que vous ajoutez affine vos resultats. Plus c'est precis, plus les offres seront pertinentes.</div>
            {tagList('skills_core', 'Ajouter une competence...')}
            {suggestions.length > 0 && (
              <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 4, alignItems: 'center' }}>
                <span style={{ fontSize: 10, color: 'var(--text-muted)', marginRight: 4 }}>Suggestions :</span>
                {suggestions.slice(0, 8).map(s => (
                  <button key={s} onClick={() => setPrefs(p => ({ ...p, skills_core: [...(p.skills_core || []), s] }))} style={{
                    padding: '2px 8px', borderRadius: 10, fontSize: 10, cursor: 'pointer', background: 'transparent',
                    color: 'var(--text-muted)', border: '1px dashed var(--border)', transition: 'all 0.15s',
                  }}>{s}</button>
                ))}
              </div>
            )}
          </div>

          {/* 4. Exclude */}
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>Technologies a eviter <span style={{ fontWeight: 400, color: 'var(--text-muted)', fontSize: 12 }}>(optionnel)</span></div>
            {tagList('skills_exclude', 'ex: PHP, Salesforce, SAP...')}
          </div>

          {/* 5. Job titles */}
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>Titres de poste recherches</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8 }}>Les titres exacts que vous recherchez sur les sites d'emploi. C'est le critere le plus important.</div>
            {tagList('titles_target', 'ex: Developpeur Fullstack, Data Engineer...')}
          </div>

          {/* 6. Experience */}
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>Niveau d'experience</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {[{ v: 0, l: 'Etudiant' }, { v: 1, l: '0-1 an' }, { v: 3, l: '1-3 ans' }, { v: 5, l: '3-5 ans' }, { v: 8, l: '5-8 ans' }, { v: 10, l: '8-10 ans' }, { v: 15, l: '10+ ans' }].map(c =>
                chip(c.l, prefs.experience_max === c.v, () => {
                  setPrefs(p => ({ ...p, experience_max: c.v, seniority_block: c.v <= 3 }))
                  if (c.v === 0) setPrefs(p => {
                    const contracts = new Set(p.contracts || []); contracts.add('Alternance'); contracts.add('Stage')
                    return { ...p, contracts: [...contracts], keywords_exclude: (p.keywords_exclude || []).filter(k => k !== 'alternance' && k !== 'stage') }
                  })
                }, 'sm')
              )}
            </div>
          </div>

          {/* 7. Cities */}
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>Ou ?</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {['Paris', 'Lyon', 'Marseille', 'Lille', 'Toulouse', 'Bordeaux', 'Nantes', 'Nice', 'Montpellier', 'Strasbourg', 'Rennes', 'Grenoble', 'Remote'].map(c =>
                chip(c, (prefs.cities || []).includes(c), () => toggleArray('cities', c), 'sm')
              )}
            </div>
          </div>

          {error && (
            <div style={{ padding: '10px 14px', borderRadius: 'var(--radius-sm)', background: 'var(--red-dim)', color: 'var(--red)', fontSize: 12, border: '1px solid var(--red)' }}>
              {error}
            </div>
          )}
        </div>

        {/* CTA */}
        <button onClick={finish} disabled={saving} style={{
          width: '100%', marginTop: 20, padding: '14px 28px', background: 'var(--accent)',
          color: '#fff', border: 'none', borderRadius: 'var(--radius-md)', fontSize: 15, fontWeight: 700,
          cursor: saving ? 'wait' : 'pointer', opacity: saving ? 0.6 : 1, transition: 'opacity 0.2s',
        }}>{saving ? 'Configuration en cours...' : 'Voir les offres'}</button>

        <div style={{ textAlign: 'center', marginTop: 12, fontSize: 11, color: 'var(--text-muted)' }}>
          Votre CV pourra etre importe plus tard pour generer des candidatures
        </div>

        </>)}
      </div>
    </div>
  )
}

// ─── CV Upload Gate ──────────────────────────────────────────────────────────

function CvGateModal({ offer, onComplete, onClose }) {
  const [mode, setMode] = useState('upload') // 'upload' | 'paste'
  const [text, setText] = useState('')
  const [profileName, setProfileName] = useState('')
  const [profileType, setProfileType] = useState('EMPLOYEE')
  const [parsing, setParsing] = useState(false)
  const [error, setError] = useState(null)

  const handleFile = async (e) => {
    const file = e.target?.files?.[0]
    if (!file) return
    setParsing(true); setError(null)
    const formData = new FormData()
    formData.append('file', file)
    try {
      const r = await apiFetch('/api/parse-cv', { method: 'POST', body: formData, headers: {} })
      const d = await r.json()
      if (d.ok && d.truth) {
        // Create named profile
        const name = profileName.trim() || d.truth.profile?.name || 'Mon profil'
        await apiFetch('/api/profiles', { method: 'POST', body: JSON.stringify({ profile_name: name, truth: d.truth }) })
        // Enrich preferences with CV skills
        try {
          const sr = await apiFetch('/api/profile/extract-skills', { method: 'POST', body: JSON.stringify(d.truth) })
          const sd = await sr.json()
          if (sd.skills?.length || sd.titles?.length) {
            const pr = await apiFetch('/api/profile/preferences').then(r => r.json())
            const updated = { ...pr, skills_core: [...new Set([...(pr.skills_core || []), ...(sd.skills || []).slice(0, 10)])], titles_target: [...new Set([...(pr.titles_target || []), ...(sd.titles || []).slice(0, 5)])] }
            await apiFetch('/api/profile/preferences', { method: 'PUT', body: JSON.stringify(updated) })
          }
        } catch {}
        onComplete(offer)
      } else { setError(d.error || 'Erreur lors de l\'analyse') }
    } catch (e) { setError(e.message) }
    finally { setParsing(false) }
    if (e.target) e.target.value = ''
  }

  const handlePaste = async () => {
    if (!text.trim()) return
    setParsing(true); setError(null)
    try {
      const r = await apiFetch('/api/parse-cv', { method: 'POST', body: JSON.stringify({ text: text.trim() }) })
      const d = await r.json()
      if (d.ok && d.truth) {
        const name = profileName.trim() || d.truth.profile?.name || 'Mon profil'
        await apiFetch('/api/profiles', { method: 'POST', body: JSON.stringify({ profile_name: name, truth: d.truth }) })
        try {
          const sr = await apiFetch('/api/profile/extract-skills', { method: 'POST', body: JSON.stringify(d.truth) })
          const sd = await sr.json()
          if (sd.skills?.length || sd.titles?.length) {
            const pr = await apiFetch('/api/profile/preferences').then(r => r.json())
            const updated = { ...pr, skills_core: [...new Set([...(pr.skills_core || []), ...(sd.skills || []).slice(0, 10)])], titles_target: [...new Set([...(pr.titles_target || []), ...(sd.titles || []).slice(0, 5)])] }
            await apiFetch('/api/profile/preferences', { method: 'PUT', body: JSON.stringify(updated) })
          }
        } catch {}
        onComplete(offer)
      } else { setError(d.error || 'Erreur lors de l\'analyse') }
    } catch (e) { setError(e.message) }
    finally { setParsing(false) }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 200, backdropFilter: 'blur(4px)' }}>
      <div style={{ background: 'var(--bg-raised)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', width: '100%', maxWidth: 500, padding: '32px 36px', animation: 'fadeUp 0.3s ease' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
          <div>
            <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)' }}>Importez votre CV</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>Pour generer une candidature, nous avons besoin de votre parcours.</div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 18 }}>x</button>
        </div>

        {/* Profile name + type */}
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>Nom du profil</div>
          <input value={profileName} onChange={e => setProfileName(e.target.value)}
            placeholder="ex: Consultant SAP, Dev Fullstack, Data Engineer..."
            style={{ width: '100%', padding: '9px 12px', background: 'var(--bg-base)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-primary)', fontSize: 12, outline: 'none', marginBottom: 8 }} />
          <div style={{ display: 'flex', gap: 6 }}>
            {[{ v: 'EMPLOYEE', l: 'Employe' }, { v: 'STUDENT', l: 'Etudiant' }, { v: 'FREELANCER', l: 'Freelance' }].map(t => (
              <button key={t.v} onClick={() => setProfileType?.(t.v)} style={{
                padding: '4px 12px', borderRadius: 16, fontSize: 11, fontWeight: 600, cursor: 'pointer',
                background: (profileType || 'EMPLOYEE') === t.v ? 'var(--bg-active)' : 'transparent',
                color: (profileType || 'EMPLOYEE') === t.v ? 'var(--text-primary)' : 'var(--text-muted)',
                border: (profileType || 'EMPLOYEE') === t.v ? '1px solid var(--text-muted)' : '1px solid var(--border)',
              }}>{t.l}</button>
            ))}
          </div>
        </div>

        {parsing ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, padding: '40px 0' }}>
            <div style={{ width: 28, height: 28, border: '3px solid var(--accent-dim)', borderTopColor: 'var(--accent)', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
            <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Analyse de votre CV...</div>
          </div>
        ) : (
          <>
            {/* Mode tabs */}
            <div style={{ display: 'flex', background: 'var(--bg-base)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)', padding: 3, gap: 2, marginBottom: 16 }}>
              {[{ v: 'upload', l: 'Fichier PDF' }, { v: 'paste', l: 'Coller le texte' }].map(m => (
                <button key={m.v} onClick={() => setMode(m.v)} style={{
                  flex: 1, background: mode === m.v ? 'var(--bg-active)' : 'transparent',
                  color: mode === m.v ? 'var(--text-primary)' : 'var(--text-muted)', border: 'none',
                  borderRadius: 6, padding: '7px 12px', cursor: 'pointer', fontSize: 12, fontWeight: 600,
                }}>{m.l}</button>
              ))}
            </div>

            {mode === 'upload' ? (
              <label style={{
                display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10,
                padding: '36px 24px', border: '2px dashed var(--border-light)',
                borderRadius: 'var(--radius-md)', cursor: 'pointer', background: 'var(--bg-base)',
              }}>
                <svg width="24" height="24" fill="none" viewBox="0 0 24 24" stroke="var(--text-muted)" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" /></svg>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)' }}>Glissez votre CV ici</div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>PDF ou fichier texte</div>
                <input type="file" accept=".pdf,.doc,.docx,.txt" onChange={handleFile} style={{ display: 'none' }} />
              </label>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <textarea value={text} onChange={e => setText(e.target.value)}
                  placeholder={"Collez votre CV ici...\n\nPrenom Nom\nPoste actuel\n\nExperience :\n- Entreprise (dates) : description...\n\nFormation :\n- Diplome, Ecole..."}
                  style={{ width: '100%', minHeight: 180, padding: '12px 14px', background: 'var(--bg-base)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-primary)', fontSize: 12, lineHeight: 1.6, resize: 'vertical', outline: 'none', fontFamily: 'inherit' }} />
                <button onClick={handlePaste} disabled={!text.trim()} style={{
                  alignSelf: 'flex-end', padding: '8px 20px',
                  background: text.trim() ? 'var(--accent)' : 'var(--bg-active)',
                  color: text.trim() ? '#fff' : 'var(--text-muted)',
                  border: 'none', borderRadius: 'var(--radius-sm)', fontSize: 13, fontWeight: 600,
                  cursor: text.trim() ? 'pointer' : 'not-allowed',
                }}>Analyser et generer</button>
              </div>
            )}
          </>
        )}

        {error && (
          <div style={{ marginTop: 12, padding: '8px 12px', borderRadius: 'var(--radius-sm)', background: 'var(--red-dim)', color: 'var(--red)', fontSize: 11, border: '1px solid var(--red)' }}>{error}</div>
        )}

        <div style={{ marginTop: 16, padding: '10px 14px', background: 'var(--bg-base)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)', fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.5 }}>
          Votre CV est analyse par l'IA pour extraire vos experiences et competences. Ces informations seront utilisees pour adapter chaque candidature. Vous pourrez modifier vos templates dans l'onglet Templates.
        </div>
      </div>
    </div>
  )
}

// ─── Generation Walkthrough Modal ─────────────────────────────────────────────

const GEN_STEPS = [
  { id: 'analyze',        label: 'Analyse de l\'offre',          icon: '1' },
  { id: 'generate',       label: 'Redaction IA (CV + Lettre)',   icon: '2' },
  { id: 'save',           label: 'Sauvegarde du profil',         icon: '3' },
  { id: 'compile_cv',     label: 'Compilation du CV en PDF',     icon: '4' },
  { id: 'compile_letter', label: 'Compilation de la lettre',     icon: '5' },
  { id: 'track',          label: 'Enregistrement',               icon: '6' },
]

function GenerationModal({ genModal, onCancel, onMinimize }) {
  if (!genModal) return null
  const { offer, steps, abortController } = genModal
  const stepMap = {}
  steps.forEach(s => { stepMap[s.step] = s })
  const doneEvent = stepMap['done']
  const isSuccess = doneEvent?.status === 'success'
  const isError = doneEvent?.status === 'error'
  const isRunning = !doneEvent

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 200, backdropFilter: 'blur(4px)' }}>
      <div style={{ background: 'var(--bg-raised)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', width: '100%', maxWidth: 480, padding: '32px 36px', animation: 'fadeUp 0.3s ease' }}>

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
          <div style={{ width: 40, height: 40, borderRadius: '50%', background: isSuccess ? 'var(--green-dim)' : isError ? 'var(--red-dim)' : 'var(--accent-glow)', border: `1px solid ${isSuccess ? 'var(--green)' : isError ? 'var(--red)' : 'var(--accent)'}`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            {isSuccess
              ? <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="var(--green)" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>
              : isError
              ? <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="var(--red)" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
              : <div style={{ width: 18, height: 18, border: '2px solid var(--accent-dim)', borderTopColor: 'var(--accent)', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />}
          </div>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>
              {isSuccess ? 'Generation terminee !' : isError ? 'Echec de la generation' : 'Generation en cours...'}
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>{offer.company} — {offer.title?.slice(0, 40)}</div>
          </div>
        </div>

        {/* Steps */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 24 }}>
          {GEN_STEPS.map((step, i) => {
            const event = stepMap[step.id]
            const status = event?.status || 'pending'
            const isActive = status === 'running'
            const isDone = status === 'done'
            const color = isDone ? 'var(--green)' : isActive ? 'var(--text-primary)' : 'var(--text-muted)'

            return (
              <div key={step.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px', borderRadius: 'var(--radius-sm)', background: isActive ? 'var(--bg-active)' : 'transparent', transition: 'all 0.3s', border: isActive ? '1px solid var(--border-light)' : '1px solid transparent' }}>
                {/* Status icon */}
                <div style={{ width: 24, height: 24, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, fontSize: 11, fontWeight: 700, background: isDone ? 'var(--green-dim)' : isActive ? 'var(--bg-hover)' : 'var(--bg-base)', color, border: `1px solid ${isDone ? 'var(--green)' : isActive ? 'var(--border-light)' : 'var(--border)'}`, transition: 'all 0.3s' }}>
                  {isDone
                    ? <svg width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="var(--green)" strokeWidth={3}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>
                    : isActive
                    ? <div style={{ width: 10, height: 10, border: '2px solid var(--text-muted)', borderTopColor: 'var(--text-primary)', borderRadius: '50%', animation: 'spin 0.7s linear infinite' }} />
                    : step.icon}
                </div>
                {/* Label */}
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: isActive ? 600 : 400, color, transition: 'all 0.3s' }}>{step.label}</div>
                  {event?.detail && (isDone || isActive) && (
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{event.detail}</div>
                  )}
                </div>
                {/* Keywords badge for generate step */}
                {step.id === 'generate' && event?.data?.keywords && (
                  <div style={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
                    {event.data.keywords.map(k => (
                      <span key={k} style={{ fontSize: 9, padding: '1px 6px', borderRadius: 8, background: 'var(--bg-base)', color: 'var(--text-muted)', border: '1px solid var(--border)' }}>{k}</span>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* Footer */}
        <div style={{ display: 'flex', justifyContent: 'center', gap: 10 }}>
          {isRunning && (
            <>
              <button onClick={() => onMinimize?.()} style={{
                padding: '8px 24px', background: 'var(--bg-active)', border: 'none',
                color: 'var(--text-primary)', borderRadius: 'var(--radius-sm)', fontSize: 13,
                fontWeight: 600, cursor: 'pointer',
              }}>Continuer en arriere-plan</button>
              <button onClick={() => { abortController?.abort(); onCancel() }} style={{
                padding: '8px 24px', background: 'transparent', border: '1px solid var(--border)',
                color: 'var(--text-muted)', borderRadius: 'var(--radius-sm)', fontSize: 13,
                fontWeight: 600, cursor: 'pointer',
              }}>Annuler</button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Select ──────────────────────────────────────────────────────────────────

function Select({ value, onChange, options }) {
  return (
    <select value={value} onChange={e => onChange(e.target.value)} style={{
      background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
      color: 'var(--text-secondary)', fontSize: 13, padding: '8px 30px 8px 12px', cursor: 'pointer', outline: 'none',
      appearance: 'none', backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%2348484a' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E")`,
      backgroundRepeat: 'no-repeat', backgroundPosition: 'right 10px center', transition: 'border-color 0.15s',
    }}>
      {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
    </select>
  )
}

// ─── Main App ─────────────────────────────────────────────────────────────────

export default function App() {
  const { user, signOut } = useAuth()
  const [profile, setProfile]                   = useState(null) // { has_truth }
  const [profileLoading, setProfileLoading]     = useState(true)
  const [data, setData]                         = useState(null)
  const [tab, setTab]                           = useState('offers')
  const [search, setSearch]                     = useState('')
  const [tier, setTier]                         = useState('all')
  const [contract, setContract]                 = useState('all')
  const [source, setSource]                     = useState('all')
  const [metierFilter, setMetierFilter]         = useState('all')
  const [sort, setSort]                         = useState('fresh')
  const [minScore, setMinScore]                 = useState(0)
  const [statsFilter, setStatsFilter]           = useState(null)
  const [view, setView]                         = useState('cards')
  const [generations, setGenerations]           = useState({})
  const [appliedCompanies, setAppliedCompanies] = useState(new Set())
  const [applications, setApplications]         = useState([])
  const [scanning, setScanning]                 = useState(false)
  const [toast, setToast]                       = useState(null)
  const [genLog, setGenLog]                     = useState([])
  const [preview, setPreview]                   = useState(null)
  const likeKey = `liked_offers_${user?.id || 'anon'}`
  const [liked, setLiked]                       = useState(() => { try { return new Set(JSON.parse(localStorage.getItem(likeKey) || '[]')) } catch { return new Set() } })
  const [sidebarOpen, setSidebarOpen]           = useState(false)
  const [isMobile, setIsMobile]                 = useState(typeof window !== 'undefined' && window.innerWidth <= 768)
  const [sidebarProfiles, setSidebarProfiles]   = useState([])
  const [activeProfileId, setActiveProfileId]   = useState(null)
  const [profileDropOpen, setProfileDropOpen]   = useState(false)
  const [shouldAutoScan, setShouldAutoScan]     = useState(false)

  useEffect(() => {
    const handler = () => setIsMobile(window.innerWidth <= 768)
    window.addEventListener('resize', handler)
    return () => window.removeEventListener('resize', handler)
  }, [])

  useEffect(() => {
    if (!profileDropOpen) return
    const close = () => setProfileDropOpen(false)
    setTimeout(() => document.addEventListener('click', close), 0)
    return () => document.removeEventListener('click', close)
  }, [profileDropOpen])

  // Check if user has completed onboarding
  useEffect(() => {
    apiFetch('/api/profile').then(r => r.json()).then(d => {
      setProfile(d)
      setProfileLoading(false)
    }).catch(() => setProfileLoading(false))
  }, [])

  const loadSidebarProfiles = () => {
    apiFetch('/api/profiles').then(r => r.json()).then(d => {
      setSidebarProfiles(d.profiles || [])
      setActiveProfileId(d.active || null)
    }).catch(() => {})
  }

  const loadOffers = (autoScan = false) => { apiFetch('/api/offers').then(r => r.json()).then(d => { setData(d); if (autoScan && d.pending_scan) setShouldAutoScan(true) }).catch(() => setData({ offers: [], scan_date: null, total: 0 })) }
  const loadApplications = () => {
    apiFetch('/api/applications').then(r => r.json()).then(d => {
      const apps = d.applications || []
      setApplications(apps)
      setAppliedCompanies(new Set(apps.map(a => a.company?.toLowerCase())))
      const gen = {}
      apps.forEach(a => { if (a.cv_url && a.letter_url && a.apply_link) gen[a.apply_link] = { cv_url: a.cv_url, letter_url: a.letter_url } })
      setGenerations(g => ({ ...gen, ...g }))
    }).catch(() => {})
  }
  useEffect(() => { loadOffers(true); loadApplications(); loadSidebarProfiles() }, [])
  useEffect(() => { if (shouldAutoScan && !scanning) { setShouldAutoScan(false); handleScan() } }, [shouldAutoScan, scanning])

  // Technicien offers (admin only)
  const loadTechOffers = () => {
    if (!profile?.is_admin) return
    apiFetch('/api/offers/technicien').then(r => r.json()).then(setTechOffers).catch(() => {})
  }
  useEffect(() => { if (profile?.is_admin) loadTechOffers() }, [profile])

  const showToast = (msg, type = 'ok', duration = 6000) => { setToast({ msg, type }); setTimeout(() => setToast(null), duration) }
  const toggleLike = (url) => { setLiked(prev => { const next = new Set(prev); if (next.has(url)) next.delete(url); else next.add(url); localStorage.setItem(likeKey, JSON.stringify([...next])); return next }) }
  const addLog = (msg, type = 'info') => { const time = new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }); setGenLog(l => [...l.slice(-50), { time, msg, type }]) }

  const handleScan = async () => {
    if (scanning) return
    setScanning(true); setToast(null)
    try {
      await apiFetch('/api/scan', { method: 'POST' })
      const poll = setInterval(async () => {
        try {
          const s = await apiFetch('/api/scan/status').then(r => r.json())
          if (!s.running) { clearInterval(poll); setScanning(false); loadOffers(); loadApplications(); if (s.last_result) showToast(s.last_result.message, s.last_result.new > 0 ? 'ok' : 'warn') }
        } catch { clearInterval(poll); setScanning(false) }
      }, 2000)
    } catch { setScanning(false); showToast('Serveur non disponible', 'err') }
  }

  // Generation state for the walkthrough modal
  const [genModal, setGenModal] = useState(null) // { offer, steps: [{step, status, detail, data}], abortController }
  const [page, setPage] = useState(0)
  const PAGE_SIZE = 24
  const [techOffers, setTechOffers] = useState(null)
  const [techScanning, setTechScanning] = useState(false)
  const [cvGate, setCvGate] = useState(null) // { offer } — show CV upload modal before generation
  const [companyGate, setCompanyGate] = useState(null) // { offer } — ask company name for anonymous offers
  const [hasRealCv, setHasRealCv] = useState(profile?.has_real_cv || false)

  // Check if user has a real CV (truth.json with experiences)
  const checkCv = async () => {
    try {
      const r = await apiFetch('/api/profile')
      const d = await r.json()
      // Admin always has CV; for others, check if truth has real experiences
      if (d.is_admin) { setHasRealCv(true); return true }
      const r2 = await apiFetch('/api/profile/truth')
      if (r2.ok) {
        const truth = await r2.json()
        const hasExp = truth?.experiences?.length > 0
        setHasRealCv(hasExp)
        return hasExp
      }
    } catch {}
    return false
  }

  const handleGenerate = async (offer) => {
    // Check if company name is anonymous — ask user first
    const co = offer.company || ''
    if (!offer._prompt && (co.length < 3 || _GENERIC_COMPANIES.test(co)) && !offer._companyOverride) {
      setCompanyGate({ offer })
      return
    }

    // Check if user has uploaded a real CV
    if (!hasRealCv && !profile?.is_admin) {
      const hasCv = await checkCv()
      if (!hasCv) {
        setCvGate({ offer })
        return
      }
    }

    const key = offer.url
    const controller = new AbortController()
    setGenerations(g => ({ ...g, [key]: 'loading' }))
    setGenModal({ offer, steps: [], abortController: controller })
    addLog(`Demarrage : ${offer.company} — ${offer.title}`, 'info')

    try {
      const { data: { session } } = await supabase.auth.getSession()
      const headers = { 'Content-Type': 'application/json' }
      if (session?.access_token) headers['Authorization'] = `Bearer ${session.access_token}`

      const res = await fetch('/api/generate', {
        method: 'POST', headers, body: JSON.stringify(offer), signal: controller.signal,
      })

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let finalData = null

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        const lines = buffer.split('\n')
        buffer = lines.pop() // keep incomplete line

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const event = JSON.parse(line.slice(6))
            setGenModal(m => m ? { ...m, steps: [...m.steps.filter(s => s.step !== event.step), event] } : null)

            if (event.step === 'done') {
              if (event.status === 'success' && event.data) {
                finalData = event.data
                setGenerations(g => ({ ...g, [key]: { cv_url: event.data.cv_url, letter_url: event.data.letter_url } }))
                setAppliedCompanies(s => new Set([...s, offer.company?.toLowerCase()]))
                addLog(`OK ${event.data.analysis?.title_suggestion || ''}`, 'ok')
                loadApplications()
              } else {
                setGenerations(g => { const n = { ...g }; delete n[key]; return n })
                addLog(`Erreur: ${event.detail}`, 'err')
              }
            }
          } catch {}
        }
      }

      // After stream ends, if we got final data show preview
      if (finalData) {
        setTimeout(() => {
          setGenModal(null)
          setPreview({ offer, result: { success: true, ...finalData } })
        }, 1500) // brief pause to show "done" state
      }

    } catch (err) {
      if (err.name === 'AbortError') {
        addLog('Generation annulee', 'info')
        showToast('Generation annulee', 'warn')
      } else {
        addLog(`Erreur: ${err.message}`, 'err')
        showToast('Erreur de connexion', 'err')
      }
      setGenerations(g => { const n = { ...g }; delete n[key]; return n })
      setGenModal(null)
    }
  }

  const [batchProgress, setBatchProgress] = useState(null) // { running, total, done, current, results }

  const handleBatchGenerate = async () => {
    if (batchProgress?.running) return
    const likedOffers = allOffers.filter(o => liked.has(o.url) && !generations[o.url])
    if (!likedOffers.length) { showToast('Tous les likes sont deja generes', 'warn'); return }

    showToast(`Lancement de ${likedOffers.length} generations en arriere-plan...`, 'warn', 5000)
    try {
      const r = await apiFetch('/api/batch-generate', { method: 'POST', body: JSON.stringify({ offers: likedOffers }) })
      const d = await r.json()
      if (d.status === 'started' || d.status === 'already_running') {
        // Start polling
        setBatchProgress({ running: true, total: d.total || likedOffers.length, done: 0, current: null, results: [] })
        const poll = setInterval(async () => {
          try {
            const s = await apiFetch('/api/batch-generate/status').then(r => r.json())
            setBatchProgress(s)
            if (!s.running) {
              clearInterval(poll)
              const ok = (s.results || []).filter(r => r.success).length
              showToast(`${ok}/${s.total} candidatures generees !`, ok > 0 ? 'ok' : 'err')
              loadApplications()
              loadOffers()
            }
          } catch { clearInterval(poll); setBatchProgress(null) }
        }, 3000)
      }
    } catch (e) { showToast(`Erreur: ${e.message}`, 'err') }
  }

  const handleRecompile = async (modifiedInspo, outputDir) => {
    try {
      const res = await apiFetch('/api/recompile', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ inspo: modifiedInspo, output_dir: outputDir }), signal: AbortSignal.timeout(120000) })
      const result = await res.json()
      if (result.success) {
        setPreview(p => p ? { ...p, result: { ...p.result, cv_url: result.cv_url, letter_url: result.letter_url } } : null)
        showToast('Recompilation réussie', 'ok')
        if (preview) setGenerations(g => ({ ...g, [preview.offer.url]: { cv_url: result.cv_url, letter_url: result.letter_url } }))
      } else { showToast(`Erreur : ${result.error}`, 'err') }
    } catch (err) { showToast(`Erreur : ${err.message}`, 'err') }
  }

  const handleStatusUpdate = async (appId, status) => {
    try { await apiFetch(`/api/applications/${appId}/status`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }) }); setApplications(apps => apps.map(a => a.id === appId ? { ...a, status } : a)) }
    catch (err) { showToast(`Erreur : ${err.message}`, 'err') }
  }

  const handleNotesUpdate = async (appId, notes) => {
    try { await apiFetch(`/api/applications/${appId}/notes`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ notes }) }); setApplications(apps => apps.map(a => a.id === appId ? { ...a, notes } : a)) }
    catch (err) { showToast(`Erreur : ${err.message}`, 'err') }
  }

  const allOffers = useMemo(() => {
    if (!data?.offers) return []
    return data.offers.filter(o => { const c = (o.contract || '').toUpperCase(); return c === 'CDI' || c === 'CDD' || c === '' })
  }, [data])

  const filtered = useMemo(() => {
    let offers = allOffers
    if (search.trim()) {
      const q = search.trim().toLowerCase()
      const idMatch = q.match(/^#?(\d+)$/)
      if (idMatch) { offers = offers.filter(o => o.id === Number(idMatch[1])) }
      else { offers = offers.filter(o => o.title?.toLowerCase().includes(q) || o.company?.toLowerCase().includes(q) || o.description?.toLowerCase().includes(q) || o.matched_skills?.some(s => s.toLowerCase().includes(q))) }
    }
    if (statsFilter === 'top')       offers = offers.filter(o => o.score >= 40)
    if (statsFilter === 'today')     offers = offers.filter(o => o.days_ago === 0)
    if (statsFilter === 'generated') offers = offers.filter(o => appliedCompanies.has(o.company?.toLowerCase()))
    if (statsFilter === 'liked')     offers = offers.filter(o => liked.has(o.url))
    if (tier !== 'all') {
      if (['T1', 'T2', 'T3'].includes(tier)) {
        offers = offers.filter(o => o.location_tier === tier)
      } else {
        // Filter by city name
        offers = offers.filter(o => (o.location || '').toLowerCase().includes(tier))
      }
    }
    if (contract !== 'all')     offers = offers.filter(o => o.contract?.toUpperCase() === contract)
    if (source !== 'all')       offers = offers.filter(o => o.source === source)
    if (minScore > 0)           offers = offers.filter(o => o.score >= minScore)
    if (metierFilter === '_profile') {
      // Filter by user's score — top matches only (score >= 80 after semantic scoring)
      offers = offers.filter(o => o.score >= 70)
    } else if (metierFilter !== 'all') {
      offers = offers.filter(o => detectMetier(o).label === metierFilter)
    }

    return [...offers].sort((a, b) => {
      // Always: highest score first, then lowest experience, then freshest
      if (sort === 'fresh') {
        const sa = a.score ?? 0, sb = b.score ?? 0
        if (sa !== sb) return sb - sa
        const ea = a.experience_min ?? 0, eb = b.experience_min ?? 0
        if (ea !== eb) return ea - eb
        return (a.days_ago ?? 99) - (b.days_ago ?? 99)
      }
      if (sort === 'score') {
        const sa = a.score ?? 0, sb = b.score ?? 0
        if (sa !== sb) return sb - sa
        const ea = a.experience_min ?? 0, eb = b.experience_min ?? 0
        if (ea !== eb) return ea - eb
        return (a.days_ago ?? 99) - (b.days_ago ?? 99)
      }
      return (a.title || '').localeCompare(b.title || '')
    })
  }, [allOffers, search, tier, contract, source, sort, minScore, metierFilter, statsFilter, appliedCompanies, liked])

  // Reset page when filters change
  useEffect(() => { setPage(0) }, [search, tier, contract, source, sort, minScore, metierFilter, statsFilter])

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE)
  const paginatedOffers = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  const stats = useMemo(() => ({
    total:     allOffers.length,
    top:       allOffers.filter(o => o.score >= 40).length,
    today:     allOffers.filter(o => o.days_ago === 0).length,
    generated: appliedCompanies.size,
    applied:   applications.filter(a => a.status === 'applied').length,
    interview: applications.filter(a => a.status === 'interview').length,
  }), [allOffers, appliedCompanies, applications])

  const metierCounts = useMemo(() => {
    const counts = {}
    allOffers.forEach(o => { const m = detectMetier(o).label; counts[m] = (counts[m] || 0) + 1 })
    return counts
  }, [allOffers])

  const scanDate = data?.scan_date || null
  const scanDateFmt = scanDate ? new Date(scanDate).toLocaleString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : null

  // Loading state
  if (profileLoading) return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ width: 24, height: 24, border: '2px solid var(--accent)', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 0.7s linear infinite' }} />
    </div>
  )

  // Onboarding: show if user hasn't completed setup (non-admin without truth+prefs)
  if (profile && !profile.onboarding_complete) {
    return <OnboardingScreen user={user} signOut={signOut} onComplete={() => {
      apiFetch('/api/profile').then(r => r.json()).then(d => {
        setProfile(d); loadOffers(); loadApplications(); loadSidebarProfiles()
        setTab('profile') // Redirect to profile page after onboarding
        handleScan() // Auto-scan in background
      })
    }} />
  }

  if (!data) return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ width: 24, height: 24, border: '2px solid var(--accent)', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 0.7s linear infinite' }} />
    </div>
  )

  const STAT_ITEMS = [
    { v: stats.total,     l: 'Offres',      f: null },
    { v: stats.top,       l: 'Top',          f: 'top' },
    { v: stats.today,     l: "Aujourd'hui",  f: 'today' },
    { v: liked.size,      l: 'Likes',        f: 'liked' },
    { v: stats.generated, l: 'Generes',      f: 'generated' },
    { v: stats.applied,   l: 'Postules',     f: 'applied' },
  ]

  const SIDEBAR_W = 220
  const handleTechScan = async () => {
    if (techScanning) return
    setTechScanning(true)
    try {
      await apiFetch('/api/scan/technicien', { method: 'POST' })
      const poll = setInterval(async () => {
        try {
          const s = await apiFetch('/api/scan/status').then(r => r.json())
          if (!s.running) { clearInterval(poll); setTechScanning(false); loadTechOffers(); if (s.last_result) showToast(s.last_result.message, 'ok') }
        } catch { clearInterval(poll); setTechScanning(false) }
      }, 2000)
    } catch { setTechScanning(false) }
  }

  const NAV_ITEMS = [
    { id: 'offers', label: 'Offres', count: stats.total, icon: <svg width="18" height="18" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M21 13.255A23.193 23.193 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" /></svg> },
    ...(profile?.is_admin ? [{ id: 'technicien', label: 'Technicien', count: techOffers?.total || 0, icon: <svg width="18" height="18" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg> }] : []),
    { id: 'kanban', label: 'Candidatures', count: applications.length, icon: <svg width="18" height="18" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" /></svg> },
    { id: 'templates', label: 'Templates', count: null, icon: <svg width="18" height="18" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg> },
    { id: 'profile', label: 'Mon Profil', count: null, icon: <svg width="18" height="18" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg> },
  ]
  const quotaUsed = applications.filter(a => { const d = new Date(a.created_at || 0); const now = new Date(); return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear() }).length
  const quotaMax = 15
  const quotaPct = Math.min(100, Math.round((quotaUsed / quotaMax) * 100))
  const quotaColor = quotaPct >= 85 ? 'var(--accent)' : quotaPct >= 60 ? 'var(--yellow)' : 'var(--green)'

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: 'var(--bg-base)' }}>

      {/* ── Mobile overlay ── */}
      {isMobile && <div className={`sidebar-overlay${sidebarOpen ? ' open' : ''}`} onClick={() => setSidebarOpen(false)} />}

      {/* ── Sidebar ── */}
      <div className={`sidebar${isMobile && sidebarOpen ? ' open' : ''}`}>
        {/* Brand */}
        <div style={{ padding: '20px 18px 16px', borderBottom: '1px solid var(--border)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ width: 30, height: 30, borderRadius: 8, background: 'var(--accent)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14, fontWeight: 800, color: '#fff', flexShrink: 0 }}>M</div>
            <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>Mass Apply</div>
          </div>
        </div>

        {/* Profile selector */}
        {sidebarProfiles.length > 0 && (
          <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--border)', position: 'relative' }}>
            <button onClick={() => setProfileDropOpen(o => !o)} style={{
              width: '100%', display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px',
              background: 'var(--bg-base)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
              cursor: 'pointer', transition: 'border-color 0.15s',
            }}
              onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent)'}
              onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}
            >
              {(() => {
                const active = sidebarProfiles.find(p => p.id === activeProfileId)
                return (
                  <>
                    <div style={{ width: 24, height: 24, borderRadius: '50%', background: 'var(--bg-active)', border: '2px solid var(--accent)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 700, color: 'var(--accent)', flexShrink: 0 }}>
                      {(active?.name || '?')[0].toUpperCase()}
                    </div>
                    <div style={{ flex: 1, minWidth: 0, textAlign: 'left' }}>
                      <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{active?.name || 'Mon profil'}</div>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{active?.type || 'EMPLOYEE'}</div>
                    </div>
                    <svg width="10" height="10" fill="none" viewBox="0 0 24 24" stroke="var(--text-muted)" strokeWidth={2.5} style={{ flexShrink: 0, transform: profileDropOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s' }}><path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" /></svg>
                  </>
                )
              })()}
            </button>
            {profileDropOpen && (
              <div style={{ position: 'absolute', top: '100%', left: 8, right: 8, background: 'var(--bg-raised)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', zIndex: 100, boxShadow: '0 8px 24px rgba(0,0,0,0.4)', overflow: 'hidden', marginTop: 2 }}>
                {sidebarProfiles.map(p => (
                  <button key={p.id} onClick={async () => {
                    if (p.id !== activeProfileId) {
                      await apiFetch(`/api/profiles/${p.id}/activate`, { method: 'POST' })
                      setActiveProfileId(p.id)
                      loadOffers(); loadApplications(); loadSidebarProfiles()
                      handleScan()
                    }
                    setProfileDropOpen(false)
                  }} style={{
                    width: '100%', display: 'flex', alignItems: 'center', gap: 8, padding: '9px 12px',
                    background: p.id === activeProfileId ? 'var(--bg-active)' : 'transparent',
                    border: 'none', cursor: 'pointer', textAlign: 'left', transition: 'background 0.1s',
                  }}
                    onMouseEnter={e => { if (p.id !== activeProfileId) e.currentTarget.style.background = 'var(--bg-surface)' }}
                    onMouseLeave={e => { if (p.id !== activeProfileId) e.currentTarget.style.background = 'transparent' }}
                  >
                    <div style={{ width: 8, height: 8, borderRadius: '50%', background: p.id === activeProfileId ? 'var(--green)' : 'var(--border)', flexShrink: 0 }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 12, fontWeight: 600, color: p.id === activeProfileId ? 'var(--text-primary)' : 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.name}</div>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{p.type} · {p.completeness}%</div>
                    </div>
                    {p.id === activeProfileId && <svg width="10" height="10" fill="none" viewBox="0 0 24 24" stroke="var(--green)" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>}
                  </button>
                ))}
                <div style={{ borderTop: '1px solid var(--border)' }} />
                <button onClick={() => { setProfileDropOpen(false); setTab('profile') }} style={{
                  width: '100%', display: 'flex', alignItems: 'center', gap: 8, padding: '9px 12px',
                  background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', fontSize: 12,
                }}
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-surface)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                >
                  <svg width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" /></svg>
                  Nouveau profil
                </button>
              </div>
            )}
          </div>
        )}

        {/* Nav */}
        <div style={{ flex: 1, padding: '12px 0', overflowY: 'auto' }}>
          {NAV_ITEMS.map(item => (
            <div key={item.id} className={`sidebar-item${tab === item.id ? ' active' : ''}`}
              onClick={() => { setTab(item.id); setStatsFilter(null); if (isMobile) setSidebarOpen(false) }}>
              {item.icon}
              <span style={{ flex: 1 }}>{item.label}</span>
              {item.count !== null && item.count > 0 && (
                <span style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 500, fontVariantNumeric: 'tabular-nums', background: 'rgba(255,255,255,0.04)', padding: '1px 6px', borderRadius: 10 }}>{item.count}</span>
              )}
            </div>
          ))}

          <div style={{ margin: '14px 14px', borderTop: '1px solid var(--border)' }} />

          {/* Scan button */}
          <div style={{ padding: '0 12px' }}>
            <button onClick={handleScan} disabled={scanning} style={{
              width: '100%', background: 'transparent', border: '1px solid var(--border)', color: scanning ? 'var(--text-muted)' : 'var(--text-secondary)',
              borderRadius: 'var(--radius-sm)', padding: '10px 14px', fontSize: 13, fontWeight: 600, cursor: scanning ? 'wait' : 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, transition: 'all 0.15s',
            }}>
              {scanning
                ? <><span style={{ width: 12, height: 12, border: '2px solid var(--text-muted)', borderTopColor: 'var(--text-secondary)', borderRadius: '50%', animation: 'spin 0.7s linear infinite', display: 'inline-block' }} />Scan en cours…</>
                : <><svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>Scanner les offres</>
              }
            </button>
            {scanDateFmt && <div style={{ fontSize: 10, color: 'var(--text-muted)', textAlign: 'center', marginTop: 6 }}>Dernier scan : {scanDateFmt}</div>}
          </div>
        </div>

        {/* Bottom: Quota + User */}
        <div style={{ borderTop: '1px solid var(--border)', padding: '12px 14px' }}>
          {/* Quota widget */}
          <div style={{ marginBottom: 14 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <span style={{ fontSize: 11, fontWeight: 500, color: 'var(--text-muted)' }}>Usage LLM</span>
              <span style={{ fontSize: 11, color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}>{quotaUsed}/{quotaMax}</span>
            </div>
            <div style={{ width: '100%', height: 3, borderRadius: 2, background: 'var(--bg-active)', overflow: 'hidden' }}>
              <div style={{ width: `${quotaPct}%`, height: '100%', borderRadius: 2, background: quotaColor, transition: 'width 0.5s ease, background 0.3s' }} />
            </div>
          </div>

          {/* User */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0' }}>
            {user?.user_metadata?.avatar_url
              ? <img src={user.user_metadata.avatar_url} alt="" style={{ width: 26, height: 26, borderRadius: '50%', border: '1px solid var(--border)', flexShrink: 0 }} />
              : <div style={{ width: 26, height: 26, borderRadius: '50%', background: 'var(--bg-active)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700, color: 'var(--text-secondary)', flexShrink: 0 }}>{(user?.email?.[0] || '?').toUpperCase()}</div>
            }
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 110 }}>{user?.user_metadata?.full_name || user?.email?.split('@')[0]}</div>
            </div>
            <button onClick={signOut} title="Deconnexion" style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: 4, display: 'flex', alignItems: 'center', borderRadius: 4, transition: 'color 0.15s', flexShrink: 0 }}
              onMouseEnter={e => e.currentTarget.style.color = 'var(--red)'}
              onMouseLeave={e => e.currentTarget.style.color = 'var(--text-muted)'}
            >
              <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" /></svg>
            </button>
          </div>
        </div>
      </div>

      {/* ── Main content area ── */}
      <div style={{ flex: 1, marginLeft: isMobile ? 0 : SIDEBAR_W, minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>

        {/* Mobile top bar */}
        {isMobile && (
          <div style={{ height: 56, background: 'var(--bg-raised)', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', padding: '0 16px', gap: 12, position: 'sticky', top: 0, zIndex: 20 }}>
            <button onClick={() => setSidebarOpen(true)} style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer', padding: 4, display: 'flex' }}>
              <svg width="22" height="22" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" /></svg>
            </button>
            <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', flex: 1 }}>Mass Apply</div>
            {user?.user_metadata?.avatar_url
              ? <img src={user.user_metadata.avatar_url} alt="" style={{ width: 28, height: 28, borderRadius: '50%' }} />
              : <div style={{ width: 28, height: 28, borderRadius: '50%', background: 'var(--bg-active)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700, color: 'var(--text-secondary)' }}>{(user?.email?.[0] || '?').toUpperCase()}</div>
            }
          </div>
        )}

        {/* Stats cards */}
        <div style={{ padding: '20px 24px 0' }}>
          <div style={{ display: 'grid', gridTemplateColumns: isMobile ? 'repeat(3, 1fr)' : 'repeat(6, 1fr)', gap: 10 }}>
            {STAT_ITEMS.map((s, i) => {
              const active = statsFilter === s.f && s.f !== null
              return (
                <div key={i} onClick={() => {
                  if (s.f === null) { setStatsFilter(null); setTab('offers'); return }
                  if (s.f === 'applied' || s.f === 'interview') { setTab('kanban'); setStatsFilter(null); return }
                  setStatsFilter(statsFilter === s.f ? null : s.f); setTab('offers')
                }} style={{
                  background: active ? 'var(--bg-surface)' : 'var(--bg-raised)', border: `1px solid ${active ? 'rgba(224,119,51,0.15)' : 'var(--border)'}`,
                  borderRadius: 'var(--radius-md)', padding: '18px 20px', cursor: 'pointer',
                  borderLeft: active ? '3px solid var(--accent)' : '3px solid transparent',
                  opacity: statsFilter && !active && s.f !== null ? 0.35 : 1,
                  transition: 'all 0.2s ease', userSelect: 'none',
                  boxShadow: active ? '0 2px 12px rgba(224,119,51,0.06)' : 'none',
                }}>
                  <div style={{ fontSize: 28, fontWeight: 800, color: active ? 'var(--accent)' : 'var(--text-primary)', lineHeight: 1, fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.02em' }}>{s.v}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8, fontWeight: 500, letterSpacing: '0.02em', textTransform: 'uppercase' }}>{s.l}</div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Filters */}
        {tab === 'offers' && (
          <div style={{ padding: '20px 24px 0' }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 14 }}>
              <div style={{ position: 'relative', flex: 1, minWidth: 220 }}>
                <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', pointerEvents: 'none' }}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                <input type="text" placeholder="Rechercher par #ID, titre, entreprise, competence…" value={search} onChange={e => setSearch(e.target.value)} style={{ width: '100%', background: 'var(--bg-raised)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: '8px 36px 8px 34px', fontSize: 13, color: 'var(--text-primary)', outline: 'none', transition: 'border-color 0.15s' }} />
                {search && <button onClick={() => setSearch('')} style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', background: 'none', border: 'none', cursor: 'pointer', fontSize: 12 }}>×</button>}
              </div>
              <Select value={sort} onChange={setSort} options={[['fresh', 'Recents'], ['score', 'Score'], ['alpha', 'A → Z']]} />
              <Select value={tier} onChange={setTier} options={[['all', 'Toutes villes'], ['paris', 'Paris / IDF'], ['lyon', 'Lyon'], ['marseille', 'Marseille / Sud'], ['lille', 'Lille'], ['toulouse', 'Toulouse'], ['bordeaux', 'Bordeaux'], ['nantes', 'Nantes'], ['nice', 'Nice / Sophia'], ['montpellier', 'Montpellier'], ['strasbourg', 'Strasbourg'], ['rennes', 'Rennes'], ['T1', 'T1 — Toutes grandes'], ['T2', 'T2 — Moyennes'], ['T3', 'T3 — Autres']]} />
              <Select value={contract} onChange={setContract} options={[['all', 'CDI + CDD'], ['CDI', 'CDI'], ['CDD', 'CDD']]} />
              <Select value={source} onChange={setSource} options={[['all', 'Toutes sources'], ...Object.entries(SOURCE_LABELS).map(([k, v]) => [k, v])]} />
              <Select value={String(minScore)} onChange={v => setMinScore(Number(v))} options={[['0', 'Tous scores'], ['20', '≥ 20'], ['40', '≥ 40']]} />

              {/* View toggle */}
              <div style={{ display: 'flex', background: 'var(--bg-raised)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)', padding: 3, gap: 2 }}>
                {[
                  { v: 'cards', icon: <svg width="13" height="13" fill="currentColor" viewBox="0 0 20 20"><path d="M5 3a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2V5a2 2 0 00-2-2H5zM5 11a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2v-2a2 2 0 00-2-2H5zM11 5a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V5zM11 13a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" /></svg> },
                  { v: 'list', icon: <svg width="13" height="13" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M3 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z" clipRule="evenodd" /></svg> },
                ].map(btn => (
                  <button key={btn.v} onClick={() => setView(btn.v)} style={{ background: view === btn.v ? 'var(--bg-active)' : 'transparent', color: view === btn.v ? 'var(--text-primary)' : 'var(--text-muted)', border: 'none', borderRadius: 6, padding: '5px 7px', cursor: 'pointer', display: 'flex', alignItems: 'center', transition: 'all 0.15s' }}>{btn.icon}</button>
                ))}
              </div>

              <div style={{ display: 'flex', alignItems: 'center', marginLeft: 'auto', color: 'var(--text-muted)', fontSize: 12 }}>
                <span style={{ color: 'var(--text-secondary)', fontWeight: 600, marginRight: 4, fontVariantNumeric: 'tabular-nums' }}>{filtered.length}</span> resultats
              </div>
              {liked.size > 0 && (
                <button onClick={handleBatchGenerate} disabled={batchProgress?.running} style={{
                  padding: '7px 14px', background: batchProgress?.running ? 'var(--bg-active)' : 'var(--accent)',
                  color: batchProgress?.running ? 'var(--text-muted)' : '#fff', border: 'none',
                  borderRadius: 'var(--radius-sm)', fontSize: 12, fontWeight: 600,
                  cursor: batchProgress?.running ? 'wait' : 'pointer', display: 'flex', alignItems: 'center', gap: 6,
                }}>
                  {batchProgress?.running
                    ? <><span style={{ width: 10, height: 10, border: '2px solid var(--text-muted)', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 0.7s linear infinite', display: 'inline-block' }} />{batchProgress.done}/{batchProgress.total}</>
                    : <><svg width="12" height="12" viewBox="0 0 24 24" fill="var(--red)" stroke="none"><path d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" /></svg>Generer {liked.size} likes</>
                  }
                </button>
              )}
            </div>

            {/* Metier pills */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 20 }}>
              <button onClick={() => setMetierFilter('all')} style={{ fontSize: 12, padding: '5px 14px', borderRadius: 20, border: '1px solid', cursor: 'pointer', fontWeight: 500, transition: 'all 0.15s', ...(metierFilter === 'all' ? { background: 'var(--bg-active)', color: 'var(--text-primary)', borderColor: 'var(--text-muted)' } : { background: 'transparent', color: 'var(--text-muted)', borderColor: 'var(--border)' }) }}>Tous</button>
              <button onClick={() => setMetierFilter(metierFilter === '_profile' ? 'all' : '_profile')} style={{ fontSize: 12, padding: '5px 14px', borderRadius: 20, cursor: 'pointer', fontWeight: 500, transition: 'all 0.15s', display: 'flex', alignItems: 'center', gap: 6, border: `1px solid ${metierFilter === '_profile' ? 'var(--accent)' : 'var(--border)'}`, background: metierFilter === '_profile' ? 'var(--accent-glow)' : 'transparent', color: metierFilter === '_profile' ? 'var(--accent)' : 'var(--text-muted)' }}>
                Mon profil
              </button>
              {METIER_RULES.map(m => {
                const count = metierCounts[m.label] || 0
                if (!count) return null
                const active = metierFilter === m.label
                return (
                  <button key={m.label} onClick={() => setMetierFilter(active ? 'all' : m.label)} style={{ fontSize: 12, padding: '5px 14px', borderRadius: 20, cursor: 'pointer', fontWeight: 500, transition: 'all 0.15s', display: 'flex', alignItems: 'center', gap: 6, border: `1px solid ${active ? 'var(--text-muted)' : 'var(--border)'}`, background: active ? 'var(--bg-active)' : 'transparent', color: active ? 'var(--text-primary)' : 'var(--text-muted)' }}>
                    {m.label}<span style={{ opacity: 0.5 }}>{count}</span>
                  </button>
                )
              })}
            </div>
          </div>
        )}

        {/* Content */}
        <main style={{ padding: tab === 'kanban' ? '24px 24px 60px' : '0 24px 60px', flex: 1 }}>
          {tab === 'profile' ? (
            <ProfilePage onRescan={handleScan} onCreateProfile={() => setCvGate({ offer: null })} onProfileChange={loadSidebarProfiles} />
          ) : tab === 'templates' ? (
            <TemplateEditor />
          ) : tab === 'kanban' ? (
            <KanbanBoard applications={applications} onStatusChange={handleStatusUpdate} onNotesChange={handleNotesUpdate} />
          ) : tab === 'technicien' ? (
            /* Technicien tab (admin only) */
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <div>
                  <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)' }}>Offres Technicien / Support</div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>Support informatique, helpdesk, systemes et reseaux, deploiement</div>
                </div>
                <button onClick={handleTechScan} disabled={techScanning} style={{
                  padding: '8px 16px', background: 'transparent', border: '1px solid var(--border)',
                  color: techScanning ? 'var(--text-muted)' : 'var(--text-secondary)', borderRadius: 'var(--radius-sm)',
                  fontSize: 12, fontWeight: 600, cursor: techScanning ? 'wait' : 'pointer',
                  display: 'flex', alignItems: 'center', gap: 6,
                }}>
                  {techScanning ? <><span style={{ width: 10, height: 10, border: '2px solid var(--text-muted)', borderTopColor: 'var(--text-secondary)', borderRadius: '50%', animation: 'spin 0.7s linear infinite', display: 'inline-block' }} />Scan en cours...</> : 'Scanner'}
                </button>
              </div>
              {!techOffers || techOffers.total === 0 ? (
                <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--text-muted)', fontSize: 14 }}>
                  {techScanning ? 'Scan en cours...' : 'Aucune offre. Lancez un scan pour chercher des postes technicien/support.'}
                </div>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 14 }}>
                  {(techOffers.offers || []).map((offer, i) => (
                    <OfferCard key={`tech-${offer.url}-${i}`} offer={offer} scanDate={techOffers.scan_date} generated={generations[offer.url]} onGenerate={handleGenerate} applied={appliedCompanies.has(offer.company?.toLowerCase())} isLiked={liked.has(offer.url)} onToggleLike={toggleLike} onOpenPreview={(o, gen) => setPreview({ offer: o, result: { success: true, cv_url: gen.cv_url, letter_url: gen.letter_url, inspo: gen.inspo || {} } })} />
                  ))}
                </div>
              )}
            </div>
          ) : (data?.pending_scan || (allOffers.length === 0 && scanning)) ? (
            /* First scan in progress — loading mascot */
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '80px 24px', textAlign: 'center' }}>
              <div style={{ width: 80, height: 80, borderRadius: '50%', background: 'var(--bg-raised)', border: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 24, animation: 'pulse 2s ease infinite' }}>
                <svg width="36" height="36" fill="none" viewBox="0 0 24 24" stroke="var(--accent)" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
              </div>
              <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>Recherche en cours...</div>
              <div style={{ fontSize: 14, color: 'var(--text-muted)', maxWidth: 400, lineHeight: 1.6, marginBottom: 20 }}>
                On scanne 8 job boards pour trouver les offres qui correspondent a votre profil. Ca prend environ 2-3 minutes.
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, width: '100%', maxWidth: 320 }}>
                {[
                  { label: 'Welcome to the Jungle', delay: '0s' },
                  { label: 'France Travail', delay: '0.3s' },
                  { label: 'LinkedIn', delay: '0.6s' },
                  { label: 'Indeed', delay: '0.9s' },
                  { label: 'APEC', delay: '1.2s' },
                  { label: 'Adzuna + PMEjob', delay: '1.5s' },
                ].map((src, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 14px', background: 'var(--bg-raised)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)', animation: `fadeUp 0.3s ease ${src.delay} both` }}>
                    <div style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--accent)', animation: 'pulse 1.5s ease infinite', animationDelay: src.delay }} />
                    <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{src.label}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : filtered.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '80px 0', color: 'var(--text-muted)', fontSize: 14 }}>Aucune offre ne correspond.</div>
          ) : (
            <>
              {view === 'cards' ? (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 14 }}>
                  {paginatedOffers.map((offer, i) => {
                    const applied = appliedCompanies.has(offer.company?.toLowerCase())
                    return <OfferCard key={`${offer.url}-${i}`} offer={offer} scanDate={scanDate} generated={generations[offer.url]} onGenerate={handleGenerate} applied={applied} isLiked={liked.has(offer.url)} onToggleLike={toggleLike} onOpenPreview={(o, gen) => setPreview({ offer: o, result: { success: true, cv_url: gen.cv_url, letter_url: gen.letter_url, inspo: gen.inspo || {} } })} />
                  })}
                </div>
              ) : (
                <div style={{ background: 'var(--bg-raised)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
                  {paginatedOffers.map((offer, i) => {
                    const applied = appliedCompanies.has(offer.company?.toLowerCase())
                    return <OfferRow key={`${offer.url}-${i}`} offer={offer} scanDate={scanDate} applied={applied} />
                  })}
                </div>
              )}

              {/* Pagination */}
              {totalPages > 1 && (
                <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 8, marginTop: 20, paddingBottom: 20 }}>
                  <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0} style={{
                    padding: '6px 14px', background: 'var(--bg-raised)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
                    color: page === 0 ? 'var(--text-faint)' : 'var(--text-secondary)', fontSize: 12, fontWeight: 600,
                    cursor: page === 0 ? 'default' : 'pointer',
                  }}>Precedent</button>

                  <div style={{ display: 'flex', gap: 4 }}>
                    {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
                      let p
                      if (totalPages <= 7) p = i
                      else if (page < 3) p = i
                      else if (page > totalPages - 4) p = totalPages - 7 + i
                      else p = page - 3 + i
                      return (
                        <button key={p} onClick={() => setPage(p)} style={{
                          width: 32, height: 32, borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)',
                          background: p === page ? 'var(--bg-active)' : 'var(--bg-raised)',
                          color: p === page ? 'var(--text-primary)' : 'var(--text-muted)',
                          fontSize: 12, fontWeight: p === page ? 700 : 400, cursor: 'pointer',
                        }}>{p + 1}</button>
                      )
                    })}
                  </div>

                  <button onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1} style={{
                    padding: '6px 14px', background: 'var(--bg-raised)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
                    color: page >= totalPages - 1 ? 'var(--text-faint)' : 'var(--text-secondary)', fontSize: 12, fontWeight: 600,
                    cursor: page >= totalPages - 1 ? 'default' : 'pointer',
                  }}>Suivant</button>
                </div>
              )}
            </>
          )}
        </main>
      </div>

      {/* ── Preview Modal ── */}
      {/* ── Generation Walkthrough Modal ── */}
      {/* CV Upload Gate */}
      {/* Company name gate for anonymous offers */}
      {companyGate && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 200, backdropFilter: 'blur(4px)' }}>
          <div style={{ background: 'var(--bg-raised)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', width: '100%', maxWidth: 420, padding: '28px 32px', animation: 'fadeUp 0.3s ease' }}>
            <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 6 }}>Nom de l'entreprise</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 16, lineHeight: 1.5 }}>
              Cette offre ne mentionne pas le nom de l'entreprise. Visitez l'offre pour le trouver, puis saisissez-le ici pour une candidature personnalisee.
            </div>
            <a href={companyGate.offer.url} target="_blank" rel="noopener noreferrer" style={{ fontSize: 12, color: 'var(--accent)', textDecoration: 'none', fontWeight: 600, display: 'inline-block', marginBottom: 12 }}>Voir l'offre ↗</a>
            <input value={companyGate._name || ''} onChange={e => setCompanyGate(g => ({...g, _name: e.target.value}))}
              onKeyDown={e => { if (e.key === 'Enter') { const o = {...companyGate.offer, company: (companyGate._name || '').trim() || companyGate.offer.company, _companyOverride: true}; setCompanyGate(null); handleGenerate(o) } }}
              placeholder="ex: Capgemini, Sopra Steria..."
              autoFocus
              style={{ width: '100%', padding: '10px 14px', background: 'var(--bg-base)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-primary)', fontSize: 13, outline: 'none', marginBottom: 12 }} />
            <div style={{ display: 'flex', gap: 8 }}>
              <button onClick={() => { const o = {...companyGate.offer, company: (companyGate._name || '').trim() || companyGate.offer.company, _companyOverride: true}; setCompanyGate(null); handleGenerate(o) }} style={{
                flex: 1, padding: '10px', background: 'var(--accent)', color: '#fff', border: 'none',
                borderRadius: 'var(--radius-sm)', fontSize: 13, fontWeight: 600, cursor: 'pointer',
              }}>{(companyGate._name || '').trim() ? 'Generer' : 'Generer quand meme'}</button>
              <button onClick={() => setCompanyGate(null)} style={{
                padding: '10px 16px', background: 'none', border: '1px solid var(--border)',
                color: 'var(--text-muted)', borderRadius: 'var(--radius-sm)', fontSize: 13, cursor: 'pointer',
              }}>Annuler</button>
            </div>
          </div>
        </div>
      )}

      {/* CV upload gate */}
      {cvGate && <CvGateModal offer={cvGate.offer} onComplete={(offer) => { setCvGate(null); setHasRealCv(true); if (offer) handleGenerate(offer); handleScan() }} onClose={() => setCvGate(null)} />}

      {/* Generation Walkthrough */}
      <GenerationModal genModal={genModal} onCancel={() => { genModal?.abortController?.abort(); setGenModal(null) }} onMinimize={() => setGenModal(null)} />

      {/* ── Preview Modal ── */}
      {preview && <PreviewModal preview={preview} onConfirm={() => setPreview(null)} onRecompile={handleRecompile} onClose={() => setPreview(null)} onRegenerate={handleGenerate} />}

      {/* ── Batch Progress (floating) ── */}
      {batchProgress?.running && (
        <div style={{ position: 'fixed', bottom: 80, right: 20, background: 'var(--bg-raised)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '14px 18px', width: 300, zIndex: 98, boxShadow: 'var(--shadow-lg)', animation: 'fadeUp 0.3s ease' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
            <div style={{ width: 16, height: 16, border: '2px solid var(--accent-dim)', borderTopColor: 'var(--accent)', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>Generation en cours</div>
          </div>
          <div style={{ width: '100%', height: 6, borderRadius: 3, background: 'var(--bg-active)', overflow: 'hidden', marginBottom: 8 }}>
            <div style={{ width: `${(batchProgress.done / batchProgress.total) * 100}%`, height: '100%', borderRadius: 3, background: 'var(--accent)', transition: 'width 0.5s ease' }} />
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
            {batchProgress.done} / {batchProgress.total} candidatures
            {batchProgress.current && <span style={{ color: 'var(--text-secondary)' }}> — {batchProgress.current.company}</span>}
          </div>
        </div>
      )}

      {/* ── Gen Log ── */}
      {genLog.length > 0 && (
        <div style={{ position: 'fixed', bottom: 20, right: 20, background: 'var(--bg-raised)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '12px 16px', width: 340, maxHeight: 200, overflowY: 'auto', zIndex: 99, boxShadow: 'var(--shadow-lg)', fontFamily: 'ui-monospace, monospace' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
            <span style={{ color: 'var(--text-muted)', fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Log</span>
            <button onClick={() => setGenLog([])} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 12 }}>×</button>
          </div>
          {genLog.map((l, i) => (
            <div key={i} style={{ fontSize: 11, lineHeight: 1.7, color: l.type === 'ok' ? 'var(--green)' : l.type === 'err' ? 'var(--red)' : l.type === 'meta' ? 'var(--text-secondary)' : 'var(--text-secondary)' }}>
              <span style={{ color: 'var(--text-faint)', marginRight: 6 }}>{l.time}</span>{l.msg}
            </div>
          ))}
        </div>
      )}

      {/* ── Toast ── */}
      {toast && (
        <div style={{
          position: 'fixed', bottom: 20, left: isMobile ? '50%' : `calc(50% + ${SIDEBAR_W / 2}px)`, transform: 'translateX(-50%)',
          background: toast.type === 'ok' ? 'var(--green-dim)' : toast.type === 'warn' ? 'var(--yellow-dim)' : 'var(--red-dim)',
          border: `1px solid ${toast.type === 'ok' ? 'var(--green)' : toast.type === 'warn' ? 'var(--yellow)' : 'var(--red)'}`,
          color: toast.type === 'ok' ? 'var(--green)' : toast.type === 'warn' ? 'var(--yellow)' : 'var(--red)',
          borderRadius: 'var(--radius-md)', padding: '10px 20px', fontSize: 13, fontWeight: 500,
          zIndex: 100, boxShadow: 'var(--shadow-lg)', display: 'flex', alignItems: 'center', gap: 8,
          animation: 'fadeIn 0.2s ease', backdropFilter: 'blur(12px)',
        }}>
          {toast.msg}
          <button onClick={() => setToast(null)} style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', opacity: 0.6, fontSize: 14, marginLeft: 4 }}>×</button>
        </div>
      )}
    </div>
  )
}
