import React, { useEffect, useState } from 'react';
import { useAuth } from '../lib/auth';
import api from '../lib/api';
import { Link } from 'react-router-dom';
import {
  Play,
  Square,
  Trash2,
  Terminal,
  ExternalLink,
  RefreshCw,
  Eye,
  ThumbsUp,
  Activity,
  MessageSquare,
  ShieldAlert,
  Plus,
  Clock,
  Edit2,
} from 'lucide-react';
import { useAIJob } from '../hooks/useAIJob';

interface App {
  id: number;
  name: string;
  stack?: string;
  status: string;
  container_id?: string;
  image_tag?: string;
  internal_port?: number;
  max_wake_seconds?: number;
  last_seen?: string;
  created_at: string;
  build_log_path?: string;
  owner?: string;
  visibility: string;
  description?: string;
  tags?: string;
  view_count: number;
  upvote_count: number;
  approval_status?: string;
}

const STATUS_MAP: Record<string, { label: string; cls: string; dot: string }> = {
  RUNNING: { label: 'Running', cls: 'bg-emerald-50 text-emerald-755 text-emerald-700 border-emerald-200', dot: 'bg-emerald-500' },
  STOPPED: { label: 'Stopped', cls: 'bg-slate-100 text-slate-600 border-slate-200', dot: 'bg-slate-400' },
  BUILDING: { label: 'Building', cls: 'bg-amber-50 text-amber-700 border-amber-200', dot: 'bg-amber-500 animate-pulse' },
  FAILED: { label: 'Failed', cls: 'bg-rose-50 text-rose-705 text-rose-700 border-rose-250', dot: 'bg-rose-500' },
};

const APPROVAL_MAP: Record<string, { label: string; cls: string }> = {
  approved: { label: 'Approved', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  rejected: { label: 'Rejected', cls: 'bg-rose-50 text-rose-700 border-rose-200' },
  pending: { label: 'Pending review', cls: 'bg-amber-50 text-amber-700 border-amber-250' },
};

export const Dashboard: React.FC = () => {
  const { user } = useAuth();
  const [apps, setApps] = useState<App[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeLogsApp, setActiveLogsApp] = useState<string | null>(null);
  const [logsContent, setLogsContent] = useState('');
  const [logsLoading, setLogsLoading] = useState(false);
  const [diagnosing, setDiagnosing] = useState(false);
  const doctorJob = useAIJob();
  
  // Edit App Metadata states
  const [editingApp, setEditingApp] = useState<App | null>(null);
  const [editDesc, setEditDesc] = useState('');
  const [editTags, setEditTags] = useState('');
  const [savingMeta, setSavingMeta] = useState(false);

  const toggleVisibility = async (appName: string, currentVisibility: string) => {
    const newVisibility = currentVisibility === 'public' ? 'private' : 'public';
    try {
      await api.patch(`/showcase/${appName}`, { visibility: newVisibility });
      fetchApps();
    } catch {
      alert('Failed to update visibility.');
    }
  };

  const handleSaveMetadata = async () => {
    if (!editingApp) return;
    setSavingMeta(true);
    try {
      await api.patch(`/showcase/${editingApp.name}`, {
        description: editDesc,
        tags: editTags
      });
      setEditingApp(null);
      fetchApps();
    } catch {
      alert('Failed to update metadata.');
    } finally {
      setSavingMeta(false);
    }
  };

  const handleDiagnoseLogs = () => {
    if (!activeLogsApp) return;
    setDiagnosing(true);
    doctorJob.submit(`/ai/deploy-doctor/${activeLogsApp}`, { build_log: logsContent });
  };

  const fetchApps = async () => {
    if (!user) return;
    try {
      const resp = await api.get(`/showcase/users/${user.username}`);
      setApps(resp.data.apps || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchApps();
    const interval = setInterval(() => {
      const hasBuilding = apps.some((a) => a.status === 'BUILDING');
      if (hasBuilding || apps.length === 0) fetchApps();
    }, 5000);
    return () => clearInterval(interval);
  }, [user, apps.map((a) => a.status).join(',')]);

  const handleStart = async (name: string) => {
    try { await api.post(`/deploy/start/${name}`); fetchApps(); }
    catch (e: any) { alert(e?.response?.data?.error || e?.response?.data?.detail || 'Failed to start.'); }
  };
  const handleStop = async (name: string) => {
    try { await api.post(`/deploy/stop/${name}`); fetchApps(); }
    catch (e: any) { alert(e?.response?.data?.error || e?.response?.data?.detail || 'Failed to stop.'); }
  };
  const handleDelete = async (name: string) => {
    if (!window.confirm(`Delete ${name}?`)) return;
    try { await api.delete(`/deploy/${name}`); fetchApps(); }
    catch { alert('Failed to delete.'); }
  };
  const fetchLogs = async (name: string) => {
    setActiveLogsApp(name);
    setLogsLoading(true);
    setLogsContent('');
    try {
      const resp = await api.get(`/deploy/${name}/logs`);
      setLogsContent(resp.data || 'No logs available.');
    } catch { setLogsContent('Failed to fetch logs.'); }
    finally { setLogsLoading(false); }
  };

  const running = apps.filter((a) => a.status === 'RUNNING').length;
  const building = apps.filter((a) => a.status === 'BUILDING').length;

  return (
    <div className="max-w-5xl mx-auto space-y-8">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black text-slate-900 tracking-tight">Your Applications</h1>
          <p className="text-sm text-slate-500 mt-1 font-semibold">Manage deployments, logs, and container lifecycles</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={fetchApps}
            className="inline-flex items-center gap-2 text-sm font-semibold text-slate-700 hover:text-slate-950 bg-white border border-slate-200 hover:border-slate-350 rounded-xl px-4 py-2.5 transition-all shadow-sm"
          >
            <RefreshCw size={14} /> Refresh
          </button>
          <Link
            to="/deploy"
            className="inline-flex items-center gap-2 text-sm font-bold text-white bg-indigo-600 hover:bg-indigo-700 rounded-xl px-5 py-2.5 transition-all shadow-md shadow-indigo-600/10 hover:shadow-indigo-600/25 hover:-translate-y-0.5"
          >
            <Plus size={14} /> New Deploy
          </Link>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {[
          { label: 'Total Apps', value: apps.length, color: 'text-slate-900' },
          { label: 'Running Now', value: running, color: 'text-emerald-600', bg: 'bg-emerald-50/50' },
          { label: 'Building Queue', value: building, color: 'text-amber-600', bg: 'bg-amber-50/50' },
        ].map((s) => (
          <div key={s.label} className={`bg-white border border-slate-200/80 rounded-2xl p-6 shadow-sm ${s.bg || ''}`}>
            <p className="text-xs text-slate-400 font-bold uppercase tracking-wider mb-2">{s.label}</p>
            <p className={`text-3xl font-black ${s.color}`}>
              {s.value}
            </p>
          </div>
        ))}
      </div>

      {/* Apps list */}
      {loading ? (
        <div className="h-48 flex items-center justify-center">
          <div className="w-8 h-8 border-3 border-indigo-600 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : apps.length === 0 ? (
        <div className="bg-white border border-slate-200 rounded-3xl p-16 text-center shadow-sm">
          <div className="w-14 h-14 rounded-2xl bg-slate-50 border border-slate-100 flex items-center justify-center mx-auto mb-5 shadow-inner">
            <Activity size={24} className="text-slate-400" />
          </div>
          <h3 className="font-extrabold text-slate-900 text-lg mb-1.5">No apps deployed yet</h3>
          <p className="text-sm text-slate-550 max-w-sm mx-auto mb-6">Deploy a Node, Python, Java, or static HTML workspace directory natively to your cloud.</p>
          <Link
            to="/deploy"
            className="inline-flex items-center gap-2 text-sm font-bold text-white bg-indigo-600 hover:bg-indigo-700 rounded-xl px-6 py-3 transition-colors shadow-md shadow-indigo-600/10"
          >
            <Plus size={14} /> Deploy first app
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {apps.map((app) => {
            const st = STATUS_MAP[app.status] ?? { label: app.status, cls: 'bg-slate-100 text-slate-500 border-slate-200', dot: 'bg-slate-400' };
            const ap = app.approval_status ? APPROVAL_MAP[app.approval_status] : null;
            return (
              <div
                key={app.id}
                className="bg-white border border-slate-200/80 hover:border-indigo-250 rounded-2xl p-5 flex flex-col md:flex-row md:items-center gap-5 transition-all shadow-sm card-hover"
              >
                {/* Left: info */}
                <div className="flex-1 min-w-0 space-y-2">
                  <div className="flex items-center gap-2.5 flex-wrap">
                    <div className={`w-2.5 h-2.5 rounded-full ${st.dot}`} />
                    <h3 className="font-bold text-slate-900 text-base">{app.name}</h3>
                    <span className={`text-xs font-bold px-2.5 py-0.5 rounded-full border ${st.cls}`}>
                      {st.label}
                    </span>
                    {app.stack && (
                      <span className="text-xs font-mono font-bold bg-slate-100 text-slate-655 text-slate-600 border border-slate-200 px-2 py-0.5 rounded-lg">
                        {app.stack}
                      </span>
                    )}
                    {ap && (
                      <span className={`text-xs font-bold px-2.5 py-0.5 rounded-full border ${ap.cls}`}>
                        {ap.label}
                      </span>
                    )}
                    <button
                      onClick={() => toggleVisibility(app.name, app.visibility)}
                      className={`text-[10px] font-extrabold px-2.5 py-0.5 rounded-full border transition-all ${
                        app.visibility === 'public'
                          ? 'bg-sky-50 text-sky-700 border-sky-200 hover:bg-sky-100'
                          : 'bg-slate-100 text-slate-700 border-slate-350 hover:bg-slate-200'
                      }`}
                      title="Toggle visibility"
                    >
                      {app.visibility === 'public' ? '🌍 Public' : '🔒 Private'}
                    </button>
                  </div>
                  
                  <div className="flex items-center gap-4 text-xs text-slate-400 font-semibold">
                    <span className="flex items-center gap-1"><Clock size={12} className="text-slate-400" /> {new Date(app.created_at).toLocaleDateString()}</span>
                    <span className="flex items-center gap-1"><Eye size={12} className="text-slate-400" /> {app.view_count} views</span>
                    <span className="flex items-center gap-1"><ThumbsUp size={12} className="text-slate-400" /> {app.upvote_count} upvotes</span>
                  </div>

                  {app.status === 'RUNNING' && (
                    <div className="pt-1">
                      <a
                        href={`http://${app.name}.quad.localhost:8000`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-700 font-bold"
                      >
                        Visit live application <ExternalLink size={11} />
                      </a>
                    </div>
                  )}
                </div>

                {/* Right: actions */}
                <div className="flex items-center gap-2 shrink-0">
                  <Link
                    to={`/ai/${app.name}`}
                    className="p-2.5 rounded-xl text-slate-500 hover:text-indigo-650 hover:bg-indigo-50 border border-slate-200 hover:border-indigo-200 transition-all shadow-sm"
                    title="AI Studio"
                  >
                    <MessageSquare size={15} />
                  </Link>
                  <button
                    onClick={() => {
                      setEditingApp(app);
                      setEditDesc(app.description || '');
                      setEditTags(app.tags || '');
                    }}
                    className="p-2.5 rounded-xl text-slate-500 hover:text-slate-900 hover:bg-slate-50 border border-slate-200 hover:border-slate-350 transition-all shadow-sm"
                    title="Edit app metadata"
                  >
                    <Edit2 size={15} />
                  </button>
                  <button
                    onClick={() => fetchLogs(app.name)}
                    className="p-2.5 rounded-xl text-slate-500 hover:text-slate-900 hover:bg-slate-50 border border-slate-200 hover:border-slate-350 transition-all shadow-sm"
                    title="Build logs"
                  >
                    <Terminal size={15} />
                  </button>
                  {app.status === 'RUNNING' ? (
                    <button
                      onClick={() => handleStop(app.name)}
                      className="p-2.5 rounded-xl text-rose-500 hover:bg-rose-50 border border-slate-200 hover:border-rose-200 transition-all shadow-sm"
                      title="Stop App"
                    >
                      <Square size={15} />
                    </button>
                  ) : (
                    <button
                      onClick={() => handleStart(app.name)}
                      disabled={app.status === 'BUILDING' || app.approval_status !== 'approved'}
                      className="p-2.5 rounded-xl text-emerald-600 hover:bg-emerald-50 border border-slate-200 hover:border-emerald-250 transition-all shadow-sm disabled:opacity-40 disabled:cursor-not-allowed"
                      title={app.approval_status !== 'approved' ? 'Waiting for admin approval' : 'Start App'}
                    >
                      <Play size={15} />
                    </button>
                  )}
                  <button
                    onClick={() => handleDelete(app.name)}
                    className="p-2.5 rounded-xl text-slate-400 hover:text-rose-600 hover:bg-rose-50 border border-slate-200 hover:border-rose-250 transition-all shadow-sm"
                    title="Delete Deploy"
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Logs Modal */}
      {activeLogsApp && (
        <div className="fixed inset-0 bg-slate-950/40 backdrop-blur-sm flex items-center justify-center p-6 z-50">
          <div className="max-w-4xl w-full bg-white border border-slate-200 rounded-3xl overflow-hidden flex flex-col h-[80vh] shadow-2xl">
            {/* Modal header */}
            <div className="px-6 py-4.5 border-b border-slate-100 flex justify-between items-center bg-slate-50/50">
              <div>
                <h3 className="font-extrabold text-slate-900 text-base">Logs — {activeLogsApp}</h3>
                <p className="text-xs text-slate-500 mt-0.5 font-semibold">Build output, deployment diagnostics, and stack compiler logs</p>
              </div>
              <div className="flex items-center gap-2.5">
                <button
                  onClick={handleDiagnoseLogs}
                  disabled={logsLoading || diagnosing}
                  className="text-xs font-bold bg-indigo-600 hover:bg-indigo-750 text-white px-4 py-2 rounded-xl transition-all shadow-md shadow-indigo-600/10 disabled:opacity-50"
                >
                  Diagnose with AI
                </button>
                <button
                  onClick={() => { setActiveLogsApp(null); setDiagnosing(false); }}
                  className="text-xs font-bold text-slate-600 hover:text-slate-900 px-4 py-2 rounded-xl hover:bg-slate-100 border border-slate-200 transition-all"
                >
                  Close
                </button>
              </div>
            </div>

            {/* AI diagnosis panel */}
            {diagnosing && (
              <div className="p-6 border-b border-indigo-100 bg-indigo-50/50 space-y-3.5 max-h-[35vh] overflow-y-auto">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-bold text-indigo-700 uppercase tracking-wider">AI Doctor diagnosis</h4>
                  <span className="text-[10px] font-mono font-bold bg-white text-indigo-600 border border-indigo-200 px-2 py-0.5 rounded-lg uppercase">
                    {doctorJob.status}
                  </span>
                </div>
                {(doctorJob.status === 'queued' || doctorJob.status === 'running') ? (
                  <div className="flex items-center gap-2 text-xs text-indigo-700 font-semibold">
                    <div className="w-4 h-4 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
                    Analyzing codebase build logs asynchronously…
                  </div>
                ) : doctorJob.error ? (
                  <div className="text-xs text-rose-700 bg-rose-50 p-3.5 rounded-xl border border-rose-200 flex items-start gap-2.5">
                    <ShieldAlert size={14} className="shrink-0 mt-0.5" />
                    {doctorJob.error}
                  </div>
                ) : doctorJob.result ? (
                  <div className="space-y-3 text-xs text-slate-700 leading-relaxed font-semibold">
                    <p><strong>Root Cause:</strong> {doctorJob.result.root_cause}</p>
                    <p><strong>Explanation:</strong> {doctorJob.result.explanation}</p>
                    {doctorJob.result.fix && (
                      <pre className="bg-slate-900 text-green-400 rounded-xl p-4 font-mono text-[11px] whitespace-pre-wrap leading-relaxed shadow-inner border border-slate-950">
                        {doctorJob.result.fix}
                      </pre>
                    )}
                    <p className="text-slate-400 text-[10px] uppercase font-bold tracking-wider">
                      Confidence Score: <span className="font-extrabold text-indigo-650">{doctorJob.result.confidence}</span>
                    </p>
                  </div>
                ) : null}
              </div>
            )}

            {/* Log content */}
            <div className="flex-1 overflow-y-auto font-mono text-[11px] bg-slate-950 text-slate-300 p-6 leading-relaxed whitespace-pre-wrap select-text">
              {logsLoading ? (
                <div className="h-full flex items-center justify-center">
                  <div className="w-6 h-6 border-2 border-indigo-550 border-t-transparent rounded-full animate-spin" />
                </div>
              ) : logsContent}
            </div>
          </div>
        </div>
      )}

      {/* Edit Metadata Modal */}
      {editingApp && (
        <div className="fixed inset-0 bg-slate-950/40 backdrop-blur-sm flex items-center justify-center p-6 z-50 animate-fade-in">
          <div className="max-w-md w-full bg-white border border-slate-200 rounded-3xl p-6 shadow-2xl space-y-4">
            <h3 className="text-lg font-bold text-slate-900">Edit App Metadata: {editingApp.name}</h3>
            <div className="space-y-3">
              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Description</label>
                <textarea
                  value={editDesc}
                  onChange={(e) => setEditDesc(e.target.value)}
                  placeholder="Short description of your application"
                  className="w-full bg-white border border-slate-200 rounded-xl p-3 text-xs text-slate-900 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 mt-1"
                  rows={3}
                />
              </div>
              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Tags (comma-separated)</label>
                <input
                  type="text"
                  value={editTags}
                  onChange={(e) => setEditTags(e.target.value)}
                  placeholder="react, fastapi, sqlite"
                  className="w-full bg-white border border-slate-200 rounded-xl px-3 py-2 text-xs text-slate-900 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 mt-1"
                />
              </div>
            </div>
            <div className="flex gap-2 justify-end pt-2">
              <button
                onClick={handleSaveMetadata}
                disabled={savingMeta}
                className="text-xs font-bold px-4 py-2 rounded-xl bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors shadow-md shadow-indigo-650/10"
              >
                {savingMeta ? 'Saving...' : 'Save Changes'}
              </button>
              <button
                onClick={() => setEditingApp(null)}
                className="text-xs font-bold px-4 py-2 rounded-xl border border-slate-200 text-slate-500 hover:bg-slate-50 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
export default Dashboard;
