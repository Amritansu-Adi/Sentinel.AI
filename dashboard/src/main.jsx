import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Bar, BarChart, Cell, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import ChatEntry from './ChatEntry.jsx';
import './styles.css';

const API = import.meta.env.VITE_GATEWAY_URL || 'http://localhost:4000';
const colors = { ALLOW: '#34d399', SANITIZE: '#fbbf24', BLOCK: '#fb7185' };

async function request(path, token, options = {}) {
  const response = await fetch(`${API}${path}`, { ...options, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...options.headers } });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.message || 'Request failed');
  return data;
}

function Login({ onLogin }) {
  const [email, setEmail] = useState('admin@sentinelai.local');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  async function submit(event) {
    event.preventDefault(); setError('');
    try { onLogin(await request('/auth/login', null, { method: 'POST', body: JSON.stringify({ email, password }) })); }
    catch (err) { setError(err.message); }
  }
  return <main className="login-shell"><form onSubmit={submit} className="login-card"><p className="eyebrow">SENTINELAI</p><h1>Security command center</h1><p>Sign in with the configured admin account.</p><label>Email<input type="email" value={email} onChange={e => setEmail(e.target.value)} required /></label><label>Password<input type="password" value={password} onChange={e => setPassword(e.target.value)} required /></label>{error && <p className="error">{error}</p>}<button>Sign in</button><p><a href="/chat">Looking for the employee chat? Go there &rarr;</a></p></form></main>;
}

function Dashboard({ token, onLogout }) {
  const [data, setData] = useState(null); const [employees, setEmployees] = useState([]); const [error, setError] = useState('');
  async function load() {
    try { setError(''); const [summary, employeeData] = await Promise.all([request('/stats/summary', token), request('/stats/employees', token)]); setData(summary); setEmployees(employeeData.employees); }
    catch (err) { setError(err.message); if (/token|admin|unauthorized/i.test(err.message)) onLogout(); }
  }
  useEffect(() => { load(); }, []);
  if (!data) return <main className="loading">{error || 'Loading protected audit metrics…'}</main>;
  const actions = [['ALLOW', data.today.allowed], ['SANITIZE', data.today.sanitized], ['BLOCK', data.today.blocked]];
  return <main className="app"><header><div><p className="eyebrow">SENTINELAI / ADMIN</p><h1>Traffic risk overview</h1></div><div className="header-actions"><button className="secondary" onClick={load}>Refresh</button><button className="secondary" onClick={onLogout}>Sign out</button></div></header>{error && <p className="error">{error}</p>}<section className="metrics"><Metric title="Requests today" value={data.today.total}/><Metric title="Allowed" value={data.today.allowed} tone="green"/><Metric title="Sanitized" value={data.today.sanitized} tone="yellow"/><Metric title="Blocked" value={data.today.blocked} tone="red"/><Metric title="Average risk" value={`${data.today.avg_risk}/100`}/></section><section className="grid"><ChartCard title="Requests over time"><ResponsiveContainer width="100%" height={240}><LineChart data={data.requests_over_time}><XAxis dataKey="hour"/><YAxis allowDecimals={false}/><Tooltip/><Line type="monotone" dataKey="requests" stroke="#38bdf8" strokeWidth={3}/></LineChart></ResponsiveContainer></ChartCard><ChartCard title="Action breakdown"><ResponsiveContainer width="100%" height={240}><BarChart data={actions.map(([action, count]) => ({ action, count }))}><XAxis dataKey="action"/><YAxis allowDecimals={false}/><Tooltip/><Bar dataKey="count">{actions.map(([action]) => <Cell key={action} fill={colors[action]}/>)}</Bar></BarChart></ResponsiveContainer></ChartCard><ChartCard title="Top violation categories"><ResponsiveContainer width="100%" height={240}><BarChart data={data.top_categories} layout="vertical"><XAxis type="number" allowDecimals={false}/><YAxis type="category" dataKey="category" width={185}/><Tooltip/><Bar dataKey="count" fill="#a78bfa"/></BarChart></ResponsiveContainer></ChartCard></section><section className="table-card"><h2>Employee risk</h2><table><thead><tr><th>Employee</th><th>Department</th><th>Requests</th><th>Violations</th><th>Average risk</th><th>Tier</th></tr></thead><tbody>{employees.map(employee => <tr key={employee.employee_id}><td>{employee.name}<small>{employee.employee_id}</small></td><td>{employee.department || '—'}</td><td>{employee.total_requests}</td><td>{employee.total_violations}</td><td>{employee.avg_risk}</td><td><span className={`tier ${employee.risk_tier.toLowerCase()}`}>{employee.risk_tier}</span></td></tr>)}{!employees.length && <tr><td colSpan="6" className="empty">No audited requests yet.</td></tr>}</tbody></table></section></main>;
}
function Metric({ title, value, tone = '' }) { return <article className={`metric ${tone}`}><span>{title}</span><strong>{value}</strong></article>; }
function ChartCard({ title, children }) { return <article className="chart-card"><h2>{title}</h2>{children}</article>; }
function App() {
  // Task 8.1: plain pathname branch, no router dependency added -- the
  // admin console (JWT-gated, "/") and the end-user chat entry ("/chat",
  // identity-gated only per project.md Task 8.1's explicit boundary
  // against a second auth system) are separate, unauthenticated-relative-
  // to-each-other surfaces. Vite's dev/preview servers serve index.html
  // for both paths by default (appType: 'spa'), so a direct load of
  // /chat works without extra server config.
  const [token, setToken] = useState(() => localStorage.getItem('sentinelai_token'));
  if (window.location.pathname.startsWith('/chat')) return <ChatEntry />;
  const login = data => { localStorage.setItem('sentinelai_token', data.access_token); setToken(data.access_token); }; const logout = () => { localStorage.removeItem('sentinelai_token'); setToken(null); }; return token ? <Dashboard token={token} onLogout={logout}/> : <Login onLogin={login}/>;
}
createRoot(document.getElementById('root')).render(<React.StrictMode><App/></React.StrictMode>);
