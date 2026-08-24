import React, { useRef, useState } from 'react';
import { identityHeaders } from './identity.js';
import { useIdentity } from './useIdentity.js';
import { buildChatOutcome, buildCompletionRequest } from './chatResponse.js';

const API = import.meta.env.VITE_GATEWAY_URL || 'http://localhost:4000';

function IdentityForm({ onSave }) {
  const [employeeId, setEmployeeId] = useState('');
  const [name, setName] = useState('');
  const [department, setDepartment] = useState('');
  const [error, setError] = useState('');

  function submit(event) {
    event.preventDefault();
    setError('');
    try {
      onSave({ employeeId, name, department });
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <main className="login-shell">
      <form onSubmit={submit} className="login-card">
        <p className="eyebrow">SENTINELAI / EMPLOYEE CHAT</p>
        <h1>Identify yourself</h1>
        <p>
          No password needed -- this just labels your requests for the audit dashboard.
          Stored only in this browser.
        </p>
        <label>
          Employee ID
          <input value={employeeId} onChange={(e) => setEmployeeId(e.target.value)} placeholder="e.g. EMP-1042" required />
        </label>
        <label>
          Name (optional)
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Priya Sharma" />
        </label>
        <label>
          Department (optional)
          <input value={department} onChange={(e) => setDepartment(e.target.value)} placeholder="e.g. Sales" />
        </label>
        {error && <p className="error">{error}</p>}
        <button>Continue</button>
        <p><a href="/">&larr; Admin console</a></p>
      </form>
    </main>
  );
}

function IdentifiedPanel({ identity, onClear }) {
  const [checkResult, setCheckResult] = useState(null);
  const [checking, setChecking] = useState(false);

  async function verifyConnection() {
    setChecking(true);
    setCheckResult(null);
    try {
      const response = await fetch(`${API}/health`, { headers: identityHeaders(identity) });
      if (!response.ok) throw new Error(`Gateway responded with ${response.status}`);
      setCheckResult({ ok: true, message: 'Gateway reachable, identity headers accepted.' });
    } catch (err) {
      setCheckResult({ ok: false, message: err.message });
    } finally {
      setChecking(false);
    }
  }

  return (
    <main className="app">
      <header>
        <div>
          <p className="eyebrow">SENTINELAI / EMPLOYEE CHAT</p>
          <h1>Hi, {identity.name}</h1>
        </div>
        <div className="header-actions">
          <button className="secondary" onClick={onClear}>Not you? Change identity</button>
        </div>
      </header>
      <section className="table-card">
        <h2>Identity confirmed</h2>
        <p>
          Employee ID <strong>{identity.employeeId}</strong>
          {identity.department ? <> &middot; {identity.department}</> : null}
        </p>
        <p>
          Every request from this browser will now carry <code>x-employee-id</code>,{' '}
          <code>x-employee-name</code>{identity.department ? <>, and <code>x-employee-department</code></> : null}{' '}
          so SentinelAI can attribute and audit it.
        </p>
        <button className="secondary" onClick={verifyConnection} disabled={checking}>
          {checking ? 'Checking…' : 'Verify gateway connection'}
        </button>
        {checkResult && (
          <p className={checkResult.ok ? '' : 'error'}>{checkResult.message}</p>
        )}
      </section>
      <ChatSurface identity={identity} />
    </main>
  );
}

// Task 8.2 — Chat UI. Each entry in `turns` is one send/receive round:
// { id, prompt, status: 'pending'|'ALLOW'|'SANITIZE'|'BLOCK'|'ERROR', outcome }
// `outcome` is exactly what chatResponse.js's buildChatOutcome() returns
// (shape varies by status; see that file for the four variants).
let turnSeq = 0;

function ChatSurface({ identity }) {
  const [turns, setTurns] = useState([]);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const composerRef = useRef(null);

  async function send(promptText) {
    const text = promptText.trim();
    if (!text || sending) return;
    setSending(true);
    setDraft('');
    const id = ++turnSeq;
    setTurns((prev) => [...prev, { id, prompt: text, status: 'pending', outcome: null }]);
    try {
      const response = await fetch(`${API}/v1/chat/completions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...identityHeaders(identity) },
        body: JSON.stringify(buildCompletionRequest(text)),
      });
      const body = await response.json().catch(() => ({}));
      const outcome = buildChatOutcome({ ok: response.ok, status: response.status, headers: response.headers, body });
      setTurns((prev) => prev.map((turn) => (turn.id === id ? { ...turn, status: outcome.state, outcome } : turn)));
    } catch (err) {
      const outcome = { state: 'ERROR', message: err.message || 'Network request failed.' };
      setTurns((prev) => prev.map((turn) => (turn.id === id ? { ...turn, status: 'ERROR', outcome } : turn)));
    } finally {
      setSending(false);
    }
  }

  function submit(event) {
    event.preventDefault();
    send(draft);
  }

  function editAndResend(promptText) {
    setDraft(promptText);
    composerRef.current?.focus();
  }

  return (
    <section className="table-card chat-surface">
      <h2>Chat</h2>
      {turns.length === 0 && (
        <p className="empty">Send a message below. SentinelAI screens every prompt before it reaches the model.</p>
      )}
      <div className="chat-thread">
        {turns.map((turn) => (
          <Turn key={turn.id} turn={turn} onEditAndResend={editAndResend} />
        ))}
      </div>
      <form onSubmit={submit} className="chat-composer">
        <textarea
          ref={composerRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(draft); }
          }}
          placeholder="Ask something… (Enter to send, Shift+Enter for a new line)"
          rows={3}
          disabled={sending}
        />
        <button disabled={sending || !draft.trim()}>{sending ? 'Sending…' : 'Send'}</button>
      </form>
    </section>
  );
}

function Turn({ turn, onEditAndResend }) {
  return (
    <div className="chat-turn">
      <div className="bubble user">{turn.prompt}</div>
      {turn.status === 'pending' && <p className="empty">Screening…</p>}
      {turn.status === 'ALLOW' && (
        <div className="bubble assistant">
          {turn.outcome.reply}
          {turn.outcome.flags.length > 0 && (
            <div className="sentinel-note advisory">
              {turn.outcome.flags.map((flag, i) => <p key={i}>{flag.message}</p>)}
            </div>
          )}
        </div>
      )}
      {turn.status === 'SANITIZE' && (
        <div className="bubble assistant">
          <div className="sentinel-note sanitize">
            <strong>Part of this message was masked before it was sent.</strong>
            {turn.outcome.flags.map((flag, i) => <p key={i}>{flag.message}</p>)}
          </div>
          {turn.outcome.reply}
        </div>
      )}
      {turn.status === 'BLOCK' && (
        <div className="sentinel-note block">
          <strong>Blocked — {turn.outcome.reason}</strong>
          {turn.outcome.categories.length > 0 && (
            <p>Categories: {turn.outcome.categories.join(', ')}</p>
          )}
          {turn.outcome.rewriteGuidance && <p>{turn.outcome.rewriteGuidance}</p>}
          <button className="secondary" onClick={() => onEditAndResend(turn.prompt)}>Edit and resend</button>
        </div>
      )}
      {turn.status === 'ERROR' && (
        <div className="sentinel-note error">
          <strong>Something went wrong.</strong>
          <p>{turn.outcome.message}</p>
          <button className="secondary" onClick={() => onEditAndResend(turn.prompt)}>Edit and resend</button>
        </div>
      )}
    </div>
  );
}

export default function ChatEntry() {
  const { identity, save, clear } = useIdentity();
  if (!identity) return <IdentityForm onSave={save} />;
  return <IdentifiedPanel identity={identity} onClear={clear} />;
}
