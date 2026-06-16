import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../lib/api';
import { FileUp, GitBranch, ArrowRight, ShieldAlert, Sparkles, Zap } from 'lucide-react';
import { useAIJob } from '../hooks/useAIJob';

interface Template {
  slug: string;
  name: string;
  description: string;
  stack: string;
}

const inputCls =
  'w-full bg-white border border-gray-200 rounded-lg px-3 py-2.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition';

const STACK_COLORS: Record<string, string> = {
  static: 'bg-blue-50 text-blue-700 border-blue-200',
  node: 'bg-green-50 text-green-700 border-green-200',
  python: 'bg-yellow-50 text-yellow-700 border-yellow-200',
  java: 'bg-orange-50 text-orange-700 border-orange-200',
};

export const DeployPage: React.FC = () => {
  const [deployType, setDeployType] = useState<'zip' | 'git'>('zip');
  const [appName, setAppName] = useState('');
  const [gitUrl, setGitUrl] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const [templates, setTemplates] = useState<Template[]>([]);
  const [modalSlug, setModalSlug] = useState<string | null>(null);
  const [modalName, setModalName] = useState('');
  const [modalBusy, setModalBusy] = useState(false);
  const [modalError, setModalError] = useState('');

  const doctorJob = useAIJob();
  const [diagnosing, setDiagnosing] = useState(false);

  useEffect(() => {
    api.get<Template[]>('/templates').then((r) => setTemplates(r.data)).catch(() => undefined);
  }, []);

  const deployTemplate = async () => {
    if (!modalSlug || !modalName.trim()) return;
    setModalBusy(true); setModalError('');
    try {
      await api.post(`/templates/${modalSlug}/deploy`, { app_name: modalName.trim() });
      setModalSlug(null); setModalName('');
      navigate('/dashboard');
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      setModalError(e.response?.data?.detail || 'Failed to deploy template.');
    } finally { setModalBusy(false); }
  };

  const handleDiagnose = () => {
    if (!error) return;
    setDiagnosing(true);
    doctorJob.submit(`/ai/deploy-doctor/${appName || 'unknown'}`, { build_log: error });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null); setLoading(true);
    try {
      if (deployType === 'zip') {
        if (!selectedFile) throw new Error('Please select a ZIP file.');
        const fd = new FormData();
        fd.append('file', selectedFile);
        await api.post(`/deploy/upload?name=${appName}`, fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      } else {
        if (!gitUrl) throw new Error('Please enter a Git URL.');
        await api.post('/deploy/git', { name: appName, git_url: gitUrl });
      }
      navigate('/dashboard');
    } catch (err: any) {
      setError(err.response?.data?.detail || err.response?.data?.error || err.message || 'Failed to deploy app.');
    } finally { setLoading(false); }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-xl font-bold text-gray-900">Deploy Application</h1>
        <p className="text-sm text-gray-500 mt-0.5">Deploy static, Node, Python, or Java projects in seconds</p>
      </div>

      {/* Templates */}
      {templates.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-2xl p-5">
          <h2 className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-2">
            <Sparkles size={14} className="text-blue-600" /> Start from a template
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {templates.map((t) => (
              <div key={t.slug} className="border border-gray-200 hover:border-gray-300 rounded-xl p-4 flex flex-col gap-2 transition-colors">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-gray-900 text-sm">{t.name}</span>
                  <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${STACK_COLORS[t.stack] ?? 'bg-gray-100 text-gray-600 border-gray-200'}`}>
                    {t.stack}
                  </span>
                </div>
                <p className="text-xs text-gray-500 flex-1 leading-relaxed">{t.description}</p>
                <button
                  type="button"
                  onClick={() => { setModalSlug(t.slug); setModalName(''); setModalError(''); }}
                  className="text-xs font-semibold text-blue-600 hover:text-blue-700 flex items-center gap-1 mt-1"
                >
                  <Zap size={11} /> Use template
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Error + AI diagnose */}
      {error && (
        <div className="space-y-3">
          <div className="p-3.5 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm flex items-start gap-2.5">
            <ShieldAlert size={15} className="shrink-0 mt-0.5 text-red-500" />
            <div className="flex-1 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
              <span>{error}</span>
              <button
                type="button"
                onClick={handleDiagnose}
                disabled={diagnosing}
                className="text-xs font-semibold bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded-lg shrink-0 disabled:opacity-50 transition-colors"
              >
                {diagnosing ? 'Diagnosing…' : 'Diagnose with AI'}
              </button>
            </div>
          </div>
          {diagnosing && (
            <div className="bg-white border border-gray-200 rounded-xl p-4 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-blue-700 uppercase tracking-wider">AI Doctor</span>
                <span className="text-[10px] font-mono bg-gray-100 text-gray-600 px-2 py-0.5 rounded uppercase">{doctorJob.status}</span>
              </div>
              {(doctorJob.status === 'queued' || doctorJob.status === 'running') ? (
                <div className="flex items-center gap-2 text-xs text-gray-500">
                  <div className="w-3.5 h-3.5 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
                  Analyzing failure…
                </div>
              ) : doctorJob.error ? (
                <p className="text-xs text-red-600">{doctorJob.error}</p>
              ) : doctorJob.result ? (
                <div className="space-y-2 text-xs text-gray-700 leading-relaxed">
                  <p><strong>Root cause:</strong> {doctorJob.result.root_cause}</p>
                  <p><strong>Explanation:</strong> {doctorJob.result.explanation}</p>
                  {doctorJob.result.fix && (
                    <pre className="bg-gray-950 text-green-400 rounded-lg p-3 font-mono text-[11px] whitespace-pre-wrap">
                      {doctorJob.result.fix}
                    </pre>
                  )}
                </div>
              ) : null}
            </div>
          )}
        </div>
      )}

      {/* Deploy form */}
      <div className="bg-white border border-gray-200 rounded-2xl p-5 space-y-5">
        <h2 className="text-sm font-semibold text-gray-900">Deploy your project</h2>

        {/* Type toggle */}
        <div className="flex gap-1 p-1 bg-gray-100 rounded-lg">
          {(['zip', 'git'] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setDeployType(t)}
              className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-md text-sm font-medium transition-colors ${
                deployType === t ? 'bg-white text-gray-900 shadow-sm border border-gray-200' : 'text-gray-500 hover:text-gray-800'
              }`}
            >
              {t === 'zip' ? <FileUp size={14} /> : <GitBranch size={14} />}
              {t === 'zip' ? 'Upload ZIP' : 'Git repository'}
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-gray-700 mb-1.5">Application name</label>
            <input
              type="text"
              required
              pattern="[a-z0-9\-]{3,40}"
              value={appName}
              onChange={(e) => setAppName(e.target.value)}
              placeholder="my-awesome-app"
              className={inputCls}
            />
            <p className="text-[11px] text-gray-400 mt-1">3–40 chars · lowercase letters, numbers, hyphens</p>
          </div>

          {deployType === 'zip' ? (
            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1.5">ZIP archive</label>
              <label className="relative flex flex-col items-center justify-center border-2 border-dashed border-gray-200 hover:border-blue-400 rounded-xl p-8 cursor-pointer transition-colors bg-gray-50 hover:bg-blue-50 group">
                <input type="file" accept=".zip" required onChange={e => { if (e.target.files?.[0]) setSelectedFile(e.target.files[0]); }}
                  className="absolute inset-0 opacity-0 cursor-pointer" />
                <FileUp size={28} className="text-gray-400 group-hover:text-blue-500 mb-2 transition-colors" />
                <p className="text-sm font-semibold text-gray-700 group-hover:text-blue-700 transition-colors">
                  {selectedFile ? selectedFile.name : 'Click or drag to upload ZIP'}
                </p>
                <p className="text-xs text-gray-400 mt-1">Max 50 MB</p>
              </label>
            </div>
          ) : (
            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1.5">Git repository URL</label>
              <input
                type="url"
                required
                value={gitUrl}
                onChange={(e) => setGitUrl(e.target.value)}
                placeholder="https://github.com/username/project.git"
                className={inputCls}
              />
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2.5 rounded-lg text-sm transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {loading ? (
              <><div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" /> Deploying…</>
            ) : (
              <>Deploy application <ArrowRight size={14} /></>
            )}
          </button>
        </form>
      </div>

      {/* Template modal */}
      {modalSlug && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white border border-gray-200 rounded-2xl p-5 w-80 space-y-4 shadow-xl">
            <h3 className="font-semibold text-gray-900">Name your app</h3>
            <input
              value={modalName}
              onChange={(e) => setModalName(e.target.value)}
              placeholder="my-new-app"
              className={inputCls}
            />
            {modalError && <p className="text-xs text-red-600">{modalError}</p>}
            <div className="flex justify-end gap-2">
              <button onClick={() => setModalSlug(null)}
                className="text-sm px-4 py-2 rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50 transition-colors">
                Cancel
              </button>
              <button onClick={deployTemplate} disabled={modalBusy}
                className="text-sm px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-semibold disabled:opacity-50 transition-colors">
                {modalBusy ? 'Deploying…' : 'Deploy'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
export default DeployPage;
