import React, { useEffect, useState } from 'react';
import api from '../lib/api';
import { Flame, ThumbsUp, Eye } from 'lucide-react';
import { Link } from 'react-router-dom';

interface UserLeader {
  username: string;
  display_name?: string;
  avatar_initial: string;
  dsa_streak: number;
  dsa_total_solved: number;
  college?: string;
  department?: string;
}

interface AppLeader {
  id: number;
  name: string;
  owner: string;
  view_count: number;
  upvote_count: number;
  stack?: string;
  description?: string;
}

const RANK_COLORS = ['text-amber-600', 'text-gray-500', 'text-orange-700'];
const RANK_BG = ['bg-amber-50', 'bg-gray-50', 'bg-orange-50/50'];

export const LeaderboardPage: React.FC = () => {
  const [tab, setTab] = useState<'dsa' | 'apps'>('dsa');
  const [dsaList, setDsaList] = useState<UserLeader[]>([]);
  const [appsList, setAppsList] = useState<AppLeader[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchLeaderboards = async () => {
    setLoading(true);
    try {
      if (tab === 'dsa') {
        const resp = await api.get('/dsa/leaderboard');
        setDsaList(resp.data || []);
      } else {
        const resp = await api.get('/showcase/leaderboard');
        setAppsList(resp.data || []);
      }
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchLeaderboards(); }, [tab]);

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-xl font-bold text-gray-900">Leaderboards</h1>
        <p className="text-sm text-gray-500 mt-0.5">Top performers in DSA streaks and showcase apps</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 bg-gray-100 rounded-lg w-fit">
        {(['dsa', 'apps'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              tab === t ? 'bg-white text-gray-900 shadow-sm border border-gray-200' : 'text-gray-500 hover:text-gray-800'
            }`}
          >
            {t === 'dsa' ? <Flame size={14} className="text-amber-500" /> : <ThumbsUp size={14} className="text-blue-600" />}
            {t === 'dsa' ? 'DSA Streaks' : 'Top Apps'}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="h-48 flex items-center justify-center">
          <div className="w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : (
        <div className="bg-white border border-gray-200 rounded-2xl overflow-hidden">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                <th className="py-3 px-5 w-12 text-center">#</th>
                {tab === 'dsa' ? (
                  <>
                    <th className="py-3 px-5">Developer</th>
                    <th className="py-3 px-5 text-center">Streak</th>
                    <th className="py-3 px-5 text-center">Solved</th>
                  </>
                ) : (
                  <>
                    <th className="py-3 px-5">App</th>
                    <th className="py-3 px-5">Creator</th>
                    <th className="py-3 px-5 text-center">Upvotes</th>
                    <th className="py-3 px-5 text-center">Views</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody>
              {tab === 'dsa'
                ? dsaList.map((usr, idx) => (
                    <tr key={usr.username} className={`border-b border-gray-100 hover:bg-gray-50 transition-colors ${idx < 3 ? RANK_BG[idx] : ''}`}>
                      <td className={`py-3.5 px-5 text-center font-bold text-sm ${idx < 3 ? RANK_COLORS[idx] : 'text-gray-400'}`}>{idx + 1}</td>
                      <td className="py-3.5 px-5">
                        <Link to={`/profile?username=${usr.username}`} className="flex items-center gap-3 group">
                          <div className="w-8 h-8 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center font-bold text-xs shrink-0">
                            {usr.avatar_initial}
                          </div>
                          <div>
                            <span className="font-semibold text-sm text-gray-900 group-hover:text-blue-600 block transition-colors">
                              {usr.display_name || usr.username}
                            </span>
                            <span className="text-xs text-gray-400">{usr.college || ''}</span>
                          </div>
                        </Link>
                      </td>
                      <td className="py-3.5 px-5 text-center">
                        <span className="inline-flex items-center gap-1 font-bold text-amber-600 text-sm">
                          <Flame size={13} /> {usr.dsa_streak}
                        </span>
                      </td>
                      <td className="py-3.5 px-5 text-center font-semibold text-gray-700 text-sm">{usr.dsa_total_solved}</td>
                    </tr>
                  ))
                : appsList.map((app, idx) => (
                    <tr key={app.id} className="border-b border-gray-100 hover:bg-gray-50 transition-colors">
                      <td className={`py-3.5 px-5 text-center font-bold text-sm ${idx < 3 ? RANK_COLORS[idx] : 'text-gray-400'}`}>{idx + 1}</td>
                      <td className="py-3.5 px-5">
                        <span className="font-semibold text-sm text-gray-900 block">{app.name}</span>
                        <span className="text-xs text-gray-400 truncate block max-w-xs">{app.description || ''}</span>
                      </td>
                      <td className="py-3.5 px-5">
                        <Link to={`/profile?username=${app.owner}`} className="text-xs text-blue-600 hover:text-blue-700 font-medium">
                          @{app.owner}
                        </Link>
                      </td>
                      <td className="py-3.5 px-5 text-center">
                        <span className="inline-flex items-center gap-1 font-bold text-blue-600 text-sm">
                          <ThumbsUp size={12} /> {app.upvote_count}
                        </span>
                      </td>
                      <td className="py-3.5 px-5 text-center">
                        <span className="inline-flex items-center gap-1 font-semibold text-gray-600 text-sm">
                          <Eye size={12} /> {app.view_count}
                        </span>
                      </td>
                    </tr>
                  ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
export default LeaderboardPage;
