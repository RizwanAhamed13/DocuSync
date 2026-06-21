import React, { useEffect, useState, useCallback } from 'react';
import api from '../lib/api';
import { useAuth } from '../lib/auth';
import { Download, Search } from 'lucide-react';

interface DsaStudent {
  username: string;
  display_name?: string;
  total_solved: number;
  streak: number;
}

interface Deploy {
  name: string;
  owner?: string;
  status: string;
  approval_status?: string;
  created_at: string;
}

interface Dashboard {
  total_students: number;
  total_projects: number;
  projects_pending_approval: number;
  dsa_class_stats: { Easy: number; Medium: number; Hard: number };
  top_dsa_students: DsaStudent[];
  recent_deploys: Deploy[];
  active_tunnels: number;
}

const Card: React.FC<{ label: string; value: number | string }> = ({ label, value }) => (
  <div className="border border-slate-200 rounded-2xl bg-white p-5 shadow-sm">
    <div className="text-3xl font-black text-slate-800">{value}</div>
    <div className="text-xs text-slate-500 font-bold uppercase tracking-wider mt-1">{label}</div>
  </div>
);

const StatusBadge: React.FC<{ status: string }> = ({ status }) => (
  <span className="inline-block px-2.5 py-0.5 rounded-full border border-slate-200 bg-slate-50 text-[10px] font-bold text-slate-600">
    {status}
  </span>
);

export const FacultyDashboard: React.FC = () => {
  const { user } = useAuth();
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState('');

  // Confirmation state
  const [confirmAction, setConfirmAction] = useState<{ name: string; action: 'approve' | 'reject' } | null>(null);

  // Search/Filter state
  const [searchQuery, setSearchQuery] = useState('');

  const load = useCallback(async () => {
    try {
      const resp = await api.get<Dashboard>('/faculty/dashboard');
      setData(resp.data);
    } catch {
      setError('Failed to load dashboard.');
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const act = async (name: string, action: 'approve' | 'reject') => {
    try {
      await api.post(`/deploy/${action}/${name}`);
      load();
    } catch {
      /* ignore */
    } finally {
      setConfirmAction(null);
    }
  };

  const handleExportCSV = () => {
    if (!data) return;
    const headers = ['Username', 'Display Name', 'Total Solved', 'Streak'];
    const rows = data.top_dsa_students.map((s) => [
      s.username,
      s.display_name || '',
      s.total_solved,
      s.streak,
    ]);
    const csvContent =
      'data:text/csv;charset=utf-8,' +
      [headers.join(','), ...rows.map((e) => e.join(','))].join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', 'student_dsa_metrics.csv');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  if (user && user.role !== 'faculty' && user.role !== 'admin') {
    return <div className="p-6 text-sm text-slate-550 font-semibold">Faculty access required.</div>;
  }

  if (error) return <div className="p-6 text-sm text-rose-600 font-bold">{error}</div>;
  if (!data) return <div className="p-6 text-sm text-slate-400 font-semibold">Loading...</div>;

  const totalDsa =
    data.dsa_class_stats.Easy + data.dsa_class_stats.Medium + data.dsa_class_stats.Hard || 1;
  const pending = data.recent_deploys.filter(
    (d) => d.status === 'PENDING_APPROVAL' || d.approval_status === 'pending'
  );

  const filteredStudents = data.top_dsa_students.filter((s) => {
    const term = searchQuery.toLowerCase();
    return (
      s.username.toLowerCase().includes(term) ||
      (s.display_name || '').toLowerCase().includes(term)
    );
  });

  // SVG Donut metrics
  const radius = 30;
  const circumference = 2 * Math.PI * radius;
  const pctEasy = (data.dsa_class_stats.Easy / totalDsa) * 100;
  const pctMedium = (data.dsa_class_stats.Medium / totalDsa) * 100;
  const pctHard = (data.dsa_class_stats.Hard / totalDsa) * 100;

  const strokeEasy = circumference * (pctEasy / 100);
  const strokeMedium = circumference * (pctMedium / 100);
  const strokeHard = circumference * (pctHard / 100);

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6 relative">
      {/* Confirmation Modal */}
      {confirmAction && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-white border border-slate-200 rounded-3xl p-6 max-w-md w-full shadow-xl space-y-4">
            <h3 className="text-sm font-extrabold text-slate-900 uppercase tracking-wider">Confirm Action</h3>
            <p className="text-xs text-slate-500 leading-relaxed font-semibold">
              Are you sure you want to <span className="font-extrabold text-slate-800 uppercase">{confirmAction.action}</span> the deployment for <span className="font-mono text-indigo-650 bg-indigo-50 px-1.5 py-0.5 rounded">{confirmAction.name}</span>?
            </p>
            <div className="flex justify-end gap-2.5 pt-2">
              <button
                onClick={() => setConfirmAction(null)}
                className="px-4 py-2 border border-slate-200 text-slate-655 text-slate-600 rounded-xl text-xs font-bold hover:bg-slate-50 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => act(confirmAction.name, confirmAction.action)}
                className={`px-4 py-2 text-white rounded-xl text-xs font-bold shadow-md transition-colors ${
                  confirmAction.action === 'approve'
                    ? 'bg-emerald-600 hover:bg-emerald-700 shadow-emerald-500/10'
                    : 'bg-rose-600 hover:bg-rose-700 shadow-rose-500/10'
                }`}
              >
                Confirm
              </button>
            </div>
          </div>
        </div>
      )}

      <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">Faculty Dashboard</h1>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card label="Total Students" value={data.total_students} />
        <Card label="Total Projects" value={data.total_projects} />
        <Card label="Pending Approvals" value={data.projects_pending_approval} />
        <Card label="Active Tunnels" value={data.active_tunnels} />
      </div>

      <div className="border border-slate-200 rounded-2xl bg-white p-5 shadow-sm">
        <h2 className="text-base font-bold text-slate-800 mb-4">DSA Class Progress</h2>
        
        <div className="flex flex-col md:flex-row items-center gap-8">
          {/* Donut chart */}
          <div className="relative w-32 h-32 shrink-0">
            <svg className="w-full h-full -rotate-90" viewBox="0 0 80 80">
              <circle cx="40" cy="40" r={radius} fill="transparent" stroke="#f1f5f9" strokeWidth="8" />
              {data.dsa_class_stats.Easy > 0 && (
                <circle 
                  cx="40" cy="40" r={radius} fill="transparent" 
                  stroke="#10b981" strokeWidth="8" 
                  strokeDasharray={`${strokeEasy} ${circumference - strokeEasy}`}
                  strokeDashoffset={0}
                />
              )}
              {data.dsa_class_stats.Medium > 0 && (
                <circle 
                  cx="40" cy="40" r={radius} fill="transparent" 
                  stroke="#f59e0b" strokeWidth="8" 
                  strokeDasharray={`${strokeMedium} ${circumference - strokeMedium}`}
                  strokeDashoffset={-strokeEasy}
                />
              )}
              {data.dsa_class_stats.Hard > 0 && (
                <circle 
                  cx="40" cy="40" r={radius} fill="transparent" 
                  stroke="#ef4444" strokeWidth="8" 
                  strokeDasharray={`${strokeHard} ${circumference - strokeHard}`}
                  strokeDashoffset={-(strokeEasy + strokeMedium)}
                />
              )}
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-lg font-black text-slate-800">{totalDsa}</span>
              <span className="text-[9px] text-slate-400 font-bold uppercase">Solved</span>
            </div>
          </div>

          <div className="flex-1 w-full space-y-3">
            {(['Easy', 'Medium', 'Hard'] as const).map((diff) => {
              const v = data.dsa_class_stats[diff];
              const colors = { Easy: 'bg-green-500', Medium: 'bg-amber-500', Hard: 'bg-red-500' };
              return (
                <div key={diff}>
                  <div className="flex justify-between text-xs text-slate-600 mb-1 font-semibold">
                    <span className="flex items-center gap-1.5">
                      <span className={`w-2 h-2 rounded-full ${colors[diff]}`} />
                      {diff}
                    </span>
                    <span className="font-bold text-slate-800">{v}</span>
                  </div>
                  <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                    <div
                      className={`h-full ${colors[diff]}`}
                      style={{ width: `${(v / totalDsa) * 100}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="border border-slate-200 rounded-2xl bg-white p-5 shadow-sm space-y-4">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <h2 className="text-base font-bold text-slate-800">Top DSA Students</h2>
          <div className="flex gap-2 items-center">
            {/* Search */}
            <div className="relative">
              <Search className="absolute left-3 top-2.5 w-3.5 h-3.5 text-slate-400" />
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search students..."
                className="bg-white border border-slate-200 rounded-xl pl-9 pr-4 py-1.5 text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:border-indigo-500 w-44 font-semibold"
              />
            </div>
            {/* Export */}
            <button
              onClick={handleExportCSV}
              className="flex items-center gap-1.5 text-xs font-bold border border-slate-200 hover:bg-slate-50 text-slate-655 text-slate-600 px-3.5 py-1.5 rounded-xl transition-all shadow-sm"
            >
              <Download className="w-3.5 h-3.5" /> Export CSV
            </button>
          </div>
        </div>

        <table className="w-full text-xs text-left">
          <thead>
            <tr className="border-b border-slate-100 text-slate-400 font-bold uppercase tracking-wider">
              <th className="py-2">Username</th>
              <th className="py-2">Solved</th>
              <th className="py-2">Streak</th>
            </tr>
          </thead>
          <tbody>
            {filteredStudents.map((s) => (
              <tr key={s.username} className="border-b border-slate-50 hover:bg-slate-50/50 transition-colors">
                <td className="py-2.5 font-semibold text-slate-800">{s.display_name || s.username}</td>
                <td className="py-2.5 text-slate-700 font-bold">{s.total_solved}</td>
                <td className="py-2.5 text-amber-600 font-bold">{s.streak}</td>
              </tr>
            ))}
            {filteredStudents.length === 0 && (
              <tr>
                <td colSpan={3} className="py-4 text-center text-slate-400 font-semibold">
                  No matches found
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="border border-slate-200 rounded-2xl bg-white p-5 shadow-sm">
        <h2 className="text-base font-bold text-slate-800 mb-3">Pending Deploy Approvals</h2>
        <table className="w-full text-xs text-left">
          <thead>
            <tr className="border-b border-slate-100 text-slate-400 font-bold uppercase tracking-wider">
              <th className="py-2">App</th>
              <th className="py-2">Owner</th>
              <th className="py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {pending.map((d) => (
              <tr key={d.name} className="border-b border-slate-50 hover:bg-slate-50/50 transition-colors">
                <td className="py-2.5 font-bold text-slate-800">{d.name}</td>
                <td className="py-2.5 text-slate-655 font-semibold text-slate-650 text-slate-600">{d.owner || '-'}</td>
                <td className="py-2.5 flex gap-2">
                  <button
                    onClick={() => setConfirmAction({ name: d.name, action: 'approve' })}
                    className="px-3 py-1 rounded-lg border border-emerald-200 text-emerald-600 hover:bg-emerald-50 bg-white font-semibold transition-colors shadow-sm"
                  >
                    Approve
                  </button>
                  <button
                    onClick={() => setConfirmAction({ name: d.name, action: 'reject' })}
                    className="px-3 py-1 rounded-lg border border-rose-200 text-rose-600 hover:bg-rose-50 bg-white font-semibold transition-colors shadow-sm"
                  >
                    Reject
                  </button>
                </td>
              </tr>
            ))}
            {pending.length === 0 && (
              <tr>
                <td colSpan={3} className="py-4 text-center text-slate-400 font-semibold">
                  No pending approvals
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="border border-slate-200 rounded-2xl bg-white p-5 shadow-sm">
        <h2 className="text-base font-bold text-slate-800 mb-3">Recent Deploys</h2>
        <table className="w-full text-xs text-left">
          <thead>
            <tr className="border-b border-slate-100 text-slate-400 font-bold uppercase tracking-wider">
              <th className="py-2">App</th>
              <th className="py-2">Owner</th>
              <th className="py-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {data.recent_deploys.map((d) => (
              <tr key={d.name} className="border-b border-slate-50 hover:bg-slate-50/50 transition-colors">
                <td className="py-2.5 font-bold text-slate-800">{d.name}</td>
                <td className="py-2.5 text-slate-600 font-semibold">{d.owner || '-'}</td>
                <td className="py-2.5">
                  <StatusBadge status={d.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default FacultyDashboard;
