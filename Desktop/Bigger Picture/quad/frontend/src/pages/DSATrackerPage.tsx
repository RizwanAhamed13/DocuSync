import React, { useEffect, useRef, useMemo, useState, useCallback } from 'react';
import Editor from '@monaco-editor/react';
import { useAuth } from '../lib/auth';
import api from '../lib/api';
import { useDSARunner } from '../lib/useDSARunner';
import { Play, CheckCircle2, XCircle, Check, Plus, Trash2, ChevronDown, ChevronUp, X, Lightbulb, BookOpen, StickyNote, Timer, TerminalSquare, Sparkles, Cpu } from 'lucide-react';

// ── Types ─────────────────────────────────────────────────────────────────────

interface QuestionSummary {
  slug: string;
  title: string;
  difficulty: string;
  category: string;
  tags: string[];
}

interface Example {
  input: string;
  output: string;
  explanation?: string;
}

interface QuestionDetail extends QuestionSummary {
  description: string;
  examples: Example[];
  constraints: string;
  hints: string[];
  editorial: string;
  starter_code_python: string;
  starter_code_js: string;
  starter_code_ts: string;
  starter_code_java: string;
  starter_code_cpp: string;
  starter_code_go: string;
}

interface TestResult {
  input: unknown;
  expected: unknown;
  actual: unknown;
  passed: boolean;
}

interface RunResponse {
  passed: number;
  total: number;
  results: TestResult[];
  error?: string;
  language?: string;
}

interface LangOption {
  id: string;
  label: string;
  runtime: string;
  available: boolean;
  monacoId: string;
  starterKey: keyof QuestionDetail;
}

// ── Language config ───────────────────────────────────────────────────────────

const ALL_LANGUAGES: LangOption[] = [
  { id: 'python',     label: 'Python',     runtime: 'python3', available: true, monacoId: 'python',     starterKey: 'starter_code_python' },
  { id: 'javascript', label: 'JavaScript', runtime: 'node',    available: true, monacoId: 'javascript', starterKey: 'starter_code_js' },
  { id: 'typescript', label: 'TypeScript', runtime: 'tsx',     available: true, monacoId: 'typescript', starterKey: 'starter_code_ts' },
  { id: 'java',       label: 'Java',       runtime: 'java',    available: true, monacoId: 'java',       starterKey: 'starter_code_java' },
  { id: 'cpp',        label: 'C++',        runtime: 'g++',     available: true, monacoId: 'cpp',        starterKey: 'starter_code_cpp' },
  { id: 'go',         label: 'Go',         runtime: 'go',      available: true, monacoId: 'go',         starterKey: 'starter_code_go' },
];

const DIFF_DOT: Record<string, string> = {
  Easy: 'bg-green-500',
  Medium: 'bg-yellow-500',
  Hard: 'bg-red-500',
};

const DIFF_BADGE: Record<string, string> = {
  Easy:   'bg-emerald-50 text-emerald-700 border-emerald-200',
  Medium: 'bg-amber-50 text-amber-700 border-amber-200',
  Hard:   'bg-rose-50 text-rose-700 border-rose-200',
};

// ── Add Question Modal ────────────────────────────────────────────────────────

interface TestCaseRow {
  input: string;   // JSON string, e.g. [[1,2], 9]
  expected: string; // JSON string
  is_hidden: boolean;
}

const AddQuestionModal: React.FC<{ onClose: () => void; onCreated: () => void }> = ({ onClose, onCreated }) => {
  const [form, setForm] = useState({
    slug: '', title: '', difficulty: 'Easy', category: '', description: '',
    constraints: '', tags: '',
    starter_code_python: 'def solve(*args):\n    pass\n',
    starter_code_js: 'function solve(...args) {\n  \n}\n',
    starter_code_ts: 'function solve(...args: any[]): any {\n  \n}\n',
    starter_code_java: 'static Object solve(Object... args) {\n    return null;\n}',
    starter_code_cpp: 'auto solve(auto&&... args) {\n    return 0;\n}',
    starter_code_go: 'func solve(args ...interface{}) interface{} {\n    return nil\n}',
  });
  const [testCases, setTestCases] = useState<TestCaseRow[]>([
    { input: '[]', expected: 'null', is_hidden: false },
  ]);
  const [starterTab, setStarterTab] = useState('python');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [aiGenerating, setAiGenerating] = useState(false);

  const validate = () => {
    const e: Record<string, string> = {};
    if (!form.slug.trim()) e.slug = 'Required';
    else if (!/^[a-z0-9-]+$/.test(form.slug)) e.slug = 'Lowercase letters, digits, hyphens only';
    if (!form.title.trim()) e.title = 'Required';
    if (!form.category.trim()) e.category = 'Required';
    if (form.description.length < 10) e.description = 'At least 10 characters';
    testCases.forEach((tc, i) => {
      try { JSON.parse(tc.input); } catch { e[`tc_input_${i}`] = 'Invalid JSON'; }
      try { JSON.parse(tc.expected); } catch { e[`tc_expected_${i}`] = 'Invalid JSON'; }
    });
    return e;
  };

  const save = async () => {
    const e = validate();
    setErrors(e);
    if (Object.keys(e).length > 0) return;
    setSaving(true);
    try {
      await api.post('/dsa/questions', {
        ...form,
        tags: form.tags.split(',').map(t => t.trim()).filter(Boolean),
        hints: (window as any).__aiHints || [],
        editorial: (window as any).__aiEditorial || '',
        test_cases: testCases.map(tc => ({
          input: JSON.parse(tc.input),
          expected: JSON.parse(tc.expected),
          is_hidden: tc.is_hidden,
        })),
      });
      delete (window as any).__aiHints;
      delete (window as any).__aiEditorial;
      onCreated();
      onClose();
    } catch (err: any) {
      setErrors({ _form: err?.response?.data?.detail || 'Failed to create question' });
    } finally {
      setSaving(false);
    }
  };

  const aiGenerate = async () => {
    if (!form.title.trim() || !form.description.trim()) {
      setErrors({ _form: 'Fill in title and description before generating.' });
      return;
    }
    setAiGenerating(true);
    setErrors({});
    try {
      const resp = await api.post('/dsa/ai-generate', {
        title: form.title,
        description: form.description,
        difficulty: form.difficulty,
      });
      const d = resp.data;
      setForm(f => ({
        ...f,
        category: d.category || f.category,
        constraints: d.constraints || f.constraints,
        tags: Array.isArray(d.tags) ? d.tags.join(', ') : f.tags,
        starter_code_python: d.starter_code_python || f.starter_code_python,
        starter_code_js: d.starter_code_js || f.starter_code_js,
        starter_code_ts: d.starter_code_ts || f.starter_code_ts,
        starter_code_java: d.starter_code_java || f.starter_code_java,
        starter_code_cpp: d.starter_code_cpp || f.starter_code_cpp,
        starter_code_go: d.starter_code_go || f.starter_code_go,
      }));
      if (d.examples?.length) {
        // Store examples for form (not editable in current form, but we can note it)
      }
      if (Array.isArray(d.test_cases) && d.test_cases.length > 0) {
        setTestCases(d.test_cases.map((tc: any) => ({
          input: JSON.stringify(tc.input),
          expected: JSON.stringify(tc.expected),
          is_hidden: tc.is_hidden || false,
        })));
      }
      // Also prefill hints/editorial into the question payload for saving
      (window as any).__aiHints = d.hints || [];
      (window as any).__aiEditorial = d.editorial || '';
    } catch (err: any) {
      setErrors({ _form: err?.response?.data?.detail || 'AI generation failed. Check Ollama is running.' });
    } finally {
      setAiGenerating(false);
    }
  };

  const addTestCase = () => setTestCases(prev => [...prev, { input: '[]', expected: 'null', is_hidden: false }]);
  const removeTestCase = (i: number) => setTestCases(prev => prev.filter((_, idx) => idx !== i));
  const updateTC = (i: number, field: keyof TestCaseRow, value: string | boolean) =>
    setTestCases(prev => prev.map((tc, idx) => idx === i ? { ...tc, [field]: value } : tc));

  const starterLangs = [
    { id: 'python', label: 'Python', key: 'starter_code_python' },
    { id: 'javascript', label: 'JS', key: 'starter_code_js' },
    { id: 'typescript', label: 'TS', key: 'starter_code_ts' },
    { id: 'java', label: 'Java', key: 'starter_code_java' },
    { id: 'cpp', label: 'C++', key: 'starter_code_cpp' },
    { id: 'go', label: 'Go', key: 'starter_code_go' },
  ] as const;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="bg-white rounded-3xl shadow-2xl w-full max-w-3xl max-h-[92vh] flex flex-col overflow-hidden border border-slate-200">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-slate-50/50">
          <div>
            <h2 className="text-sm font-bold text-slate-800">Add New Question</h2>
            <p className="text-xs text-slate-500 font-semibold mt-0.5">All fields marked * are required</p>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-xl hover:bg-slate-100 transition-colors">
            <X className="w-4 h-4 text-slate-500" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {errors._form && (
            <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-2.5 text-xs text-red-700 font-semibold">{errors._form}</div>
          )}

          {/* Row: slug + title */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">Slug *</label>
              <input
                value={form.slug}
                onChange={e => setForm(f => ({ ...f, slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-') }))}
                placeholder="two-sum"
                className={`w-full text-xs border rounded-xl px-3 py-2 font-mono focus:outline-none focus:border-indigo-400 ${errors.slug ? 'border-red-400 bg-red-50' : 'border-slate-200'}`}
              />
              {errors.slug && <p className="text-[10px] text-red-500 mt-1 font-semibold">{errors.slug}</p>}
            </div>
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">Title *</label>
              <input
                value={form.title}
                onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
                placeholder="Two Sum"
                className={`w-full text-xs border rounded-xl px-3 py-2 focus:outline-none focus:border-indigo-400 ${errors.title ? 'border-red-400 bg-red-50' : 'border-slate-200'}`}
              />
              {errors.title && <p className="text-[10px] text-red-500 mt-1 font-semibold">{errors.title}</p>}
            </div>
          </div>

          {/* Row: difficulty + category + tags */}
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">Difficulty *</label>
              <select
                value={form.difficulty}
                onChange={e => setForm(f => ({ ...f, difficulty: e.target.value }))}
                className="w-full text-xs border border-slate-200 rounded-xl px-3 py-2 focus:outline-none focus:border-indigo-400"
              >
                <option>Easy</option>
                <option>Medium</option>
                <option>Hard</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">Category *</label>
              <input
                value={form.category}
                onChange={e => setForm(f => ({ ...f, category: e.target.value }))}
                placeholder="Arrays"
                className={`w-full text-xs border rounded-xl px-3 py-2 focus:outline-none focus:border-indigo-400 ${errors.category ? 'border-red-400 bg-red-50' : 'border-slate-200'}`}
              />
              {errors.category && <p className="text-[10px] text-red-500 mt-1 font-semibold">{errors.category}</p>}
            </div>
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">Tags (comma-separated)</label>
              <input
                value={form.tags}
                onChange={e => setForm(f => ({ ...f, tags: e.target.value }))}
                placeholder="hash-map, two-pointer"
                className="w-full text-xs border border-slate-200 rounded-xl px-3 py-2 focus:outline-none focus:border-indigo-400"
              />
            </div>
          </div>

          {/* Description */}
          <div>
            <label className="block text-xs font-bold text-slate-700 mb-1">Description *</label>
            <textarea
              value={form.description}
              onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
              rows={4}
              placeholder="Given an array of integers..."
              className={`w-full text-xs border rounded-xl px-3 py-2 resize-none focus:outline-none focus:border-indigo-400 ${errors.description ? 'border-red-400 bg-red-50' : 'border-slate-200'}`}
            />
            {errors.description && <p className="text-[10px] text-red-500 mt-1 font-semibold">{errors.description}</p>}
          </div>

          {/* Constraints */}
          <div>
            <label className="block text-xs font-bold text-slate-700 mb-1">Constraints</label>
            <input
              value={form.constraints}
              onChange={e => setForm(f => ({ ...f, constraints: e.target.value }))}
              placeholder="2 <= nums.length <= 10^4"
              className="w-full text-xs border border-slate-200 rounded-xl px-3 py-2 focus:outline-none focus:border-indigo-400"
            />
          </div>

          {/* Starter code per language */}
          <div>
            <label className="block text-xs font-bold text-slate-700 mb-2">Starter Code</label>
            <div className="border border-slate-200 rounded-2xl overflow-hidden">
              <div className="flex border-b border-slate-200 bg-slate-50/50 overflow-x-auto">
                {starterLangs.map(l => (
                  <button
                    key={l.id}
                    onClick={() => setStarterTab(l.id)}
                    className={`text-[11px] px-3 py-2 font-semibold shrink-0 transition-colors ${starterTab === l.id ? 'text-indigo-700 bg-white border-b-2 border-indigo-600' : 'text-slate-500 hover:text-slate-800'}`}
                  >
                    {l.label}
                  </button>
                ))}
              </div>
              {starterLangs.map(l => starterTab === l.id && (
                <textarea
                  key={l.id}
                  value={(form as any)[l.key]}
                  onChange={e => setForm(f => ({ ...f, [l.key]: e.target.value }))}
                  rows={5}
                  className="w-full text-xs font-mono px-4 py-3 resize-none focus:outline-none"
                />
              ))}
            </div>
          </div>

          {/* Test cases */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-bold text-slate-700">Test Cases</label>
              <button
                onClick={addTestCase}
                className="flex items-center gap-1 text-[11px] text-indigo-600 hover:text-indigo-700 font-semibold"
              >
                <Plus className="w-3 h-3" /> Add case
              </button>
            </div>
            <div className="space-y-3">
              {testCases.map((tc, i) => (
                <div key={i} className="border border-slate-200 rounded-2xl p-3 bg-slate-50/40 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-bold text-slate-500">Case #{i + 1}</span>
                    <div className="flex items-center gap-3">
                      <label className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-500 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={tc.is_hidden}
                          onChange={e => updateTC(i, 'is_hidden', e.target.checked)}
                          className="rounded"
                        />
                        Hidden
                      </label>
                      {testCases.length > 1 && (
                        <button onClick={() => removeTestCase(i)} className="text-rose-400 hover:text-rose-600">
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-[10px] font-bold text-slate-500 mb-1">Input (JSON array of args)</label>
                      <input
                        value={tc.input}
                        onChange={e => updateTC(i, 'input', e.target.value)}
                        placeholder='[[2,7,11,15], 9]'
                        className={`w-full text-xs font-mono border rounded-lg px-2.5 py-1.5 focus:outline-none ${errors[`tc_input_${i}`] ? 'border-red-400 bg-red-50' : 'border-slate-200 bg-white'}`}
                      />
                      {errors[`tc_input_${i}`] && <p className="text-[10px] text-red-500 mt-0.5 font-semibold">{errors[`tc_input_${i}`]}</p>}
                    </div>
                    <div>
                      <label className="block text-[10px] font-bold text-slate-500 mb-1">Expected (JSON)</label>
                      <input
                        value={tc.expected}
                        onChange={e => updateTC(i, 'expected', e.target.value)}
                        placeholder='[0, 1]'
                        className={`w-full text-xs font-mono border rounded-lg px-2.5 py-1.5 focus:outline-none ${errors[`tc_expected_${i}`] ? 'border-red-400 bg-red-50' : 'border-slate-200 bg-white'}`}
                      />
                      {errors[`tc_expected_${i}`] && <p className="text-[10px] text-red-500 mt-0.5 font-semibold">{errors[`tc_expected_${i}`]}</p>}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-200 bg-slate-50/50 flex items-center justify-between gap-3">
          <button
            onClick={aiGenerate}
            disabled={aiGenerating || saving}
            className="flex items-center gap-1.5 text-xs px-4 py-2 rounded-xl border border-violet-200 text-violet-700 bg-violet-50 hover:bg-violet-100 disabled:opacity-50 font-semibold transition-colors"
            title="Auto-fill test cases, hints, editorial and starter code using AI"
          >
            <Sparkles className="w-3.5 h-3.5" />
            {aiGenerating ? 'Generating...' : 'AI Auto-fill'}
          </button>
          <div className="flex gap-3">
            <button onClick={onClose} className="text-xs px-4 py-2 rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-100 font-semibold transition-colors">
              Cancel
            </button>
            <button
              onClick={save}
              disabled={saving || aiGenerating}
              className="text-xs px-5 py-2 rounded-xl bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 font-semibold shadow-sm transition-colors"
            >
              {saving ? 'Creating...' : 'Create Question'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

// ── Add Test Case Modal ───────────────────────────────────────────────────────

const AddTestCaseModal: React.FC<{ slug: string; onClose: () => void; onAdded: () => void }> = ({ slug, onClose, onAdded }) => {
  const [input, setInput] = useState('[]');
  const [expected, setExpected] = useState('null');
  const [isHidden, setIsHidden] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  const save = async () => {
    const e: Record<string, string> = {};
    try { JSON.parse(input); } catch { e.input = 'Invalid JSON'; }
    try { JSON.parse(expected); } catch { e.expected = 'Invalid JSON'; }
    setErrors(e);
    if (Object.keys(e).length > 0) return;
    setSaving(true);
    try {
      await api.post(`/dsa/questions/${slug}/test-cases`, {
        input: JSON.parse(input),
        expected: JSON.parse(expected),
        is_hidden: isHidden,
      });
      onAdded();
      onClose();
    } catch (err: any) {
      setErrors({ _form: err?.response?.data?.detail || 'Failed to add test case' });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="bg-white rounded-3xl shadow-2xl w-full max-w-md border border-slate-200">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-200 bg-slate-50/50">
          <h2 className="text-sm font-bold text-slate-800">Add Test Case</h2>
          <button onClick={onClose} className="p-1.5 rounded-xl hover:bg-slate-100"><X className="w-4 h-4 text-slate-500" /></button>
        </div>
        <div className="p-5 space-y-4">
          {errors._form && <div className="bg-red-50 border border-red-200 rounded-xl px-3 py-2 text-xs text-red-700 font-semibold">{errors._form}</div>}
          <div>
            <label className="block text-xs font-bold text-slate-700 mb-1">Input (JSON array of args)</label>
            <input value={input} onChange={e => setInput(e.target.value)} placeholder='[[2,7,11,15], 9]'
              className={`w-full text-xs font-mono border rounded-xl px-3 py-2 focus:outline-none ${errors.input ? 'border-red-400 bg-red-50' : 'border-slate-200'}`} />
            {errors.input && <p className="text-[10px] text-red-500 mt-0.5 font-semibold">{errors.input}</p>}
          </div>
          <div>
            <label className="block text-xs font-bold text-slate-700 mb-1">Expected (JSON)</label>
            <input value={expected} onChange={e => setExpected(e.target.value)} placeholder='[0, 1]'
              className={`w-full text-xs font-mono border rounded-xl px-3 py-2 focus:outline-none ${errors.expected ? 'border-red-400 bg-red-50' : 'border-slate-200'}`} />
            {errors.expected && <p className="text-[10px] text-red-500 mt-0.5 font-semibold">{errors.expected}</p>}
          </div>
          <label className="flex items-center gap-2 text-xs font-semibold text-slate-600 cursor-pointer">
            <input type="checkbox" checked={isHidden} onChange={e => setIsHidden(e.target.checked)} className="rounded" />
            Hidden test case (not shown to users)
          </label>
        </div>
        <div className="px-5 py-3 border-t border-slate-200 flex justify-end gap-2">
          <button onClick={onClose} className="text-xs px-3 py-1.5 rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-100 font-semibold">Cancel</button>
          <button onClick={save} disabled={saving} className="text-xs px-4 py-1.5 rounded-xl bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 font-semibold">
            {saving ? 'Adding...' : 'Add'}
          </button>
        </div>
      </div>
    </div>
  );
};

// ── Main page ─────────────────────────────────────────────────────────────────

export const DSATrackerPage: React.FC = () => {
  const { isAuthenticated, user } = useAuth();
  const isAdmin = (user as any)?.role === 'admin' || (user as any)?.role === 'faculty';
  const { run: runInBrowser, runCustom: runCustomInBrowser, pyodideReady, workerAvailable } = useDSARunner();

  const [questions, setQuestions] = useState<QuestionSummary[]>([]);
  const [categoryFilter, setCategoryFilter] = useState<string>('All');
  const [diffFilter, setDiffFilter] = useState<string>('All');
  const [selected, setSelected] = useState<QuestionDetail | null>(null);
  const [language, setLanguage] = useState<string>('python');
  const [availableLangs, setAvailableLangs] = useState<LangOption[]>(ALL_LANGUAGES);
  const [code, setCode] = useState('');
  const [running, setRunning] = useState(false);
  const [runResult, setRunResult] = useState<RunResponse | null>(null);
  const [solved, setSolved] = useState(false);
  const [submissions, setSubmissions] = useState<any[]>([]);
  const [showAddQuestion, setShowAddQuestion] = useState(false);
  const [showAddTC, setShowAddTC] = useState(false);
  const [testCasesExpanded, setTestCasesExpanded] = useState(false);
  const [adminTestCases, setAdminTestCases] = useState<any[]>([]);

  // Hints, editorial, notes, custom input, timer
  const [hintsRevealed, setHintsRevealed] = useState(0);
  const [showEditorial, setShowEditorial] = useState(false);
  const [note, setNote] = useState('');
  const [noteSaved, setNoteSaved] = useState(false);
  const [activeTab, setActiveTab] = useState<'description' | 'hints' | 'editorial' | 'notes' | 'custom'>('description');
  const [customInput, setCustomInput] = useState('');
  const [customResult, setCustomResult] = useState<{stdout:string;stderr:string;exit_code:number}|null>(null);
  const [customRunning, setCustomRunning] = useState(false);
  // Timer
  const [timerSeconds, setTimerSeconds] = useState(0);
  const [timerRunning, setTimerRunning] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadQuestions = useCallback(async () => {
    try {
      const resp = await api.get<QuestionSummary[]>('/dsa/questions');
      setQuestions(resp.data);
    } catch { setQuestions([]); }
  }, []);

  const fetchSubmissions = useCallback(async () => {
    if (!user) return;
    try {
      const resp = await api.get(`/dsa/submissions/${(user as any).username}`);
      setSubmissions(resp.data || []);
    } catch { /* ignore */ }
  }, [user]);

  const fetchLanguages = useCallback(async () => {
    try {
      const resp = await api.get<{ id: string; label: string; runtime: string; available: boolean }[]>('/dsa/languages');
      setAvailableLangs(ALL_LANGUAGES.map(l => ({
        ...l,
        available: resp.data.find(r => r.id === l.id)?.available ?? true,
      })));
    } catch { /* use defaults */ }
  }, []);

  useEffect(() => {
    loadQuestions();
    fetchSubmissions();
    fetchLanguages();
  }, [loadQuestions, fetchSubmissions, fetchLanguages]);

  // Timer effect
  useEffect(() => {
    if (timerRunning) {
      timerRef.current = setInterval(() => setTimerSeconds(s => s + 1), 1000);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [timerRunning]);

  const formatTime = (s: number) => {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    if (h > 0) return `${h}:${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`;
    return `${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`;
  };

  const selectQuestion = async (slug: string) => {
    try {
      const resp = await api.get<QuestionDetail>(`/dsa/questions/${slug}`);
      setSelected(resp.data);
      const lang = 'python';
      setLanguage(lang);
      setCode(resp.data.starter_code_python);
      setRunResult(null);
      setSolved(submissions.some(s => s.problem_slug === slug));
      setTestCasesExpanded(false);
      setAdminTestCases([]);
      // Reset new state
      setHintsRevealed(0);
      setShowEditorial(false);
      setActiveTab('description');
      setCustomInput('');
      setCustomResult(null);
      setNote('');
      setNoteSaved(false);
      // Reset & start timer
      setTimerSeconds(0);
      setTimerRunning(true);
      // Load user note
      if (user) {
        try {
          const nr = await api.get(`/dsa/notes/${slug}`);
          setNote(nr.data.content || '');
        } catch { /* no note yet */ }
      }
    } catch { /* ignore */ }
  };

  const changeLanguage = (lang: string) => {
    setLanguage(lang);
    if (selected) {
      const opt = ALL_LANGUAGES.find(l => l.id === lang);
      if (opt) {
        setCode((selected as any)[opt.starterKey] || '');
      }
    }
    setRunResult(null);
  };

  const runCode = async () => {
    if (!selected) return;
    setRunning(true);
    setRunResult(null);
    try {
      // Use browser runner for Python/JS/TS, server for Java/C++/Go
      const testCases = selected.test_cases?.map((tc: any) => ({
        input: tc.input,
        expected_output: tc.expected_output,
      })) || [];
      const result = await runInBrowser(selected.slug, code, language, testCases);
      setRunResult(result as RunResponse);
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || 'Failed to run code.';
      setRunResult({ passed: 0, total: 0, results: [], error: typeof msg === 'string' ? msg : JSON.stringify(msg) });
    } finally {
      setRunning(false);
    }
  };

  const markSolved = async () => {
    if (!selected) return;
    try {
      await api.post('/dsa/submit', {
        problem_slug: selected.slug,
        problem_title: selected.title,
        difficulty: selected.difficulty,
      });
      setSolved(true);
      setTimerRunning(false);
      fetchSubmissions();
    } catch { setSolved(true); setTimerRunning(false); fetchSubmissions(); }
  };

  const saveNote = async () => {
    if (!selected || !user) return;
    try {
      await api.put(`/dsa/notes/${selected.slug}`, { content: note });
      setNoteSaved(true);
      setTimeout(() => setNoteSaved(false), 2000);
    } catch { /* ignore */ }
  };

  const runCustomCode = async () => {
    if (!selected) return;
    setCustomRunning(true);
    setCustomResult(null);
    try {
      const result = await runCustomInBrowser(code, language, customInput);
      setCustomResult(result);
    } catch (err: any) {
      setCustomResult({ stdout: '', stderr: err?.response?.data?.detail || err?.message || 'Error', exit_code: 1 });
    } finally {
      setCustomRunning(false);
    }
  };

  const loadAdminTestCases = async () => {
    if (!selected) return;
    try {
      const resp = await api.get(`/dsa/questions/${selected.slug}/test-cases`);
      setAdminTestCases(resp.data);
    } catch { /* ignore */ }
  };

  const deleteTestCase = async (tcId: number) => {
    if (!selected) return;
    if (!confirm('Delete this test case?')) return;
    try {
      await api.delete(`/dsa/questions/${selected.slug}/test-cases/${tcId}`);
      loadAdminTestCases();
    } catch { /* ignore */ }
  };

  const deleteQuestion = async () => {
    if (!selected) return;
    if (!confirm(`Delete question "${selected.title}"? This cannot be undone.`)) return;
    try {
      await api.delete(`/dsa/questions/${selected.slug}`);
      setSelected(null);
      loadQuestions();
    } catch { /* ignore */ }
  };

  const categories = useMemo(() => {
    const set = new Set(questions.map(q => q.category));
    return ['All', ...Array.from(set).sort()];
  }, [questions]);

  const grouped = useMemo(() => {
    let filtered = questions;
    if (categoryFilter !== 'All') filtered = filtered.filter(q => q.category === categoryFilter);
    if (diffFilter !== 'All') filtered = filtered.filter(q => q.difficulty === diffFilter);
    const order = ['Easy', 'Medium', 'Hard'];
    const out: Record<string, QuestionSummary[]> = { Easy: [], Medium: [], Hard: [] };
    for (const q of filtered) {
      if (!out[q.difficulty]) out[q.difficulty] = [];
      out[q.difficulty].push(q);
    }
    return order.map(d => ({ difficulty: d, items: out[d] || [] }));
  }, [questions, categoryFilter, diffFilter]);

  const currentLang = ALL_LANGUAGES.find(l => l.id === language) || ALL_LANGUAGES[0];

  // Heatmap
  const ContributionHeatmap = () => {
    const counts = useMemo(() => {
      const map: Record<string, number> = {};
      for (const s of submissions) {
        if (s.solved_at) {
          const dateStr = s.solved_at.split('T')[0];
          map[dateStr] = (map[dateStr] || 0) + 1;
        }
      }
      return map;
    }, []);

    const cells = useMemo(() => {
      const arr = [];
      const today = new Date();
      const startDate = new Date();
      startDate.setDate(today.getDate() - 83);
      for (let i = 0; i < 84; i++) {
        const d = new Date(startDate);
        d.setDate(startDate.getDate() + i);
        const dateStr = d.toISOString().split('T')[0];
        arr.push({ date: dateStr, count: counts[dateStr] || 0 });
      }
      return arr;
    }, [counts]);

    const getColor = (count: number) =>
      count === 0 ? 'bg-slate-100 border-slate-200/50' :
      count === 1 ? 'bg-emerald-100 border-emerald-200' :
      count === 2 ? 'bg-emerald-300 border-emerald-400' :
                    'bg-emerald-500 border-emerald-600';

    return (
      <div className="bg-white border border-slate-200 rounded-3xl p-6 shadow-sm space-y-4">
        <div>
          <h3 className="text-sm font-bold text-slate-800">Activity Heatmap</h3>
          <p className="text-xs text-slate-400 font-semibold mt-0.5">Solved challenges over the last 12 weeks</p>
        </div>
        <div className="grid grid-flow-col grid-rows-7 gap-1.5 w-fit">
          {cells.map((cell, idx) => (
            <div key={idx} className={`w-3 h-3 rounded border ${getColor(cell.count)}`}
              title={`${cell.count} solved on ${new Date(cell.date).toLocaleDateString()}`} />
          ))}
        </div>
        <div className="flex items-center gap-2 text-[10px] text-slate-400 font-bold uppercase">
          <span>Less</span>
          {['bg-slate-100','bg-emerald-100','bg-emerald-300','bg-emerald-500'].map((c,i) => (
            <div key={i} className={`w-2.5 h-2.5 ${c} border rounded`} />
          ))}
          <span>More</span>
        </div>
      </div>
    );
  };

  const SubmissionsTimeline = () => (
    <div className="bg-white border border-slate-200 rounded-3xl p-6 shadow-sm space-y-4">
      <div>
        <h3 className="text-sm font-bold text-slate-800">Submission History</h3>
        <p className="text-xs text-slate-400 font-semibold mt-0.5">All successfully solved questions</p>
      </div>
      {submissions.length === 0 ? (
        <p className="text-xs text-slate-400 font-semibold italic">No submissions yet.</p>
      ) : (
        <div className="relative border-l border-slate-200 ml-2 pl-5 space-y-4 max-h-[300px] overflow-y-auto pr-2">
          {submissions.map(s => (
            <div key={s.id} className="relative">
              <div className="absolute -left-[25px] top-1.5 w-2 h-2 rounded-full bg-white border border-emerald-500" />
              <div className="flex justify-between items-start gap-4">
                <div>
                  <span className="text-xs font-bold text-slate-800 block">{s.problem_title}</span>
                  <span className="text-[10px] text-slate-400 font-semibold block mt-0.5">
                    {new Date(s.solved_at).toLocaleString()}
                  </span>
                </div>
                <span className={`text-[9px] font-bold px-2 py-0.5 rounded-full border ${DIFF_BADGE[s.difficulty] || ''}`}>
                  {s.difficulty}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  return (
    <div className="flex h-[calc(100vh-84px)] bg-white border border-slate-200 rounded-3xl overflow-hidden shadow-sm">
      {/* Modals */}
      {showAddQuestion && (
        <AddQuestionModal onClose={() => setShowAddQuestion(false)} onCreated={loadQuestions} />
      )}
      {showAddTC && selected && (
        <AddTestCaseModal
          slug={selected.slug}
          onClose={() => setShowAddTC(false)}
          onAdded={loadAdminTestCases}
        />
      )}

      {/* Left panel */}
      <div className="border-r border-slate-200 bg-slate-50/50 overflow-auto flex flex-col" style={{ width: 280 }}>
        <div className="p-4 border-b border-slate-200 bg-white space-y-2">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold text-slate-800">DSA Problems</h2>
            {isAdmin && (
              <button
                onClick={() => setShowAddQuestion(true)}
                className="flex items-center gap-1 text-[11px] text-indigo-600 hover:text-indigo-700 font-semibold"
                title="Add new question"
              >
                <Plus className="w-3.5 h-3.5" /> New
              </button>
            )}
          </div>
          <select
            value={categoryFilter}
            onChange={e => setCategoryFilter(e.target.value)}
            className="w-full text-xs border border-slate-200 rounded-lg px-2.5 py-1.5 text-slate-700 bg-white focus:outline-none focus:border-indigo-500 font-semibold"
          >
            {categories.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          <div className="flex gap-1">
            {['All', 'Easy', 'Medium', 'Hard'].map(d => (
              <button
                key={d}
                onClick={() => setDiffFilter(d)}
                className={`flex-1 text-[10px] font-bold py-1 rounded-lg border transition-colors ${
                  diffFilter === d
                    ? d === 'All' ? 'bg-slate-800 text-white border-slate-800'
                    : d === 'Easy' ? 'bg-emerald-500 text-white border-emerald-500'
                    : d === 'Medium' ? 'bg-amber-500 text-white border-amber-500'
                    : 'bg-rose-500 text-white border-rose-500'
                    : 'bg-white text-slate-500 border-slate-200 hover:bg-slate-50'
                }`}
              >
                {d}
              </button>
            ))}
          </div>
        </div>
        <div className="py-2 flex-1 overflow-auto">
          {grouped.map(g => (
            <div key={g.difficulty} className="mb-4">
              {g.items.length > 0 && (
                <div className="px-4 pt-2 pb-1 text-[10px] font-bold uppercase text-slate-400 flex items-center gap-1.5">
                  <span className={`w-1.5 h-1.5 rounded-full ${DIFF_DOT[g.difficulty]}`} />
                  {g.difficulty} · {g.items.length}
                </div>
              )}
              {g.items.map(q => {
                const isSolved = submissions.some(s => s.problem_slug === q.slug);
                return (
                  <button
                    key={q.slug}
                    onClick={() => selectQuestion(q.slug)}
                    className={`w-full text-left px-4 py-2.5 text-xs transition-all ${
                      selected?.slug === q.slug
                        ? 'bg-indigo-50 text-indigo-700 font-bold border-r-2 border-indigo-600'
                        : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="flex items-center gap-2 min-w-0">
                        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${DIFF_DOT[g.difficulty]}`} />
                        <span className="truncate">{q.title}</span>
                      </span>
                      {isSolved && <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />}
                    </div>
                    {q.tags?.length > 0 && (
                      <div className="flex gap-1 mt-1 ml-3.5 flex-wrap">
                        {q.tags.slice(0, 2).map(t => (
                          <span key={t} className="text-[9px] font-semibold bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded">{t}</span>
                        ))}
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          ))}
          {grouped.every(g => g.items.length === 0) && (
            <div className="px-4 py-8 text-center text-xs text-slate-400 font-semibold">No questions match filters</div>
          )}
        </div>
      </div>

      {/* Right panel */}
      <div className="flex-1 flex flex-col min-w-0 bg-white">
        {!selected ? (
          <div className="flex-1 overflow-y-auto p-8 bg-slate-50/20 space-y-6">
            <div className="bg-gradient-to-r from-indigo-50 to-indigo-100/50 border border-indigo-100 rounded-3xl p-6 shadow-sm">
              <h2 className="text-lg font-black text-indigo-950">DSA Tracker</h2>
              <p className="text-xs text-indigo-700 font-semibold mt-1 max-w-lg leading-relaxed">
                Choose a challenge from the left. Code in Python, JavaScript, TypeScript, Java, C++, or Go — run test cases and track your streak!
              </p>
              <div className="flex gap-2 mt-3 flex-wrap">
                {availableLangs.map(l => (
                  <span key={l.id} className={`text-[10px] font-bold px-2 py-1 rounded-lg border ${l.available ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-slate-50 text-slate-400 border-slate-200 line-through'}`}>
                    {l.label}
                  </span>
                ))}
              </div>
            </div>
            <ContributionHeatmap />
            <SubmissionsTimeline />
          </div>
        ) : (
          <div className="flex flex-col flex-1 min-h-0">
            {/* Problem panel — tabbed */}
            <div className="flex flex-col border-b border-slate-200 bg-white" style={{maxHeight: 300}}>
              {/* Title + timer row */}
              <div className="flex items-center justify-between gap-2 px-5 pt-4 pb-2 flex-wrap">
                <div className="flex items-center gap-2 flex-wrap min-w-0">
                  <span className={`w-2 h-2 rounded-full shrink-0 ${DIFF_DOT[selected.difficulty]}`} />
                  <h1 className="text-sm font-bold text-slate-800 truncate">{selected.title}</h1>
                  <span className="text-xs text-slate-400 font-semibold bg-slate-100 px-2 py-0.5 rounded-full shrink-0">{selected.category}</span>
                  <span className={`text-[9px] font-bold px-2 py-0.5 rounded-full border shrink-0 ${DIFF_BADGE[selected.difficulty]}`}>{selected.difficulty}</span>
                  {selected.tags?.map(t => (
                    <span key={t} className="text-[9px] font-semibold bg-indigo-50 text-indigo-600 border border-indigo-100 px-1.5 py-0.5 rounded shrink-0">{t}</span>
                  ))}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {/* Timer */}
                  <button
                    onClick={() => setTimerRunning(r => !r)}
                    className={`flex items-center gap-1 text-[11px] font-mono font-bold px-2.5 py-1 rounded-lg border transition-colors ${timerRunning ? 'bg-indigo-50 text-indigo-700 border-indigo-200' : 'bg-slate-50 text-slate-500 border-slate-200'}`}
                    title={timerRunning ? 'Pause timer' : 'Start timer'}
                  >
                    <Timer className="w-3 h-3" />
                    {formatTime(timerSeconds)}
                  </button>
                  {isAdmin && (
                    <button onClick={deleteQuestion} className="text-[10px] text-rose-500 hover:text-rose-700 font-semibold flex items-center gap-1">
                      <Trash2 className="w-3 h-3" /> Delete
                    </button>
                  )}
                </div>
              </div>

              {/* Tabs */}
              <div className="flex border-b border-slate-100 px-5 overflow-x-auto">
                {[
                  { id: 'description', label: 'Problem', icon: null },
                  { id: 'hints', label: `Hints${selected.hints?.length ? ` (${selected.hints.length})` : ''}`, icon: Lightbulb },
                  { id: 'editorial', label: 'Editorial', icon: BookOpen },
                  { id: 'custom', label: 'Custom Test', icon: TerminalSquare },
                  ...(isAuthenticated ? [{ id: 'notes', label: 'Notes', icon: StickyNote }] : []),
                ].map(tab => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id as any)}
                    className={`flex items-center gap-1.5 text-[11px] font-semibold px-3 py-2 border-b-2 transition-colors shrink-0 ${
                      activeTab === tab.id
                        ? 'border-indigo-600 text-indigo-700'
                        : 'border-transparent text-slate-500 hover:text-slate-700'
                    }`}
                  >
                    {tab.icon && <tab.icon className="w-3 h-3" />}
                    {tab.label}
                  </button>
                ))}
              </div>

              {/* Tab content */}
              <div className="flex-1 overflow-auto p-5 text-xs">
                {activeTab === 'description' && (
                  <div className="space-y-3">
                    <p className="text-slate-700 leading-relaxed">{selected.description}</p>
                    {selected.examples.map((ex, i) => (
                      <div key={i} className="bg-slate-50 border border-slate-200 rounded-xl p-3 space-y-1">
                        <p className="text-slate-800"><span className="font-bold text-slate-600">Input:</span> {ex.input}</p>
                        <p className="text-slate-800"><span className="font-bold text-slate-600">Output:</span> {ex.output}</p>
                        {ex.explanation && <p className="text-slate-500 italic">{ex.explanation}</p>}
                      </div>
                    ))}
                    {selected.constraints && (
                      <p className="text-slate-500">
                        <span className="font-bold text-slate-600">Constraints:</span> {selected.constraints}
                      </p>
                    )}
                  </div>
                )}

                {activeTab === 'hints' && (
                  <div className="space-y-3">
                    {!selected.hints?.length ? (
                      <p className="text-slate-400 italic">No hints available for this problem.</p>
                    ) : (
                      <>
                        {selected.hints.slice(0, hintsRevealed).map((h, i) => (
                          <div key={i} className="bg-amber-50 border border-amber-200 rounded-xl p-3">
                            <span className="text-[10px] font-bold text-amber-600 uppercase tracking-wider block mb-1">Hint {i + 1}</span>
                            <p className="text-slate-700">{h}</p>
                          </div>
                        ))}
                        {hintsRevealed < (selected.hints?.length || 0) ? (
                          <button
                            onClick={() => setHintsRevealed(n => n + 1)}
                            className="flex items-center gap-1.5 text-xs text-amber-600 hover:text-amber-800 font-semibold border border-amber-200 bg-amber-50 rounded-xl px-4 py-2 transition-colors"
                          >
                            <Lightbulb className="w-3.5 h-3.5" />
                            {hintsRevealed === 0 ? 'Show first hint' : `Show hint ${hintsRevealed + 1} of ${selected.hints.length}`}
                          </button>
                        ) : (
                          <p className="text-[11px] text-slate-400 font-semibold italic">All hints revealed.</p>
                        )}
                      </>
                    )}
                  </div>
                )}

                {activeTab === 'editorial' && (
                  <div>
                    {!solved && !isAdmin ? (
                      <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 text-center space-y-2">
                        <BookOpen className="w-6 h-6 text-slate-300 mx-auto" />
                        <p className="text-slate-500 font-semibold">Mark the problem as solved to unlock the editorial.</p>
                      </div>
                    ) : !selected.editorial ? (
                      <p className="text-slate-400 italic">No editorial written for this problem yet.</p>
                    ) : (
                      <div className="prose prose-sm max-w-none">
                        <pre className="whitespace-pre-wrap text-slate-700 leading-relaxed font-sans">{selected.editorial}</pre>
                      </div>
                    )}
                  </div>
                )}

                {activeTab === 'custom' && (
                  <div className="space-y-3">
                    <div>
                      <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1.5">Custom stdin (optional)</label>
                      <textarea
                        value={customInput}
                        onChange={e => setCustomInput(e.target.value)}
                        rows={3}
                        placeholder="Type custom input here..."
                        className="w-full text-xs font-mono border border-slate-200 rounded-xl px-3 py-2 resize-none focus:outline-none focus:border-indigo-400"
                      />
                    </div>
                    <button
                      onClick={runCustomCode}
                      disabled={customRunning}
                      className="flex items-center gap-1.5 text-xs px-4 py-2 rounded-xl bg-slate-800 text-white hover:bg-slate-900 disabled:opacity-50 font-semibold transition-colors"
                    >
                      <TerminalSquare className="w-3.5 h-3.5" />
                      {customRunning ? 'Running...' : 'Run with custom input'}
                    </button>
                    {customResult && (
                      <div className="space-y-2">
                        {customResult.stdout && (
                          <div>
                            <p className="text-[10px] font-bold text-slate-500 uppercase mb-1">stdout</p>
                            <pre className="text-xs font-mono bg-slate-50 border border-slate-200 rounded-xl p-3 whitespace-pre-wrap text-slate-800 max-h-32 overflow-auto">{customResult.stdout}</pre>
                          </div>
                        )}
                        {customResult.stderr && (
                          <div>
                            <p className="text-[10px] font-bold text-rose-500 uppercase mb-1">stderr</p>
                            <pre className="text-xs font-mono bg-red-50 border border-red-200 rounded-xl p-3 whitespace-pre-wrap text-red-700 max-h-32 overflow-auto">{customResult.stderr}</pre>
                          </div>
                        )}
                        <p className="text-[10px] text-slate-400 font-semibold">exit code: {customResult.exit_code}</p>
                      </div>
                    )}
                  </div>
                )}

                {activeTab === 'notes' && isAuthenticated && (
                  <div className="space-y-3">
                    <textarea
                      value={note}
                      onChange={e => { setNote(e.target.value); setNoteSaved(false); }}
                      rows={6}
                      placeholder="Write your notes, approach ideas, or reminders for this problem..."
                      className="w-full text-xs border border-slate-200 rounded-xl px-3 py-2 resize-none focus:outline-none focus:border-indigo-400"
                    />
                    <button
                      onClick={saveNote}
                      className={`text-xs px-4 py-1.5 rounded-xl font-semibold transition-colors ${
                        noteSaved ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-indigo-600 text-white hover:bg-indigo-700'
                      }`}
                    >
                      {noteSaved ? '✓ Saved' : 'Save Note'}
                    </button>
                  </div>
                )}
              </div>
            </div>

            {/* Admin: test case manager */}
            {isAdmin && (
              <div className="border-b border-slate-200 bg-amber-50/40">
                <button
                  onClick={() => {
                    setTestCasesExpanded(v => !v);
                    if (!testCasesExpanded) loadAdminTestCases();
                  }}
                  className="w-full flex items-center justify-between px-5 py-2.5 text-xs font-bold text-amber-800"
                >
                  <span>Manage Test Cases ({adminTestCases.length || '?'})</span>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={e => { e.stopPropagation(); setShowAddTC(true); }}
                      className="flex items-center gap-1 text-amber-700 hover:text-amber-900 text-[11px]"
                    >
                      <Plus className="w-3 h-3" /> Add
                    </button>
                    {testCasesExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                  </div>
                </button>
                {testCasesExpanded && (
                  <div className="px-5 pb-3 max-h-40 overflow-auto space-y-1.5">
                    {adminTestCases.length === 0 ? (
                      <p className="text-xs text-amber-600 font-semibold italic">No test cases yet.</p>
                    ) : adminTestCases.map((tc, i) => (
                      <div key={tc.id} className="flex items-center justify-between text-xs bg-white border border-amber-100 rounded-lg px-3 py-1.5">
                        <span className="font-mono text-slate-700 truncate flex-1">
                          #{i + 1} {tc.is_hidden ? '🔒 ' : ''}in:{JSON.stringify(tc.input)} → {JSON.stringify(tc.expected_output)}
                        </span>
                        <button onClick={() => deleteTestCase(tc.id)} className="ml-2 text-rose-400 hover:text-rose-600 shrink-0">
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Editor toolbar */}
            <div className="h-12 border-b border-slate-200 bg-slate-50/50 flex items-center justify-between px-4 gap-3">
              {/* Language selector */}
              {/* Pyodide status chip */}
              <div className="flex gap-1 overflow-x-auto">
                {workerAvailable && (
                  <span className={`text-[10px] font-bold px-2 py-1 rounded-lg border shrink-0 ${
                    pyodideReady
                      ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                      : 'bg-amber-50 text-amber-700 border-amber-200'
                  }`} title={pyodideReady ? 'Python runs in your browser (no server cost)' : 'Loading Python runtime...'}>
                    <Cpu className="w-2.5 h-2.5 inline mr-1" />
                    {pyodideReady ? 'JS/Py: browser' : 'loading...'}
                  </span>
                )}
                {availableLangs.map(l => (
                  <button
                    key={l.id}
                    onClick={() => l.available && changeLanguage(l.id)}
                    title={l.available ? l.label : `${l.label} — ${l.runtime} not installed`}
                    className={`text-[11px] px-2.5 py-1 rounded-lg border font-semibold transition-colors shrink-0 ${
                      !l.available
                        ? 'opacity-40 cursor-not-allowed border-slate-200 text-slate-400 bg-white'
                        : language === l.id
                        ? 'border-indigo-200 text-indigo-700 bg-indigo-50 shadow-sm'
                        : 'border-slate-200 text-slate-500 bg-white hover:bg-slate-50'
                    }`}
                  >
                    {l.label}
                  </button>
                ))}
              </div>
              <div className="flex gap-2 shrink-0">
                <button
                  onClick={runCode}
                  disabled={running}
                  className="flex items-center gap-1.5 text-xs px-4 py-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 font-semibold shadow-sm transition-colors"
                >
                  <Play className="w-3.5 h-3.5" /> {running ? 'Running...' : 'Run'}
                </button>
                {isAuthenticated && (
                  <button
                    onClick={markSolved}
                    disabled={solved}
                    className="flex items-center gap-1.5 text-xs px-4 py-1.5 rounded-lg border border-emerald-200 text-emerald-600 hover:bg-emerald-50 bg-white disabled:opacity-50 font-semibold transition-colors"
                  >
                    <Check className="w-3.5 h-3.5" /> {solved ? 'Solved' : 'Mark Solved'}
                  </button>
                )}
              </div>
            </div>

            {/* Monaco editor */}
            <div className="flex-1 min-h-0">
              <Editor
                height="100%"
                language={currentLang.monacoId}
                value={code}
                onChange={v => setCode(v ?? '')}
                theme="vs"
                options={{ minimap: { enabled: false }, fontSize: 13 }}
              />
            </div>

            {/* Results */}
            {runResult && (
              <div className="border-t border-slate-200 bg-slate-50/50 max-h-52 overflow-auto p-4">
                {runResult.error ? (
                  <pre className="text-xs text-red-600 whitespace-pre-wrap font-mono p-3 bg-red-50 border border-red-200 rounded-xl">{runResult.error}</pre>
                ) : (
                  <>
                    <p className={`text-xs font-bold mb-2.5 ${runResult.passed === runResult.total ? 'text-emerald-700' : 'text-slate-700'}`}>
                      {runResult.passed}/{runResult.total} passed
                      {runResult.language && <span className="font-normal text-slate-400 ml-2">({runResult.language})</span>}
                      {(runResult as any).engine === 'client' && (
                        <span className="ml-2 text-[10px] font-bold text-emerald-600 bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 rounded-full">⚡ browser</span>
                      )}
                      {(runResult as any).engine === 'server' && (
                        <span className="ml-2 text-[10px] font-bold text-slate-500 bg-slate-100 border border-slate-200 px-1.5 py-0.5 rounded-full">☁ server</span>
                      )}
                    </p>
                    <div className="space-y-2">
                      {runResult.results.map((r, i) => (
                        <div key={i} className="text-xs flex items-start gap-3 border border-slate-200 bg-white rounded-xl p-3 shadow-sm">
                          {r.passed
                            ? <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />
                            : <XCircle className="w-4 h-4 text-rose-500 shrink-0 mt-0.5" />}
                          <div className="font-mono text-slate-700 min-w-0 space-y-0.5">
                            <div><span className="font-semibold text-slate-500">input:</span> {JSON.stringify(r.input)}</div>
                            <div><span className="font-semibold text-slate-500">expected:</span> {JSON.stringify(r.expected)}</div>
                            {!r.passed && <div><span className="font-semibold text-slate-500">actual:</span> {JSON.stringify(r.actual)}</div>}
                          </div>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default DSATrackerPage;
