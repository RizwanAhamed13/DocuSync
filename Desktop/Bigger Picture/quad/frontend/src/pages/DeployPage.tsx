import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Editor from '@monaco-editor/react';
import api from '../lib/api';
import { FileUp, GitBranch, ArrowRight, ShieldAlert, Sparkles, Zap, Eye, X, FileText } from 'lucide-react';
import { useAIJob } from '../hooks/useAIJob';

interface Template {
  slug: string;
  name: string;
  description: string;
  stack: string;
}

const inputCls =
  'w-full bg-white border border-slate-200 rounded-xl px-4 py-3 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-50 transition-all font-semibold';

const STACK_COLORS: Record<string, string> = {
  static: 'bg-indigo-50 text-indigo-700 border-indigo-200',
  node: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  python: 'bg-amber-50 text-amber-700 border-amber-200',
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

  // Template Preview states
  const [previewTemplate, setPreviewTemplate] = useState<Template | null>(null);
  const [previewFiles, setPreviewFiles] = useState<Array<{ path: string }>>([]);
  const [selectedPreviewFile, setSelectedPreviewFile] = useState<string | null>(null);
  const [previewContent, setPreviewContent] = useState<string>('');
  const [previewLoading, setPreviewLoading] = useState<boolean>(false);
  const [previewContentLoading, setPreviewContentLoading] = useState<boolean>(false);

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

  const handleOpenPreview = async (t: Template) => {
    setPreviewTemplate(t);
    setPreviewLoading(true);
    setSelectedPreviewFile(null);
    setPreviewContent('');
    try {
      const resp = await api.get<{ files: Array<{ path: string }> }>(`/templates/${t.slug}/files`);
      setPreviewFiles(resp.data.files || []);
      if (resp.data.files && resp.data.files.length > 0) {
        const firstFile = resp.data.files[0].path;
        setSelectedPreviewFile(firstFile);
        fetchPreviewFileContent(t.slug, firstFile);
      }
    } catch (err) {
      console.error(err);
      alert('Failed to load template file structure.');
    } finally {
      setPreviewLoading(false);
    }
  };

  const fetchPreviewFileContent = async (slug: string, path: string) => {
    setPreviewContentLoading(true);
    try {
      const resp = await api.get<{ content: string }>(`/templates/${slug}/file?path=${encodeURIComponent(path)}`);
      setPreviewContent(resp.data.content || '');
    } catch (err) {
      console.error(err);
      setPreviewContent('// Failed to load file content.');
    } finally {
      setPreviewContentLoading(false);
    }
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
    <div className="max-w-2xl mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-black text-slate-900 tracking-tight">Deploy Application</h1>
        <p className="text-sm text-slate-500 mt-1 font-semibold">Deploy static, Node, Python, or Java projects in seconds</p>
      </div>

      {/* Templates */}
      {templates.length > 0 && (
        <div className="bg-white border border-slate-200/80 rounded-3xl p-6 shadow-sm">
          <h2 className="text-sm font-bold text-slate-900 mb-4 flex items-center gap-2">
            <Sparkles size={16} className="text-indigo-600" /> Start from a template
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {templates.map((t) => (
              <div key={t.slug} className="border border-slate-200 hover:border-indigo-200 rounded-2xl p-5 flex flex-col gap-3.5 transition-colors bg-slate-50/20">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-slate-900 text-sm">{t.name}</span>
                  <span className={`text-[10px] font-bold px-2.5 py-0.5 rounded-full border ${STACK_COLORS[t.stack] ?? 'bg-slate-100 text-slate-600 border-slate-200'}`}>
                    {t.stack}
                  </span>
                </div>
                <p className="text-xs text-slate-500 flex-1 leading-relaxed font-semibold">{t.description}</p>
                <div className="flex gap-4 mt-1">
                  <button
                    type="button"
                    onClick={() => { setModalSlug(t.slug); setModalName(''); setModalError(''); }}
                    className="text-xs font-bold text-indigo-600 hover:text-indigo-700 flex items-center gap-1 text-left w-fit"
                  >
                    <Zap size={12} className="fill-indigo-600/10" /> Use template
                  </button>
                  <button
                    type="button"
                    onClick={() => handleOpenPreview(t)}
                    className="text-xs font-bold text-slate-500 hover:text-slate-700 flex items-center gap-1 text-left w-fit"
                  >
                    <Eye size={12} /> Preview code
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Error + AI diagnose */}
      {error && (
        <div className="space-y-3">
          <div className="p-4 rounded-2xl bg-rose-50 border border-rose-200 text-rose-700 text-sm flex items-start gap-3">
            <ShieldAlert size={16} className="shrink-0 mt-0.5 text-rose-500" />
            <div className="flex-1 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
              <span className="font-semibold">{error}</span>
              <button
                type="button"
                onClick={handleDiagnose}
                disabled={diagnosing}
                className="text-xs font-bold bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-xl shrink-0 disabled:opacity-50 transition-colors shadow-sm"
              >
                {diagnosing ? 'Diagnosing…' : 'Diagnose with AI'}
              </button>
            </div>
          </div>
          {diagnosing && (
            <div className="bg-white border border-slate-200 rounded-2xl p-5 space-y-3.5 shadow-md">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-indigo-700 uppercase tracking-wider">AI Doctor diagnosis</span>
                <span className="text-[10px] font-mono font-bold bg-slate-100 text-slate-600 px-2.5 py-0.5 rounded-lg uppercase">{doctorJob.status}</span>
              </div>
              {(doctorJob.status === 'queued' || doctorJob.status === 'running') ? (
                <div className="flex items-center gap-2 text-xs text-slate-400 font-semibold">
                  <div className="w-3.5 h-3.5 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
                  Analyzing failure logs asynchronously…
                </div>
              ) : doctorJob.error ? (
                <p className="text-xs text-rose-600 font-semibold">{doctorJob.error}</p>
              ) : doctorJob.result ? (
                <div className="space-y-3 text-xs text-slate-700 leading-relaxed font-semibold">
                  <p><strong>Root cause:</strong> {doctorJob.result.root_cause}</p>
                  <p><strong>Explanation:</strong> {doctorJob.result.explanation}</p>
                  {doctorJob.result.fix && (
                    <pre className="bg-slate-950 text-emerald-400 rounded-xl p-4 font-mono text-[11px] whitespace-pre-wrap leading-relaxed shadow-inner">
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
      <div className="bg-white border border-slate-200/80 rounded-3xl p-6 space-y-6 shadow-sm">
        <h2 className="text-sm font-bold text-slate-900">Configure Deployment Source</h2>

        {/* Type toggle */}
        <div className="flex gap-1.5 p-1.5 bg-slate-100/80 rounded-2xl">
          {(['zip', 'git'] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setDeployType(t)}
              className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-bold transition-all ${
                deployType === t ? 'bg-white text-slate-900 shadow-sm border border-slate-200' : 'text-slate-500 hover:text-slate-800'
              }`}
            >
              {t === 'zip' ? <FileUp size={15} /> : <GitBranch size={15} />}
              {t === 'zip' ? 'Upload ZIP' : 'Git repository'}
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-2">Application name</label>
            <input
              type="text"
              required
              pattern="[a-z0-9\-]{3,40}"
              value={appName}
              onChange={(e) => setAppName(e.target.value)}
              placeholder="my-awesome-app"
              className={inputCls}
            />
            <p className="text-[11px] text-slate-400 mt-1.5 font-semibold">3–40 characters · lowercase letters, numbers, and hyphens only</p>
          </div>

          {deployType === 'zip' ? (
            <div>
              <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-2">ZIP archive</label>
              <label className="relative flex flex-col items-center justify-center border-2 border-dashed border-slate-200 hover:border-indigo-400 rounded-2xl p-10 cursor-pointer transition-all bg-slate-50/50 hover:bg-indigo-50/50 group">
                <input type="file" accept=".zip" required onChange={e => { if (e.target.files?.[0]) setSelectedFile(e.target.files[0]); }}
                  className="absolute inset-0 opacity-0 cursor-pointer" />
                <FileUp size={32} className="text-slate-400 group-hover:text-indigo-600 mb-3 transition-colors" />
                <p className="text-sm font-bold text-slate-700 group-hover:text-indigo-800 transition-colors">
                  {selectedFile ? selectedFile.name : 'Click or drag to upload ZIP archive'}
                </p>
                <p className="text-xs text-slate-400 mt-1.5 font-semibold">Maximum file upload size: 50 MB</p>
              </label>
            </div>
          ) : (
            <div>
              <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-2">Git repository URL</label>
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
            className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-3 rounded-xl text-sm transition-all disabled:opacity-50 flex items-center justify-center gap-2 shadow-md shadow-indigo-600/10 hover:shadow-indigo-600/25 hover:-translate-y-0.5"
          >
            {loading ? (
              <><div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" /> Deploying App…</>
            ) : (
              <>Deploy Application <ArrowRight size={14} /></>
            )}
          </button>
        </form>
      </div>

      {/* Template Name Confirmation Modal */}
      {modalSlug && (
        <div className="fixed inset-0 bg-slate-950/40 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-white border border-slate-200 rounded-3xl p-6 w-96 space-y-4.5 shadow-2xl">
            <div>
              <h3 className="font-extrabold text-slate-900 text-base">Name your app</h3>
              <p className="text-xs text-slate-400 mt-0.5 font-semibold">Enter a unique identifier for the template deployment</p>
            </div>
            <input
              value={modalName}
              onChange={(e) => setModalName(e.target.value)}
              placeholder="my-new-app"
              className={inputCls}
            />
            {modalError && <p className="text-xs text-rose-600 font-semibold">{modalError}</p>}
            <div className="flex justify-end gap-3.5 pt-1">
              <button onClick={() => setModalSlug(null)}
                className="text-xs font-bold px-4 py-2.5 rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50 transition-colors">
                Cancel
              </button>
              <button onClick={deployTemplate} disabled={modalBusy}
                className="text-xs font-bold px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white disabled:opacity-50 transition-colors">
                {modalBusy ? 'Deploying…' : 'Deploy'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Template Preview Modal */}
      {previewTemplate && (
        <div className="fixed inset-0 bg-slate-950/40 backdrop-blur-sm flex items-center justify-center z-50 p-4 animate-fade-in">
          <div className="bg-white border border-slate-200 rounded-3xl w-full max-w-5xl h-[80vh] flex flex-col shadow-2xl overflow-hidden">
            {/* Modal Header */}
            <div className="px-6 py-4.5 border-b border-slate-100 flex justify-between items-center bg-slate-50/50">
              <div>
                <h3 className="font-extrabold text-slate-900 text-base">Template Preview: {previewTemplate.name}</h3>
                <p className="text-xs text-slate-500 mt-0.5 font-semibold">{previewTemplate.description}</p>
              </div>
              <button 
                onClick={() => setPreviewTemplate(null)}
                className="p-1.5 hover:bg-slate-100 rounded-lg text-slate-400 hover:text-slate-700 transition-colors"
              >
                <X size={18} />
              </button>
            </div>

            {/* Modal Body */}
            <div className="flex-1 flex min-h-0">
              {/* Left pane: File structure */}
              <div className="w-64 border-r border-slate-100 bg-slate-50/30 overflow-y-auto">
                <div className="px-4 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-wider border-b border-slate-100">
                  Template Files
                </div>
                {previewLoading ? (
                  <div className="p-4 text-xs text-slate-400 font-semibold">Loading file list...</div>
                ) : previewFiles.length === 0 ? (
                  <div className="p-4 text-xs text-slate-400 font-semibold">No files found.</div>
                ) : (
                  <div className="py-1">
                    {previewFiles.map((file) => (
                      <button
                        key={file.path}
                        onClick={() => {
                          setSelectedPreviewFile(file.path);
                          fetchPreviewFileContent(previewTemplate.slug, file.path);
                        }}
                        className={`w-full text-left flex items-center gap-2 px-4 py-2.5 text-xs truncate transition-colors ${
                          selectedPreviewFile === file.path
                            ? 'bg-indigo-50 text-indigo-700 font-bold border-r-2 border-indigo-600'
                            : 'text-slate-600 hover:bg-slate-100/50 hover:text-slate-950'
                        }`}
                      >
                        <FileText size={14} className="text-slate-400 shrink-0" />
                        <span className="truncate">{file.path}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Right pane: Editor */}
              <div className="flex-1 flex flex-col min-h-0 bg-white">
                <div className="px-4 py-2 bg-slate-50/50 border-b border-slate-100 flex items-center justify-between text-xs text-slate-500 font-semibold">
                  <span className="truncate">{selectedPreviewFile || 'Select a file'}</span>
                </div>
                <div className="flex-1 min-h-0">
                  {previewContentLoading ? (
                    <div className="h-full flex items-center justify-center text-xs text-slate-400 font-semibold bg-white">
                      Loading file contents...
                    </div>
                  ) : (
                    <Editor
                      height="100%"
                      theme="vs"
                      language={
                        selectedPreviewFile 
                          ? (selectedPreviewFile.endsWith('.py') 
                              ? 'python' 
                              : selectedPreviewFile.endsWith('.json') 
                                ? 'json' 
                                : (selectedPreviewFile.endsWith('.js') || selectedPreviewFile.endsWith('.jsx'))
                                  ? 'javascript' 
                                  : selectedPreviewFile.endsWith('.html')
                                    ? 'html'
                                    : selectedPreviewFile.endsWith('.css')
                                      ? 'css'
                                      : 'plaintext') 
                          : 'plaintext'
                      }
                      value={previewContent}
                      options={{ readOnly: true, minimap: { enabled: false }, fontSize: 13 }}
                    />
                  )}
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-3.5 border-t border-slate-100 flex justify-end gap-3 bg-slate-50/50">
              <button 
                onClick={() => setPreviewTemplate(null)}
                className="text-xs font-bold px-4 py-2.5 rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50 transition-colors"
              >
                Close Preview
              </button>
              <button 
                onClick={() => {
                  const slug = previewTemplate.slug;
                  setPreviewTemplate(null);
                  setModalSlug(slug);
                  setModalName('');
                  setModalError('');
                }}
                className="text-xs font-bold px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white shadow-md shadow-indigo-650/10"
              >
                Use Template to Deploy
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default DeployPage;
