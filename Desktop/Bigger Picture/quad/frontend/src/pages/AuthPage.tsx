import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../lib/auth';
import { KeyRound, Mail, User, ShieldAlert, ArrowRight } from 'lucide-react';

const inputCls =
  'w-full bg-white border border-gray-200 rounded-lg px-3 py-2.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition';

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
    <div className="min-h-screen bg-gray-50 flex items-center justify-center py-12 px-4">
      <div className="max-w-md w-full">
        {/* Logo */}
        <div className="text-center mb-8">
          <Link to="/" className="inline-flex items-center gap-2 justify-center mb-6">
            <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center text-white font-black text-sm">Q</div>
            <span className="font-bold text-gray-900 text-lg">Quad</span>
          </Link>
          <h1 className="text-2xl font-bold text-gray-900">
            {isRegister ? 'Create your account' : 'Sign in to Quad'}
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            {isRegister ? 'Join the deployment platform' : 'Enter your credentials to continue'}
          </p>
        </div>

        <div className="bg-white border border-gray-200 rounded-2xl p-6 shadow-sm">
          {error && (
            <div className="mb-4 p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm flex items-start gap-2">
              <ShieldAlert size={15} className="shrink-0 mt-0.5" />
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {isRegister ? (
              <>
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1.5">Username</label>
                  <div className="relative">
                    <User size={14} className="absolute left-3 top-3 text-gray-400" />
                    <input type="text" required value={username} onChange={e => setUsername(e.target.value)}
                      placeholder="john-doe" className={inputCls + ' pl-9'} />
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1.5">Email address</label>
                  <div className="relative">
                    <Mail size={14} className="absolute left-3 top-3 text-gray-400" />
                    <input type="email" required value={email} onChange={e => setEmail(e.target.value)}
                      placeholder="john@example.com" className={inputCls + ' pl-9'} />
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1.5">Display name <span className="text-gray-400 font-normal">(optional)</span></label>
                  <input type="text" value={displayName} onChange={e => setDisplayName(e.target.value)}
                    placeholder="John Doe" className={inputCls} />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-gray-700 mb-1.5">Role</label>
                    <select value={role} onChange={e => setRole(e.target.value)} className={inputCls}>
                      <option value="student">Student</option>
                      <option value="faculty">Faculty</option>
                      <option value="admin">Admin</option>
                    </select>
                  </div>
                  {role === 'student' && (
                    <div>
                      <label className="block text-xs font-semibold text-gray-700 mb-1.5">Year of study</label>
                      <input type="number" min="1" max="5" value={yearOfStudy || ''}
                        onChange={e => setYearOfStudy(e.target.value ? Number(e.target.value) : undefined)}
                        placeholder="3" className={inputCls} />
                    </div>
                  )}
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1.5">College <span className="text-gray-400 font-normal">(optional)</span></label>
                  <input type="text" value={college} onChange={e => setCollege(e.target.value)}
                    placeholder="Engineering College" className={inputCls} />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1.5">Department <span className="text-gray-400 font-normal">(optional)</span></label>
                  <input type="text" value={department} onChange={e => setDepartment(e.target.value)}
                    placeholder="Computer Science" className={inputCls} />
                </div>
              </>
            ) : (
              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1.5">Username or email</label>
                <div className="relative">
                  <User size={14} className="absolute left-3 top-3 text-gray-400" />
                  <input type="text" required value={usernameOrEmail} onChange={e => setUsernameOrEmail(e.target.value)}
                    placeholder="john-doe" className={inputCls + ' pl-9'} />
                </div>
              </div>
            )}

            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1.5">Password</label>
              <div className="relative">
                <KeyRound size={14} className="absolute left-3 top-3 text-gray-400" />
                <input type="password" required value={password} onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••" className={inputCls + ' pl-9'} />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full mt-2 bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2.5 rounded-lg text-sm transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {loading ? (
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              ) : (
                <>{isRegister ? 'Create account' : 'Sign in'} <ArrowRight size={14} /></>
              )}
            </button>
          </form>
        </div>

        <p className="text-center text-sm text-gray-500 mt-4">
          {isRegister ? 'Already have an account?' : "Don't have an account?"}{' '}
          <button onClick={handleToggle} className="text-blue-600 hover:text-blue-700 font-semibold transition-colors">
            {isRegister ? 'Sign in' : 'Register'}
          </button>
        </p>
      </div>
    </div>
  );
};
export default AuthPage;
