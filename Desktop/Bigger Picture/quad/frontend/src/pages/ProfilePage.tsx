import React, { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { useAuth } from '../lib/auth';
import api from '../lib/api';
import { 
  User, 
  Mail, 
  GitBranch, 
  Edit3, 
  Save, 
  Flame, 
  Trophy,
  ExternalLink,
  BookOpen
} from 'lucide-react';

interface ProfileData {
  user: {
    username: string;
    display_name?: string;
    avatar_initial: string;
    college?: string;
    department?: string;
    role: string;
    bio?: string;
    github_url?: string;
    linkedin_url?: string;
    dsa_streak: number;
    dsa_total_solved: number;
  };
  apps: AppItem[];
}

interface AppItem {
  id: number;
  name: string;
  description?: string;
  status?: string;
}

interface Badge {
  badge_type: string;
  earned_at: string;
  label: string;
  icon_emoji: string;
}

interface DsaStats {
  difficulty_distribution: { Easy: number; Medium: number; Hard: number };
}

export const ProfilePage: React.FC = () => {
  const { user: currentUser, updateUser: updateAuthUser } = useAuth();
  const location = useLocation();
  
  // Parse username query parameter
  const searchParams = new URLSearchParams(location.search);
  const usernameParam = searchParams.get('username');
  const targetUsername = usernameParam || currentUser?.username;

  const isSelf = currentUser && targetUsername === currentUser.username;

  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [loading, setLoading] = useState(true);
  const [badges, setBadges] = useState<Badge[]>([]);
  const [dsaStats, setDsaStats] = useState<DsaStats | null>(null);
  const [recentPosts, setRecentPosts] = useState<{ post_id: string; content: string; created_at: string }[]>([]);
  
  // Edit mode states
  const [isEditing, setIsEditing] = useState(false);
  const [displayName, setDisplayName] = useState('');
  const [bio, setBio] = useState('');
  const [githubUrl, setGithubUrl] = useState('');
  const [linkedinUrl, setLinkedinUrl] = useState('');
  const [college, setCollege] = useState('');
  const [department, setDepartment] = useState('');
  
  const [copied, setCopied] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchProfile = async () => {
    if (!targetUsername) return;
    setLoading(true);
    try {
      const resp = await api.get(`/showcase/users/${targetUsername}`);
      setProfile(resp.data);
      
      // Sync edit inputs
      if (resp.data.user) {
        const u = resp.data.user;
        setDisplayName(u.display_name || '');
        setBio(u.bio || '');
        setGithubUrl(u.github_url || '');
        setLinkedinUrl(u.linkedin_url || '');
        setCollege(u.college || '');
        setDepartment(u.department || '');
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProfile();
    if (targetUsername) {
      api.get<Badge[]>(`/badges/${targetUsername}`).then((r) => setBadges(r.data)).catch(() => setBadges([]));
      api.get<DsaStats>(`/dsa/stats/${targetUsername}`).then((r) => setDsaStats(r.data)).catch(() => setDsaStats(null));
      api
        .get<{ post_id: string; username: string; content: string; created_at: string }[]>('/feed')
        .then((r) => setRecentPosts(r.data.filter((p) => p.username === targetUsername).slice(0, 5)))
        .catch(() => setRecentPosts([]));
    }
  }, [targetUsername]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSaving(true);

    try {
      const resp = await api.patch('/auth/profile', {
        display_name: displayName || undefined,
        bio: bio || undefined,
        github_url: githubUrl || undefined,
        linkedin_url: linkedinUrl || undefined,
        college: college || undefined,
        department: department || undefined,
      });
      
      // Update global context user
      if (currentUser) {
        updateAuthUser({
          ...currentUser,
          ...resp.data
        });
      }
      setIsEditing(false);
      fetchProfile();
    } catch (err: any) {
      const msg = err.response?.data?.detail || err.response?.data?.error || 'Failed to update profile.';
      setError(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {loading ? (
        <div className="h-64 flex items-center justify-center">
          <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-indigo-650" />
        </div>
      ) : !profile ? (
        <div className="text-center py-12">
          <p className="text-slate-500">User profile not found.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Sidebar Info card */}
          <div className="lg:col-span-1 space-y-6">
            <div className="p-6 rounded-3xl border border-slate-200 bg-white text-center space-y-4 relative shadow-sm">
              {isSelf && !isEditing && (
                <button
                  onClick={() => setIsEditing(true)}
                  className="absolute right-4 top-4 p-2 rounded-lg bg-white hover:bg-slate-50 text-slate-500 hover:text-slate-800 border border-slate-200 transition-colors shadow-sm"
                  title="Edit Profile"
                >
                  <Edit3 className="w-4 h-4" />
                </button>
              )}

              {/* Avatar block */}
              <div className="w-20 h-20 rounded-full bg-gradient-to-tr from-indigo-650 to-indigo-500 border border-indigo-500/20 flex items-center justify-center font-bold text-3xl text-white mx-auto shadow-md shadow-indigo-650/15">
                {profile.user.avatar_initial}
              </div>

              <div className="space-y-1">
                <h3 className="text-xl font-bold text-slate-800">{profile.user.display_name || profile.user.username}</h3>
                <span className="text-xs text-slate-500 font-semibold block">@{profile.user.username}</span>
                <span className="text-xs uppercase bg-slate-100 text-slate-650 px-2.5 py-0.5 rounded-full border border-slate-200 font-semibold inline-block mt-1">
                  {profile.user.role}
                </span>
              </div>

              {profile.user.bio && (
                <p className="text-xs text-slate-500 leading-relaxed border-t border-b border-slate-100 py-3">
                  {profile.user.bio}
                </p>
              )}

              {/* Academic metadata */}
              <div className="space-y-2 text-left text-xs text-slate-500">
                {profile.user.college && (
                  <div className="flex items-start gap-2">
                    <BookOpen className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
                    <div>
                      <span className="font-semibold block text-slate-700">College</span>
                      <span className="text-slate-550">{profile.user.college}</span>
                    </div>
                  </div>
                )}
                {profile.user.department && (
                  <div className="flex items-start gap-2">
                    <BookOpen className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
                    <div>
                      <span className="font-semibold block text-slate-700">Department</span>
                      <span className="text-slate-500">{profile.user.department}</span>
                    </div>
                  </div>
                )}
              </div>

              {/* Share Portfolio */}
              <button
                onClick={() => {
                  const shareUrl = `${window.location.origin}/profile?username=${profile.user.username}`;
                  navigator.clipboard.writeText(shareUrl);
                  setCopied(true);
                  setTimeout(() => setCopied(false), 2000);
                }}
                className={`w-full text-xs font-bold py-2.5 px-4 rounded-xl border transition-all shadow-sm ${
                  copied
                    ? 'bg-emerald-50 border-emerald-250 text-emerald-700'
                    : 'bg-white hover:bg-slate-50 text-slate-700 border-slate-200 hover:border-slate-300'
                }`}
              >
                {copied ? 'Link Copied!' : 'Share Portfolio'}
              </button>

              {/* Badges Display */}
              {badges.length > 0 && (
                <div className="pt-4 border-t border-slate-100 text-left">
                  <h4 className="text-[10px] text-slate-500 font-bold uppercase tracking-wider mb-3">Earned Badges</h4>
                  <div className="grid grid-cols-2 gap-2">
                    {badges.map((b) => (
                      <div
                        key={b.badge_type}
                        title={`Earned on ${new Date(b.earned_at).toLocaleDateString()}`}
                        className="flex items-center gap-2 p-2.5 rounded-xl border border-slate-200/60 bg-gradient-to-br from-slate-50 to-white shadow-sm hover:shadow hover:scale-[1.02] transition-all"
                      >
                        <span className="text-2xl filter drop-shadow">{b.icon_emoji}</span>
                        <div className="min-w-0">
                          <span className="text-[10px] font-extrabold text-slate-800 block truncate leading-tight">{b.label}</span>
                          <span className="text-[8px] text-slate-400 font-semibold uppercase mt-0.5 block">
                            {new Date(b.earned_at).toLocaleDateString(undefined, {month: 'short', day: 'numeric'})}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Social Link Previews */}
              {(profile.user.github_url || profile.user.linkedin_url) && (
                <div className="pt-4 border-t border-slate-100 text-left space-y-2">
                  <h4 className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">Connected Accounts</h4>
                  
                  {profile.user.github_url && (
                    <a 
                      href={profile.user.github_url} 
                      target="_blank" 
                      rel="noopener noreferrer"
                      className="flex items-center justify-between p-3 rounded-2xl border border-slate-205 border-slate-200 bg-slate-50/50 hover:bg-slate-50 hover:border-slate-300 transition-all shadow-sm group"
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        <div className="w-8 h-8 rounded-xl bg-slate-900 flex items-center justify-center text-white text-sm shrink-0 shadow-sm">
                          <GitBranch className="w-4 h-4" />
                        </div>
                        <div className="min-w-0">
                          <span className="text-xs font-bold text-slate-800 block">GitHub Profile</span>
                          <span className="text-[10px] text-slate-400 font-semibold truncate block">
                            {profile.user.github_url.replace(/https?:\/\/(www\.)?github\.com\//, '')}
                          </span>
                        </div>
                      </div>
                      <ExternalLink className="w-3.5 h-3.5 text-slate-400 group-hover:text-slate-700 transition-colors" />
                    </a>
                  )}

                  {profile.user.linkedin_url && (
                    <a 
                      href={profile.user.linkedin_url} 
                      target="_blank" 
                      rel="noopener noreferrer"
                      className="flex items-center justify-between p-3 rounded-2xl border border-slate-205 border-slate-200 bg-slate-50/50 hover:bg-slate-50 hover:border-slate-300 transition-all shadow-sm group"
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        <div className="w-8 h-8 rounded-xl bg-blue-600 flex items-center justify-center text-white text-sm shrink-0 shadow-sm">
                          <ExternalLink className="w-4 h-4" />
                        </div>
                        <div className="min-w-0">
                          <span className="text-xs font-bold text-slate-800 block">LinkedIn Profile</span>
                          <span className="text-[10px] text-slate-400 font-semibold truncate block">
                            {profile.user.linkedin_url.replace(/https?:\/\/(www\.)?linkedin\.com\/in\//, '')}
                          </span>
                        </div>
                      </div>
                      <ExternalLink className="w-3.5 h-3.5 text-slate-400 group-hover:text-slate-700 transition-colors" />
                    </a>
                  )}
                </div>
              )}
            </div>

            {/* DSA breakdown pie chart */}
            {dsaStats && (() => {
              const easy = dsaStats.difficulty_distribution.Easy || 0;
              const medium = dsaStats.difficulty_distribution.Medium || 0;
              const hard = dsaStats.difficulty_distribution.Hard || 0;
              const total = easy + medium + hard || 1;
              
              const pctEasy = (easy / total) * 100;
              const pctMedium = (medium / total) * 100;
              const pctHard = (hard / total) * 100;

              const radius = 30;
              const circumference = 2 * Math.PI * radius;
              const strokeEasy = circumference * (pctEasy / 100);
              const strokeMedium = circumference * (pctMedium / 100);
              const strokeHard = circumference * (pctHard / 100);

              return (
                <div className="p-5 rounded-3xl border border-slate-200 bg-white space-y-4 shadow-sm">
                  <h4 className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">DSA Breakdown</h4>
                  
                  <div className="flex items-center gap-4">
                    <div className="relative w-20 h-20 shrink-0">
                      <svg className="w-full h-full -rotate-90" viewBox="0 0 80 80">
                        <circle cx="40" cy="40" r={radius} fill="transparent" stroke="#f1f5f9" strokeWidth="8" />
                        {easy > 0 && (
                          <circle 
                            cx="40" cy="40" r={radius} fill="transparent" 
                            stroke="#10b981" strokeWidth="8" 
                            strokeDasharray={`${strokeEasy} ${circumference - strokeEasy}`}
                            strokeDashoffset={0}
                          />
                        )}
                        {medium > 0 && (
                          <circle 
                            cx="40" cy="40" r={radius} fill="transparent" 
                            stroke="#f59e0b" strokeWidth="8" 
                            strokeDasharray={`${strokeMedium} ${circumference - strokeMedium}`}
                            strokeDashoffset={-strokeEasy}
                          />
                        )}
                        {hard > 0 && (
                          <circle 
                            cx="40" cy="40" r={radius} fill="transparent" 
                            stroke="#ef4444" strokeWidth="8" 
                            strokeDasharray={`${strokeHard} ${circumference - strokeHard}`}
                            strokeDashoffset={-(strokeEasy + strokeMedium)}
                          />
                        )}
                      </svg>
                      <div className="absolute inset-0 flex flex-col items-center justify-center">
                        <span className="text-sm font-black text-slate-800">{easy + medium + hard}</span>
                        <span className="text-[8px] text-slate-400 font-bold uppercase">solved</span>
                      </div>
                    </div>
                    
                    <div className="flex-1 space-y-2">
                      {[
                        { label: 'Easy', val: easy, pct: pctEasy, color: 'bg-emerald-500' },
                        { label: 'Medium', val: medium, pct: pctMedium, color: 'bg-amber-500' },
                        { label: 'Hard', val: hard, pct: pctHard, color: 'bg-rose-500' },
                      ].map((item) => (
                        <div key={item.label} className="text-xs">
                          <div className="flex justify-between items-center text-[10px] text-slate-500 mb-0.5">
                            <span className="font-semibold flex items-center gap-1">
                              <span className={`w-1.5 h-1.5 rounded-full ${item.color}`} />
                              {item.label}
                            </span>
                            <span className="font-extrabold text-slate-700">{item.val}</span>
                          </div>
                          <div className="h-1 bg-slate-100 rounded-full overflow-hidden">
                            <div className={`h-full ${item.color}`} style={{ width: `${item.pct}%` }} />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              );
            })()}

            {/* Stats */}
            <div className="grid grid-cols-2 gap-4">
              <div className="p-5 rounded-2xl border border-slate-200 bg-white text-center shadow-sm">
                <Flame className="w-6 h-6 text-amber-500 fill-amber-500/10 mx-auto mb-1" />
                <h4 className="text-xl font-black text-slate-800">{profile.user.dsa_streak}</h4>
                <span className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider block">Streak</span>
              </div>
              <div className="p-5 rounded-2xl border border-slate-200 bg-white text-center shadow-sm">
                <Trophy className="w-6 h-6 text-indigo-600 mx-auto mb-1" />
                <h4 className="text-xl font-black text-slate-800">{profile.user.dsa_total_solved}</h4>
                <span className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider block">DSA Solved</span>
              </div>
            </div>
          </div>

          {/* Main profile content */}
          <div className="lg:col-span-2 space-y-6">
            {isEditing ? (
              <form onSubmit={handleSave} className="p-6 rounded-3xl border border-slate-200 bg-white space-y-4 shadow-sm">
                <div className="flex justify-between items-center pb-2 border-b border-slate-100">
                  <h3 className="font-bold text-base text-slate-850">Edit Profile Details</h3>
                  <button 
                    type="button" 
                    onClick={() => setIsEditing(false)}
                    className="text-xs text-slate-500 hover:text-slate-800 font-semibold"
                  >
                    Cancel
                  </button>
                </div>

                {error && (
                  <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-600 text-xs">
                    {error}
                  </div>
                )}

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1 col-span-2">
                    <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Display Name</label>
                    <input
                      type="text"
                      value={displayName}
                      onChange={(e) => setDisplayName(e.target.value)}
                      className="w-full bg-white border border-slate-200 rounded-xl py-2 px-4 text-sm text-slate-900 focus:outline-none focus:border-indigo-500 transition-colors"
                    />
                  </div>
                  
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider">College</label>
                    <input
                      type="text"
                      value={college}
                      onChange={(e) => setCollege(e.target.value)}
                      className="w-full bg-white border border-slate-200 rounded-xl py-2 px-4 text-sm text-slate-900 focus:outline-none focus:border-indigo-500 transition-colors"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Department</label>
                    <input
                      type="text"
                      value={department}
                      onChange={(e) => setDepartment(e.target.value)}
                      className="w-full bg-white border border-slate-200 rounded-xl py-2 px-4 text-sm text-slate-900 focus:outline-none focus:border-indigo-500 transition-colors"
                    />
                  </div>

                  <div className="space-y-1 col-span-2">
                    <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Bio</label>
                    <textarea
                      value={bio}
                      onChange={(e) => setBio(e.target.value)}
                      rows={3}
                      className="w-full bg-white border border-slate-200 rounded-xl py-2 px-4 text-sm text-slate-900 focus:outline-none focus:border-indigo-500 transition-colors resize-none"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider">GitHub URL</label>
                    <input
                      type="url"
                      value={githubUrl}
                      onChange={(e) => setGithubUrl(e.target.value)}
                      className="w-full bg-white border border-slate-200 rounded-xl py-2 px-4 text-sm text-slate-900 focus:outline-none focus:border-indigo-500 transition-colors"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider">LinkedIn URL</label>
                    <input
                      type="url"
                      value={linkedinUrl}
                      onChange={(e) => setLinkedinUrl(e.target.value)}
                      className="w-full bg-white border border-slate-200 rounded-xl py-2 px-4 text-sm text-slate-900 focus:outline-none focus:border-indigo-500 transition-colors"
                    />
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={saving}
                  className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-2.5 rounded-xl transition-all shadow-md shadow-indigo-600/10 flex items-center justify-center gap-1.5"
                >
                  <Save className="w-4 h-4" /> {saving ? 'Saving...' : 'Save Profile Changes'}
                </button>
              </form>
            ) : (
              <div className="space-y-4">
                <h3 className="font-bold text-lg text-slate-800">Projects Showcase</h3>
                {profile.apps.length === 0 ? (
                  <div className="border border-dashed border-slate-200 p-8 text-center rounded-2xl bg-white shadow-sm">
                    <p className="text-slate-500 text-xs">No projects listed yet.</p>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 gap-3">
                    {profile.apps.map((app) => (
                      <div key={app.id} className="p-4 rounded-xl border border-slate-200 bg-white flex justify-between items-center gap-4 hover:border-slate-350 transition-all shadow-sm">
                        <div>
                          <span className="font-bold text-sm text-slate-800 block">{app.name}</span>
                          <span className="text-[10px] text-slate-500 block truncate max-w-md">
                            {app.description || 'No description provided.'}
                          </span>
                        </div>
                        {app.status === 'RUNNING' && (
                          <a 
                            href={`http://${app.name}.quad.localhost:8000`} 
                            target="_blank" 
                            rel="noopener noreferrer"
                            className="p-1.5 rounded bg-white hover:bg-slate-50 text-slate-500 hover:text-slate-700 border border-slate-200 transition-colors shadow-sm"
                          >
                            <ExternalLink className="w-3.5 h-3.5" />
                          </a>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                <h3 className="font-bold text-lg text-slate-800 pt-2">Recent Activity</h3>
                {recentPosts.length === 0 ? (
                  <div className="border border-dashed border-slate-205 border-slate-200 p-6 text-center rounded-2xl bg-white shadow-sm">
                    <p className="text-slate-500 text-xs">No recent posts.</p>
                  </div>
                ) : (
                  <div className="relative border-l border-slate-200 ml-3.5 pl-6 space-y-4">
                    {recentPosts.map((p) => (
                      <div key={p.post_id} className="relative group">
                        {/* Dot */}
                        <div className="absolute -left-[31px] top-1.5 w-2.5 h-2.5 rounded-full bg-white border-2 border-indigo-650 shadow-sm transition-transform group-hover:scale-125" />
                        <div className="p-4 rounded-2xl border border-slate-200 bg-white hover:border-slate-350 transition-all shadow-sm">
                          <p className="text-xs text-slate-700 font-medium leading-relaxed">{p.content}</p>
                          <span className="text-[10px] text-slate-400 font-bold block mt-2">
                            {new Date(p.created_at).toLocaleString()}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
export default ProfilePage;
