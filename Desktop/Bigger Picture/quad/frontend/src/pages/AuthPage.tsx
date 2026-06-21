import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../lib/auth';
import { KeyRound, Mail, User, ShieldAlert, ArrowRight } from 'lucide-react';

const inputCls =
  'w-full bg-white border border-slate-200 rounded-xl px-4 py-3 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-50 transition-all font-semibold';

export const AuthPage: React.FC = () => {
  const [isRegister, setIsRegister] = useState(false);
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [role, setRole] = useState('student');
  const [college, setCollege] = useState('');
  const [department, setDepartment] = useState('');
  const [yearOfStudy, setYearOfStudy] = useState<number | undefined>(undefined);
  const [usernameOrEmail, setUsernameOrEmail] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const { login, register } = useAuth();
  const navigate = useNavigate();

  const handleToggle = () => { setIsRegister(!isRegister); setError(null); };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (isRegister) {
        await register({
          username, email, password, role,
          display_name: displayName || undefined,
          college: college || undefined,
          department: department || undefined,
          year_of_study: role === 'student' ? Number(yearOfStudy) : undefined,
        });
        await login(username, password);
      } else {
        await login(usernameOrEmail, password);
      }
      navigate('/dashboard');
    } catch (err: any) {
      setError(err.response?.data?.detail || err.response?.data?.error || 'Authentication failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center py-16 px-4 select-none">
      <div className="max-w-md w-full space-y-8">
        {/* Logo */}
        <div className="text-center">
          <Link to="/" className="inline-flex items-center gap-2.5 justify-center mb-6">
            <div className="w-9 h-9 rounded-xl bg-indigo-600 flex items-center justify-center text-white font-black text-base shadow-md shadow-indigo-600/20 hover:scale-105 transition-transform">
              Q
            </div>
            <span className="font-extrabold text-slate-900 text-xl tracking-tight">Quad</span>
          </Link>
          <h1 className="text-2xl font-black text-slate-900 tracking-tight">
            {isRegister ? 'Create your account' : 'Welcome back'}
          </h1>
          <p className="text-sm text-slate-500 mt-1 font-semibold">
            {isRegister ? 'Join the deployment platform' : 'Enter your credentials to continue'}
          </p>
        </div>

        <div className="bg-white border border-slate-200/80 rounded-3xl p-8 shadow-sm space-y-6">
          {error && (
            <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-sm flex items-start gap-2.5 font-semibold">
              <ShieldAlert size={16} className="shrink-0 mt-0.5 text-rose-500" />
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {isRegister ? (
              <>
                <div>
                  <label className="block text-xs font-bold text-slate-750 text-slate-700 uppercase tracking-wider mb-2">Username</label>
                  <div className="relative">
                    <User size={14} className="absolute left-4 top-3.5 text-slate-400" />
                    <input type="text" required value={username} onChange={e => setUsername(e.target.value)}
                      placeholder="john-doe" className={inputCls + ' pl-10'} />
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-750 text-slate-700 uppercase tracking-wider mb-2">Email address</label>
                  <div className="relative">
                    <Mail size={14} className="absolute left-4 top-3.5 text-slate-400" />
                    <input type="email" required value={email} onChange={e => setEmail(e.target.value)}
                      placeholder="john@example.com" className={inputCls + ' pl-10'} />
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-750 text-slate-700 uppercase tracking-wider mb-2">Display name <span className="text-slate-400 font-normal lowercase">(optional)</span></label>
                  <input type="text" value={displayName} onChange={e => setDisplayName(e.target.value)}
                    placeholder="John Doe" className={inputCls} />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-bold text-slate-750 text-slate-700 uppercase tracking-wider mb-2">Role</label>
                    <select value={role} onChange={e => setRole(e.target.value)} className={inputCls}>
                      <option value="student">Student</option>
                      <option value="faculty">Faculty</option>
                      <option value="admin">Admin</option>
                    </select>
                  </div>
                  {role === 'student' && (
                    <div>
                      <label className="block text-xs font-bold text-slate-750 text-slate-700 uppercase tracking-wider mb-2">Year of study</label>
                      <input type="number" min="1" max="5" value={yearOfStudy || ''}
                        onChange={e => setYearOfStudy(e.target.value ? Number(e.target.value) : undefined)}
                        placeholder="3" className={inputCls} />
                    </div>
                  )}
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-750 text-slate-700 uppercase tracking-wider mb-2">College <span className="text-slate-400 font-normal lowercase">(optional)</span></label>
                  <input type="text" value={college} onChange={e => setCollege(e.target.value)}
                    placeholder="Engineering College" className={inputCls} />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-750 text-slate-700 uppercase tracking-wider mb-2">Department <span className="text-slate-400 font-normal lowercase">(optional)</span></label>
                  <input type="text" value={department} onChange={e => setDepartment(e.target.value)}
                    placeholder="Computer Science" className={inputCls} />
                </div>
              </>
            ) : (
              <div>
                <label className="block text-xs font-bold text-slate-750 text-slate-700 uppercase tracking-wider mb-2">Username or email</label>
                <div className="relative">
                  <User size={14} className="absolute left-4 top-3.5 text-slate-400" />
                  <input type="text" required value={usernameOrEmail} onChange={e => setUsernameOrEmail(e.target.value)}
                    placeholder="john-doe" className={inputCls + ' pl-10'} />
                </div>
              </div>
            )}

            <div>
              <label className="block text-xs font-bold text-slate-750 text-slate-700 uppercase tracking-wider mb-2">Password</label>
              <div className="relative">
                <KeyRound size={14} className="absolute left-4 top-3.5 text-slate-400" />
                <input type="password" required value={password} onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••" className={inputCls + ' pl-10'} />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full mt-4 bg-indigo-600 hover:bg-indigo-700 text-white font-extrabold py-3.5 rounded-xl text-sm transition-all disabled:opacity-50 flex items-center justify-center gap-2 shadow-md shadow-indigo-600/10 hover:shadow-indigo-650/20 hover:-translate-y-0.5"
            >
              {loading ? (
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              ) : (
                <>{isRegister ? 'Create Account' : 'Sign In'} <ArrowRight size={14} /></>
              )}
            </button>
          </form>
        </div>

        <p className="text-center text-sm text-slate-500 font-semibold">
          {isRegister ? 'Already have an account?' : "Don't have an account?"}{' '}
          <button onClick={handleToggle} className="text-indigo-650 hover:text-indigo-750 font-bold transition-colors">
            {isRegister ? 'Sign in' : 'Register'}
          </button>
        </p>
      </div>
    </div>
  );
};
export default AuthPage;
