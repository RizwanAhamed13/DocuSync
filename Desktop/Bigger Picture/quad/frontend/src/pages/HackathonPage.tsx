import React, { useEffect, useState, useCallback } from 'react';
import api from '../lib/api';
import { useAuth } from '../lib/auth';
import { ExternalLink, Star } from 'lucide-react';

interface Hackathon {
  hackathon_id: string;
  title: string;
  theme?: string;
  start_time: string;
  end_time: string;
  status: string;
  judging_criteria: string[];
  max_team_size: number;
  min_team_size: number;
}

interface HackTeam {
  hack_team_id: string;
  team_name: string;
  members: string[];
  leader_username: string;
  project_title?: string;
  project_description?: string;
  demo_url?: string;
  submitted_at?: string;
}

interface ScoreRow {
  team_id: string;
  team_name: string;
  total_score: number;
  rank?: number;
}

const statusStyles: Record<string, string> = {
  upcoming: 'border-blue-300 text-blue-600 bg-blue-50',
  active: 'border-green-300 text-green-600 bg-green-50',
  ended: 'border-gray-300 text-gray-500 bg-gray-50',
};

const StatusBadge: React.FC<{ status: string }> = ({ status }) => (
  <span
    className={`inline-block px-2.5 py-0.5 rounded-full border text-[10px] font-bold uppercase tracking-wider ${
      statusStyles[status] || statusStyles.ended
    }`}
  >
    {status}
  </span>
);

function getCountdown(end: string, now: number): string {
  const diff = new Date(end.replace(' ', 'T')).getTime() - now;
  if (Number.isNaN(diff) || diff <= 0) return 'ended';
  const d = Math.floor(diff / 86400000);
  const h = Math.floor((diff % 86400000) / 3600000);
  const m = Math.floor((diff % 3600000) / 60000);
  return `${d}d ${h}h ${m}m left`;
}

export const HackathonPage: React.FC = () => {
  const { user } = useAuth();
  const isFaculty = user?.role === 'faculty' || user?.role === 'admin';

  const [list, setList] = useState<Hackathon[]>([]);
  const [selected, setSelected] = useState<Hackathon | null>(null);
  const [teams, setTeams] = useState<HackTeam[]>([]);
  const [scoreboard, setScoreboard] = useState<ScoreRow[]>([]);
  const [tab, setTab] = useState<'detail' | 'scoreboard'>('detail');
  const [teamName, setTeamName] = useState('');
  const [submitForm, setSubmitForm] = useState({ title: '', description: '', app_name: '', demo_url: '' });
  const [msg, setMsg] = useState('');

  // Live countdown state
  const [nowTime, setNowTime] = useState(Date.now());

  // Creation form state
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [createForm, setCreateForm] = useState({
    title: '',
    theme: '',
    start_time: '',
    end_time: '',
    judging_criteria: '',
    max_team_size: 4,
    min_team_size: 1,
  });

  // Judging state
  const [scoringTeamId, setScoringTeamId] = useState<string | null>(null);
  const [scores, setScores] = useState<Record<string, number>>({});
  const [judgeComment, setJudgeComment] = useState('');
  const [judgingBusy, setJudgingBusy] = useState(false);

  useEffect(() => {
    const timer = setInterval(() => setNowTime(Date.now()), 10000);
    return () => clearInterval(timer);
  }, []);

  const loadList = useCallback(async () => {
    try {
      const resp = await api.get<Hackathon[]>('/hackathons');
      setList(resp.data);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    loadList();
  }, [loadList]);

  const openDetail = async (h: Hackathon) => {
    setSelected(h);
    setTab('detail');
    setMsg('');
    setScoringTeamId(null);
    try {
      const t = await api.get<HackTeam[]>(`/hackathons/${h.hackathon_id}/teams`);
      setTeams(t.data);
    } catch {
      setTeams([]);
    }
  };

  const loadScoreboard = async () => {
    if (!selected) return;
    setTab('scoreboard');
    try {
      const resp = await api.get<{ scoreboard?: ScoreRow[] } | ScoreRow[]>(
        `/hackathons/${selected.hackathon_id}/scoreboard`
      );
      const d = resp.data as { scoreboard?: ScoreRow[] };
      setScoreboard(Array.isArray(resp.data) ? (resp.data as ScoreRow[]) : d.scoreboard || []);
    } catch {
      setScoreboard([]);
    }
  };

  const register = async () => {
    if (!selected || !teamName.trim()) return;
    try {
      await api.post(`/hackathons/${selected.hackathon_id}/register`, { team_name: teamName });
      setMsg('Registered!');
      setTeamName('');
      openDetail(selected);
    } catch (e) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg(err.response?.data?.detail || 'Registration failed');
    }
  };

  const submitProject = async () => {
    if (!selected || !myTeam) return;
    try {
      await api.post(`/hackathons/${selected.hackathon_id}/submit`, {
        team_id: myTeam.hack_team_id,
        title: submitForm.title,
        description: submitForm.description,
        app_name: submitForm.app_name || undefined,
        demo_url: submitForm.demo_url || undefined,
      });
      setMsg('Project submitted!');
      openDetail(selected);
    } catch (e) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg(err.response?.data?.detail || 'Submission failed');
    }
  };

  const handleCreateHackathon = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const payload = {
        title: createForm.title,
        theme: createForm.theme || undefined,
        start_time: createForm.start_time.replace('T', ' '),
        end_time: createForm.end_time.replace('T', ' '),
        judging_criteria: createForm.judging_criteria.split(',').map((s) => s.trim()).filter(Boolean),
        max_team_size: Number(createForm.max_team_size),
        min_team_size: Number(createForm.min_team_size),
      };
      await api.post('/hackathons', payload);
      setMsg('Hackathon created successfully!');
      setShowCreateForm(false);
      setCreateForm({
        title: '',
        theme: '',
        start_time: '',
        end_time: '',
        judging_criteria: '',
        max_team_size: 4,
        min_team_size: 1,
      });
      loadList();
    } catch (err: any) {
      setMsg(err.response?.data?.detail || 'Failed to create hackathon');
    }
  };

  const handleScoreTeam = async (teamId: string) => {
    if (!selected) return;
    setJudgingBusy(true);
    try {
      for (const criterion of selected.judging_criteria) {
        const score = scores[criterion] || 5;
        await api.post(`/hackathons/${selected.hackathon_id}/score/${teamId}`, {
          criterion,
          score,
          comment: judgeComment || undefined,
        });
      }
      setMsg('Project scored successfully!');
      setScoringTeamId(null);
      setScores({});
      setJudgeComment('');
      openDetail(selected);
    } catch (err: any) {
      setMsg(err.response?.data?.detail || 'Failed to submit scores');
    } finally {
      setJudgingBusy(false);
    }
  };

  const myTeam = teams.find((t) => user && t.members.includes(user.username));

  if (!selected) {
    return (
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-black text-slate-900 tracking-tight">Department Hackathons</h1>
            <p className="text-sm text-slate-500 mt-1 font-semibold">Participate in challenges, submit projects, and compete on teams</p>
          </div>
          {isFaculty && (
            <button
              onClick={() => setShowCreateForm((prev) => !prev)}
              className="text-xs font-bold text-white bg-indigo-650 bg-indigo-600 hover:bg-indigo-700 rounded-xl px-4 py-2.5 transition-all shadow-md shadow-indigo-500/10"
            >
              {showCreateForm ? 'Cancel' : 'Schedule Hackathon'}
            </button>
          )}
        </div>

        {/* Schedule Form */}
        {isFaculty && showCreateForm && (
          <form onSubmit={handleCreateHackathon} className="bg-white border border-slate-200 rounded-3xl p-6 shadow-sm space-y-4">
            <h3 className="font-bold text-sm text-slate-800">Schedule New Hackathon</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-500 uppercase">Title</label>
                <input
                  required
                  value={createForm.title}
                  onChange={(e) => setCreateForm({ ...createForm, title: e.target.value })}
                  placeholder="Hackathon title"
                  className="w-full bg-white border border-slate-200 rounded-xl px-3.5 py-2 text-xs text-slate-900 focus:outline-none focus:border-indigo-500"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-500 uppercase">Theme</label>
                <input
                  value={createForm.theme}
                  onChange={(e) => setCreateForm({ ...createForm, theme: e.target.value })}
                  placeholder="Theme/Topic (optional)"
                  className="w-full bg-white border border-slate-200 rounded-xl px-3.5 py-2 text-xs text-slate-900 focus:outline-none focus:border-indigo-500"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-500 uppercase">Start Time (YYYY-MM-DD HH:MM)</label>
                <input
                  required
                  type="datetime-local"
                  value={createForm.start_time}
                  onChange={(e) => setCreateForm({ ...createForm, start_time: e.target.value })}
                  className="w-full bg-white border border-slate-200 rounded-xl px-3.5 py-2 text-xs text-slate-900 focus:outline-none focus:border-indigo-500"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-500 uppercase">End Time (YYYY-MM-DD HH:MM)</label>
                <input
                  required
                  type="datetime-local"
                  value={createForm.end_time}
                  onChange={(e) => setCreateForm({ ...createForm, end_time: e.target.value })}
                  className="w-full bg-white border border-slate-200 rounded-xl px-3.5 py-2 text-xs text-slate-900 focus:outline-none focus:border-indigo-500"
                />
              </div>
              <div className="space-y-1 md:col-span-2">
                <label className="text-xs font-semibold text-slate-500 uppercase">Judging Criteria (comma-separated)</label>
                <input
                  required
                  value={createForm.judging_criteria}
                  onChange={(e) => setCreateForm({ ...createForm, judging_criteria: e.target.value })}
                  placeholder="Code Quality, Innovation, Pitch, Presentation"
                  className="w-full bg-white border border-slate-200 rounded-xl px-3.5 py-2 text-xs text-slate-900 focus:outline-none focus:border-indigo-500"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-500 uppercase">Min Team Size</label>
                <input
                  type="number"
                  required
                  value={createForm.min_team_size}
                  onChange={(e) => setCreateForm({ ...createForm, min_team_size: Number(e.target.value) })}
                  className="w-full bg-white border border-slate-200 rounded-xl px-3.5 py-2 text-xs text-slate-900 focus:outline-none focus:border-indigo-500"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-500 uppercase">Max Team Size</label>
                <input
                  type="number"
                  required
                  value={createForm.max_team_size}
                  onChange={(e) => setCreateForm({ ...createForm, max_team_size: Number(e.target.value) })}
                  className="w-full bg-white border border-slate-200 rounded-xl px-3.5 py-2 text-xs text-slate-900 focus:outline-none focus:border-indigo-500"
                />
              </div>
            </div>
            <button
              type="submit"
              className="text-xs font-bold text-white bg-indigo-650 bg-indigo-600 hover:bg-indigo-700 rounded-xl px-5 py-2.5 transition-all shadow-md shadow-indigo-500/10"
            >
              Create Hackathon
            </button>
          </form>
        )}

        {msg && (
          <div className="p-4 rounded-xl bg-indigo-50 border border-indigo-150 text-indigo-700 text-xs font-bold">
            {msg}
          </div>
        )}

        {list.length === 0 ? (
          <div className="bg-white border border-slate-200/80 rounded-3xl p-16 text-center shadow-sm">
            <p className="text-sm text-slate-555 font-semibold">No hackathons have been scheduled yet.</p>
          </div>
        ) : (
          <div className="grid gap-4">
            {list.map((h) => (
              <button
                key={h.hackathon_id}
                onClick={() => openDetail(h)}
                className="text-left bg-white border border-slate-200/80 rounded-2xl p-6 hover:border-indigo-250 hover:shadow-md transition-all card-hover"
              >
                <div className="flex items-center justify-between gap-4">
                  <span className="font-extrabold text-slate-900 text-base">{h.title}</span>
                  <StatusBadge status={h.status} />
                </div>
                {h.theme && <p className="text-sm text-slate-600 mt-2 font-medium">{h.theme}</p>}
                <div className="flex items-center gap-2 mt-4 text-[11px] text-slate-400 font-semibold">
                  <span>Timeline:</span>
                  <span className="font-mono bg-slate-50 border border-slate-200 px-2 py-0.5 rounded text-slate-600">{h.start_time}</span>
                  <span>→</span>
                  <span className="font-mono bg-slate-50 border border-slate-200 px-2 py-0.5 rounded text-slate-600">{h.end_time}</span>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <button
        onClick={() => setSelected(null)}
        className="inline-flex items-center gap-1.5 text-xs text-indigo-650 hover:text-indigo-750 font-bold transition-colors"
      >
        &larr; Back to hackathons
      </button>

      <div className="bg-white border border-slate-200/80 rounded-3xl p-6 shadow-sm space-y-4">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <h1 className="text-2xl font-black text-slate-900 tracking-tight">{selected.title}</h1>
          <StatusBadge status={selected.status} />
        </div>
        {selected.theme && <p className="text-sm text-slate-600 font-semibold">{selected.theme}</p>}
        <div className="flex items-center gap-2.5 text-xs text-slate-400 font-semibold flex-wrap">
          <span>Schedule:</span>
          <span className="font-mono bg-slate-50 border border-slate-200 px-2.5 py-0.5 rounded text-slate-600">{selected.start_time} &rarr; {selected.end_time}</span>
          {selected.status === 'active' && (
            <span className="font-mono bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 rounded text-emerald-700 animate-pulse uppercase tracking-wider font-bold">
              {getCountdown(selected.end_time, nowTime)}
            </span>
          )}
          <span className="bg-slate-100 px-2.5 py-0.5 rounded text-slate-500 font-bold">
            {teams.length} {teams.length === 1 ? 'Team' : 'Teams'}
          </span>
        </div>
      </div>

      <div className="flex gap-2">
        <button
          onClick={() => setTab('detail')}
          className={`text-xs font-bold px-4 py-2 rounded-xl transition-all border ${
            tab === 'detail'
              ? 'border-indigo-200 text-indigo-700 bg-indigo-50/50 shadow-sm'
              : 'border-slate-200 text-slate-600 hover:bg-slate-50'
          }`}
        >
          Details
        </button>
        {(selected.status === 'ended' || isFaculty) && (
          <button
            onClick={loadScoreboard}
            className={`text-xs font-bold px-4 py-2 rounded-xl transition-all border ${
              tab === 'scoreboard'
                ? 'border-indigo-200 text-indigo-700 bg-indigo-50/50 shadow-sm'
                : 'border-slate-200 text-slate-600 hover:bg-slate-50'
            }`}
          >
            Scoreboard
          </button>
        )}
      </div>

      {msg && (
        <div className="p-4 rounded-xl bg-indigo-50 border border-indigo-150 text-indigo-700 text-xs font-bold">
          {msg}
        </div>
      )}

      {tab === 'detail' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-6">
            <div className="bg-white border border-slate-200/80 rounded-3xl p-6 shadow-sm">
              <h2 className="text-sm font-bold text-slate-900 mb-4">Judging Criteria</h2>
              <ul className="text-xs text-slate-600 space-y-2.5 font-semibold">
                {selected.judging_criteria.map((c, idx) => (
                  <li key={c} className="flex items-start gap-2">
                    <span className="w-5 h-5 rounded-lg bg-indigo-50 border border-indigo-100 flex items-center justify-center text-[10px] text-indigo-600 font-bold shrink-0 mt-0.5">
                      {idx + 1}
                    </span>
                    <span className="leading-normal">{c}</span>
                  </li>
                ))}
              </ul>
            </div>

            {user && selected.status === 'active' && !myTeam && (
              <div className="bg-white border border-slate-200/80 rounded-3xl p-6 shadow-sm space-y-4">
                <div>
                  <h2 className="text-sm font-bold text-slate-900">Register a Team</h2>
                  <p className="text-xs text-slate-400 mt-0.5 font-semibold">Join the competition under a custom team name</p>
                </div>
                <div className="flex gap-2.5">
                  <input
                    value={teamName}
                    onChange={(e) => setTeamName(e.target.value)}
                    placeholder="Team name"
                    className="flex-1 bg-white border border-slate-200 rounded-xl px-4 py-2.5 text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-50 transition-all font-semibold"
                  />
                  <button
                    onClick={register}
                    className="text-xs font-bold text-white bg-indigo-600 hover:bg-indigo-700 rounded-xl px-5 py-2.5 transition-all shadow-md shadow-indigo-600/10 hover:shadow-indigo-650/20"
                  >
                    Register
                  </button>
                </div>
              </div>
            )}

            {user && myTeam && selected.status === 'active' && (
              <div className="bg-white border border-slate-200/80 rounded-3xl p-6 shadow-sm space-y-4">
                <div>
                  <h2 className="text-sm font-bold text-slate-900">Submit Project</h2>
                  <p className="text-xs text-slate-400 mt-0.5 font-semibold">Fill in details to submit your team's application</p>
                </div>
                <div className="space-y-3">
                  <input
                    value={submitForm.title}
                    onChange={(e) => setSubmitForm({ ...submitForm, title: e.target.value })}
                    placeholder="Project title"
                    className="w-full bg-white border border-slate-200 rounded-xl px-4 py-2.5 text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-50 transition-all font-semibold"
                  />
                  <textarea
                    value={submitForm.description}
                    onChange={(e) => setSubmitForm({ ...submitForm, description: e.target.value })}
                    placeholder="Description"
                    className="w-full bg-white border border-slate-200 rounded-xl px-4 py-2.5 text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-50 transition-all font-semibold h-20 resize-none"
                  />
                  <input
                    value={submitForm.app_name}
                    onChange={(e) => setSubmitForm({ ...submitForm, app_name: e.target.value })}
                    placeholder="App name (optional)"
                    className="w-full bg-white border border-slate-200 rounded-xl px-4 py-2.5 text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-50 transition-all font-semibold"
                  />
                  <input
                    value={submitForm.demo_url}
                    onChange={(e) => setSubmitForm({ ...submitForm, demo_url: e.target.value })}
                    placeholder="Demo URL (optional)"
                    className="w-full bg-white border border-slate-200 rounded-xl px-4 py-2.5 text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-50 transition-all font-semibold"
                  />
                  <button
                    onClick={submitProject}
                    className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-2.5 rounded-xl text-xs transition-all shadow-md shadow-indigo-600/10 hover:shadow-indigo-650/20"
                  >
                    Submit Project
                  </button>
                </div>
              </div>
            )}
          </div>

          <div className="bg-white border border-slate-200/80 rounded-3xl p-6 shadow-sm h-fit space-y-4">
            <h2 className="text-sm font-bold text-slate-900">Registered Teams</h2>
            {teams.length === 0 ? (
              <p className="text-xs text-slate-400 font-semibold">No teams registered yet.</p>
            ) : (
              <ul className="space-y-4">
                {teams.map((t) => (
                  <li key={t.hack_team_id} className="p-4 bg-slate-50/50 border border-slate-200 rounded-2xl space-y-3">
                    <div className="flex items-center justify-between">
                      <div>
                        <span className="text-xs font-bold text-slate-900 block">{t.team_name}</span>
                        <span className="text-[10px] text-slate-400 font-semibold mt-0.5 block">
                          Leader: @{t.leader_username}
                        </span>
                      </div>
                      {t.submitted_at && (
                        <span className="text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200 px-2 py-0.5 rounded-full uppercase tracking-wider">
                          submitted
                        </span>
                      )}
                    </div>

                    {/* Member chips */}
                    <div className="flex flex-wrap gap-1">
                      {t.members.map((m) => (
                        <span key={m} className={`px-2 py-0.5 rounded-full text-[9px] font-bold ${m === t.leader_username ? 'bg-indigo-150 text-indigo-700' : 'bg-slate-200 text-slate-600'}`}>
                          @{m} {m === t.leader_username && '👑'}
                        </span>
                      ))}
                    </div>

                    {/* Project submission details */}
                    {t.project_title && (
                      <div className="p-3 bg-white border border-slate-150 rounded-xl space-y-1">
                        <span className="text-xs font-bold text-slate-800 block">Project: {t.project_title}</span>
                        <p className="text-[10px] text-slate-500">{t.project_description}</p>
                        <div className="flex gap-3 pt-1">
                          {t.demo_url && (
                            <a href={t.demo_url} target="_blank" rel="noreferrer" className="text-[10px] font-bold text-indigo-600 hover:text-indigo-700 flex items-center gap-0.5">
                              Demo Link <ExternalLink className="w-2.5 h-2.5" />
                            </a>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Judging / Score trigger */}
                    {isFaculty && t.project_title && (
                      <div className="border-t border-slate-200 pt-3">
                        {scoringTeamId === t.hack_team_id ? (
                          <div className="space-y-3 bg-white border border-slate-150 p-3 rounded-xl">
                            <span className="text-[10px] uppercase font-bold text-slate-400">Evaluate Project</span>
                            {selected.judging_criteria.map((c) => (
                              <div key={c} className="space-y-1">
                                <div className="flex justify-between text-[11px] font-bold text-slate-700">
                                  <span>{c}</span>
                                  <span>{scores[c] || 5} / 10</span>
                                </div>
                                <input
                                  type="range"
                                  min="1"
                                  max="10"
                                  value={scores[c] || 5}
                                  onChange={(e) => setScores({ ...scores, [c]: Number(e.target.value) })}
                                  className="w-full h-1 bg-slate-150 rounded-lg appearance-none cursor-pointer accent-indigo-600"
                                />
                              </div>
                            ))}
                            <div className="space-y-1">
                              <label className="text-[10px] font-bold text-slate-400 uppercase">Comments</label>
                              <textarea
                                value={judgeComment}
                                onChange={(e) => setJudgeComment(e.target.value)}
                                placeholder="Feedback comments..."
                                className="w-full text-xs border border-slate-200 rounded-lg p-2 h-12 resize-none"
                              />
                            </div>
                            <div className="flex gap-2">
                              <button
                                onClick={() => handleScoreTeam(t.hack_team_id)}
                                disabled={judgingBusy}
                                className="text-xs font-bold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg px-3 py-1.5 transition-colors disabled:opacity-50"
                              >
                                {judgingBusy ? 'Saving...' : 'Submit'}
                              </button>
                              <button
                                onClick={() => setScoringTeamId(null)}
                                className="text-xs font-bold border border-slate-200 text-slate-500 hover:bg-slate-50 rounded-lg px-3 py-1.5 transition-colors"
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        ) : (
                          <button
                            onClick={() => {
                              setScoringTeamId(t.hack_team_id);
                              const initScores: Record<string, number> = {};
                              selected.judging_criteria.forEach((c) => {
                                initScores[c] = 5;
                              });
                              setScores(initScores);
                            }}
                            className="text-xs font-bold text-indigo-650 hover:text-indigo-755 hover:text-indigo-700 flex items-center gap-1"
                          >
                            <Star className="w-3.5 h-3.5 text-indigo-500" /> Judge Submission
                          </button>
                        )}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {tab === 'scoreboard' && (
        <div className="bg-white border border-slate-200/80 rounded-3xl p-6 shadow-sm">
          <h2 className="text-sm font-bold text-slate-900 mb-4">Scoreboard</h2>
          {scoreboard.length === 0 ? (
            <p className="text-xs text-slate-400 font-semibold">No scores yet.</p>
          ) : (
            <div className="overflow-hidden border border-slate-100 rounded-2xl">
              <table className="w-full text-xs text-left border-collapse">
                <thead>
                  <tr className="bg-slate-50 text-slate-400 font-bold uppercase tracking-wider border-b border-slate-100">
                    <th className="py-3 px-4 w-20">Rank</th>
                    <th className="py-3 px-4">Team Name</th>
                    <th className="py-3 px-4 text-right">Total Score</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 font-semibold">
                  {scoreboard.map((r, i) => (
                    <tr key={r.team_id} className="hover:bg-slate-50/40 transition-colors">
                      <td className="py-3 px-4 text-slate-900 font-bold">#{r.rank ?? i + 1}</td>
                      <td className="py-3 px-4 text-slate-700">{r.team_name}</td>
                      <td className="py-3 px-4 text-slate-900 font-black text-right">{r.total_score}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default HackathonPage;
