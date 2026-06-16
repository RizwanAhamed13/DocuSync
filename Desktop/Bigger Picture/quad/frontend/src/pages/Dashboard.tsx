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
  RUNNING: { label: 'Running', cls: 'bg-green-50 text-green-700 border-green-200', dot: 'bg-green-500' },
  STOPPED: { label: 'Stopped', cls: 'bg-gray-100 text-gray-600 border-gray-200', dot: 'bg-gray-400' },
  BUILDING: { label: 'Building', cls: 'bg-amber-50 text-amber-700 border-amber-200', dot: 'bg-amber-500 animate-pulse' },
  FAILED: { label: 'Failed', cls: 'bg-red-50 text-red-700 border-red-200', dot: 'bg-red-500' },
};

const APPROVAL_MAP: Record<string, { label: string; cls: string }> = {
  approved: { label: 'Approved', cls: 'bg-green-50 text-green-700 border-green-200' },
  rejected: { label: 'Rejected', cls: 'bg-red-50 text-red-700 border-red-200' },
  pending: { label: 'Pending review', cls: 'bg-amber-50 text-amber-700 border-amber-200' },
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
    try { await api.post(`/apps/${name}/start`); fetchApps(); }
    catch { alert('Failed to start.'); }
  };
  const handleStop = async (name: string) => {
    try { await api.post(`/apps/${name}/stop`); fetchApps(); }
    catch { alert('Failed to stop.'); }
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
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Your Applications</h1>
          <p className="text-sm text-gray-500 mt-0.5">Manage deployments, logs, and app lifecycle</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={fetchApps}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-gray-600 hover:text-gray-900 bg-white border border-gray-200 hover:border-gray-300 rounded-lg px-3 py-2 transition-colors"
          >
            <RefreshCw size={14} /> Refresh
          </button>
          <Link
            to="/deploy"
            className="inline-flex items-center gap-1.5 text-sm font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg px-4 py-2 transition-colors"
          >
            <Plus size={14} /> New deploy
          </Link>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: 'Total apps', value: apps.length },
          { label: 'Running', value: running, green: true },
          { label: 'Building', value: building, amber: true },
        ].map((s) => (
          <div key={s.label} className="bg-white border border-gray-200 rounded-xl p-4">
            <p className="text-xs text-gray-500 font-medium mb-1">{s.label}</p>
            <p className={`text-2xl font-bold ${s.green ? 'text-green-600' : s.amber ? 'text-amber-600' : 'text-gray-900'}`}>
              {s.value}
            </p>
          </div>
        ))}
      </div>

      {/* Apps list */}
      {loading ? (
        <div className="h-48 flex items-center justify-center">
          <div className="w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : apps.length === 0 ? (
        <div className="bg-white border border-gray-200 rounded-2xl p-16 text-center">
          <div className="w-12 h-12 rounded-xl bg-gray-100 flex items-center justify-center mx-auto mb-4">
            <Activity size={22} className="text-gray-400" />
          </div>
          <h3 className="font-semibold text-gray-900 mb-1">No apps deployed yet</h3>
          <p className="text-sm text-gray-500 mb-5">Deploy your first Node, Python, Java, or static project.</p>
          <Link
            to="/deploy"
            className="inline-flex items-center gap-1.5 text-sm font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg px-5 py-2.5 transition-colors"
          >
            <Plus size={14} /> Deploy first app
          </Link>
        </div>
      ) : (
        <div className="space-y-2">
          {apps.map((app) => {
            const st = STATUS_MAP[app.status] ?? { label: app.status, cls: 'bg-gray-100 text-gray-500 border-gray-200', dot: 'bg-gray-400' };
            const ap = app.approval_status ? APPROVAL_MAP[app.approval_status] : null;
            return (
              <div
                key={app.id}
                className="bg-white border border-gray-200 hover:border-gray-300 rounded-xl p-4 flex flex-col md:flex-row md:items-center gap-4 transition-all"
              >
                {/* Left: info */}
                <div className="flex-1 min-w-0 space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <div className={`w-2 h-2 rounded-full ${st.dot}`} />
                    <h3 className="font-semibold text-gray-900 text-sm">{app.name}</h3>
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${st.cls}`}>
                      {st.label}
                    </span>
                    {app.stack && (
                      <span className="text-xs font-mono bg-gray-100 text-gray-600 border border-gray-200 px-2 py-0.5 rounded-md">
                        {app.stack}
                      </span>
                    )}
                    {ap && (
                      <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${ap.cls}`}>
                        {ap.label}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 text-xs text-gray-500">
                    <span className="flex items-center gap-1"><Clock size={11} /> {new Date(app.created_at).toLocaleDateString()}</span>
                    <span className="flex items-center gap-1"><Eye size={11} /> {app.view_count}</span>
                    <span className="flex items-center gap-1"><ThumbsUp size={11} /> {app.upvote_count}</span>
                  </div>
                  {app.status === 'RUNNING' && (
                    <a
                      href={`http://${app.name}.quad.localhost:8000`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700 font-medium"
                    >
                      Visit app <ExternalLink size={10} />
                    </a>
                  )}
                </div>

                {/* Right: actions */}
                <div className="flex items-center gap-1.5 shrink-0">
                  <Link
                    to={`/ai/${app.name}`}
                    className="p-2 rounded-lg text-gray-500 hover:text-blue-600 hover:bg-blue-50 border border-gray-200 hover:border-blue-200 transition-colors"
                    title="AI Studio"
                  >
                    <MessageSquare size={15} />
                  </Link>
                  <button
                    onClick={() => fetchLogs(app.name)}
                    className="p-2 rounded-lg text-gray-500 hover:text-gray-900 hover:bg-gray-100 border border-gray-200 transition-colors"
                    title="Build logs"
                  >
                    <Terminal size={15} />
                  </button>
                  {app.status === 'RUNNING' ? (
                    <button
                      onClick={() => handleStop(app.name)}
                      className="p-2 rounded-lg text-red-500 hover:bg-red-50 border border-gray-200 hover:border-red-200 transition-colors"
                      title="Stop"
                    >
                      <Square size={15} />
                    </button>
                  ) : (
                    <button
                      onClick={() => handleStart(app.name)}
                      disabled={app.status === 'BUILDING'}
                      className="p-2 rounded-lg text-green-600 hover:bg-green-50 border border-gray-200 hover:border-green-200 transition-colors disabled:opacity-40"
                      title="Start"
                    >
                      <Play size={15} />
                    </button>
                  )}
                  <button
                    onClick={() => handleDelete(app.name)}
                    className="p-2 rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50 border border-gray-200 hover:border-red-200 transition-colors"
                    title="Delete"
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
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center p-6 z-50">
          <div className="max-w-3xl w-full bg-white border border-gray-200 rounded-2xl overflow-hidden flex flex-col h-[75vh] shadow-2xl">
            {/* Modal header */}
            <div className="px-5 py-4 border-b border-gray-200 flex justify-between items-center">
              <div>
                <h3 className="font-semibold text-gray-900">Logs — {activeLogsApp}</h3>
                <p className="text-xs text-gray-500 mt-0.5">Build output and compiler logs</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleDiagnoseLogs}
                  disabled={logsLoading || diagnosing}
                  className="text-xs font-semibold bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded-lg transition-colors disabled:opacity-40"
                >
                  Diagnose with AI
                </button>
                <button
                  onClick={() => { setActiveLogsApp(null); setDiagnosing(false); }}
                  className="text-sm text-gray-500 hover:text-gray-900 px-3 py-1.5 rounded-lg hover:bg-gray-100 transition-colors font-medium"
                >
                  Close
                </button>
              </div>
            </div>

            {/* AI diagnosis panel */}
            {diagnosing && (
              <div className="p-5 border-b border-gray-200 bg-blue-50 space-y-3 max-h-[35vh] overflow-y-auto">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-bold text-blue-700 uppercase tracking-wider">AI Deployment Diagnosis</h4>
                  <span className="text-[10px] font-mono bg-white text-gray-600 border border-gray-200 px-2 py-0.5 rounded uppercase">
                    {doctorJob.status}
                  </span>
                </div>
                {(doctorJob.status === 'queued' || doctorJob.status === 'running') ? (
                  <div className="flex items-center gap-2 text-xs text-blue-700">
                    <div className="w-3.5 h-3.5 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
                    Analyzing build log…
                  </div>
                ) : doctorJob.error ? (
                  <div className="text-xs text-red-700 bg-red-50 p-3 rounded-lg border border-red-200 flex items-start gap-2">
                    <ShieldAlert size={14} className="shrink-0" />
                    {doctorJob.error}
                  </div>
                ) : doctorJob.result ? (
                  <div className="space-y-3 text-xs text-gray-800 leading-relaxed">
                    <p><strong>Root Cause:</strong> {doctorJob.result.root_cause}</p>
                    <p><strong>Explanation:</strong> {doctorJob.result.explanation}</p>
                    {doctorJob.result.fix && (
                      <pre className="bg-white border border-gray-200 rounded-lg p-3 font-mono text-blue-700 whitespace-pre-wrap">
                        {doctorJob.result.fix}
                      </pre>
                    )}
                    <p className="text-gray-500">
                      Confidence: <span className="font-semibold uppercase text-blue-600">{doctorJob.result.confidence}</span>
                    </p>
                  </div>
                ) : null}
              </div>
            )}

            {/* Log content */}
            <div className="flex-1 overflow-y-auto font-mono text-[12px] bg-gray-950 text-gray-300 p-5 leading-relaxed whitespace-pre-wrap select-text">
              {logsLoading ? (
                <div className="h-full flex items-center justify-center">
                  <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                </div>
              ) : logsContent}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
export default Dashboard;
