import React from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../lib/auth';
import { CloudLightning, Shield, Zap, ArrowRight, Globe, CheckSquare, Trophy, Terminal } from 'lucide-react';

const FEATURES = [
  {
    icon: CloudLightning,
    title: 'Auto-Stack Detection',
    desc: 'Upload a ZIP or connect a Git repo. Quad auto-detects Node, Python, Java, or Static HTML and compiles a build recipe in seconds.',
    color: 'text-indigo-600',
    bg: 'bg-indigo-50',
  },
  {
    icon: Zap,
    title: 'Scale-to-Zero',
    desc: 'Idle containers are reaped automatically. The proxy wakes them instantly on the next request — zero manual intervention.',
    color: 'text-violet-600',
    bg: 'bg-violet-50',
  },
  {
    icon: Shield,
    title: 'Secure Tunnels',
    desc: 'Expose any local port to the internet via frp-powered tunnels. Get a public subdomain with one click.',
    color: 'text-emerald-600',
    bg: 'bg-emerald-50',
  },
  {
    icon: Terminal,
    title: 'AI Deploy Doctor',
    desc: 'Build failed? Paste your logs and let the AI diagnose the root cause and suggest a fix immediately.',
    color: 'text-rose-600',
    bg: 'bg-rose-50',
  },
  {
    icon: CheckSquare,
    title: 'DSA Tracker',
    desc: 'Track your LeetCode / competitive programming progress and compete on department-wide leaderboards.',
    color: 'text-fuchsia-600',
    bg: 'bg-fuchsia-50',
  },
  {
    icon: Trophy,
    title: 'Hackathons & Showcase',
    desc: 'Host and join hackathons, submit projects, vote for the best apps, and build a public developer portfolio.',
    color: 'text-amber-600',
    bg: 'bg-amber-50',
  },
];

export const LandingPage: React.FC = () => {
  const { isAuthenticated } = useAuth();

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col selection:bg-indigo-100 selection:text-indigo-900">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-md border-b border-slate-200/80">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-indigo-600 flex items-center justify-center text-white font-black text-sm shadow-md shadow-indigo-600/20">
              Q
            </div>
            <span className="font-extrabold text-slate-900 text-lg tracking-tight">Quad</span>
          </Link>

          <nav className="hidden md:flex items-center gap-8 text-sm font-semibold text-slate-600">
            <Link to="/showcase" className="hover:text-indigo-600 transition-colors">Showcase</Link>
            <Link to="/leaderboard" className="hover:text-indigo-600 transition-colors">Leaderboard</Link>
            <Link to="/hackathons" className="hover:text-indigo-600 transition-colors">Hackathons</Link>
          </nav>

          <div className="flex items-center gap-3">
            {isAuthenticated ? (
              <Link
                to="/dashboard"
                className="inline-flex items-center gap-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-bold px-4 py-2 rounded-xl transition-all shadow-md shadow-indigo-600/10 hover:shadow-indigo-600/20 hover:-translate-y-0.5"
              >
                Dashboard <ArrowRight size={14} />
              </Link>
            ) : (
              <>
                <Link
                  to="/auth"
                  className="text-sm font-semibold text-slate-700 hover:text-indigo-600 px-3 py-2 rounded-xl hover:bg-slate-100/80 transition-colors"
                >
                  Sign in
                </Link>
                <Link
                  to="/auth"
                  className="text-sm font-bold bg-indigo-600 hover:bg-indigo-700 text-white px-4.5 py-2.5 rounded-xl transition-all shadow-md shadow-indigo-600/10 hover:shadow-indigo-600/20 hover:-translate-y-0.5"
                >
                  Get started
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      {/* Hero */}
      <main className="flex-1 relative overflow-hidden">
        {/* Subtle decorative mesh background */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full max-w-7xl h-[500px] pointer-events-none opacity-40 mix-blend-multiply filter blur-3xl bg-gradient-to-r from-indigo-300 via-purple-300 to-pink-200 rounded-full" />
        
        <section className="max-w-6xl mx-auto px-6 pt-28 pb-20 text-center relative z-10">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-indigo-50 border border-indigo-200/80 text-indigo-700 text-xs font-bold mb-8 shadow-sm">
            <Zap size={12} className="fill-indigo-700/20 text-indigo-600 animate-pulse" />
            Self-Hosted App Engine for Students &amp; Teams
          </div>

          <h1 className="text-5xl md:text-7xl font-black tracking-tight text-slate-900 mb-6 leading-[1.08] max-w-4xl mx-auto">
            Deploy, tunnel, and{' '}
            <span className="premium-text-gradient">collaborate</span>
            <br />on your own cloud.
          </h1>

          <p className="text-slate-500 text-lg md:text-xl max-w-2xl mx-auto mb-10 leading-relaxed font-medium">
            Quad is a premium student app-engine. Deploys full-stack apps natively, routes custom subdomains via secure tunnels, and supports DSA streaks and team hackathons.
          </p>

          <div className="flex flex-col sm:flex-row gap-4.5 justify-center items-center">
            <Link
              to={isAuthenticated ? '/dashboard' : '/auth'}
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-750 text-white font-extrabold px-8 py-4 rounded-2xl transition-all text-base shadow-lg shadow-indigo-600/20 hover:shadow-indigo-650/35 hover:-translate-y-0.5"
            >
              Get started free <ArrowRight size={16} />
            </Link>
            <Link
              to="/showcase"
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 bg-white hover:bg-slate-50 border border-slate-250 text-slate-800 font-bold px-8 py-4 rounded-2xl transition-all text-base shadow-sm hover:shadow-md hover:-translate-y-0.5"
            >
              <Globe size={16} className="text-indigo-600" /> View showcase
            </Link>
          </div>

          {/* Social proof strip */}
          <div className="mt-16 flex items-center justify-center gap-8 flex-wrap text-sm text-slate-400 font-semibold">
            {['Node.js', 'Python', 'Java', 'Static HTML', 'Docker', 'frp Tunnels'].map((s) => (
              <span key={s} className="inline-flex items-center gap-2 px-3 py-1 bg-white border border-slate-200/60 rounded-lg shadow-sm">
                <span className="w-2 h-2 rounded-full bg-emerald-500" />
                {s}
              </span>
            ))}
          </div>
        </section>

        {/* Dashboard preview placeholder */}
        <section className="max-w-5xl mx-auto px-6 mb-28 relative z-10">
          <div className="rounded-2xl border border-slate-200/80 bg-white overflow-hidden shadow-xl hover:shadow-2xl transition-all duration-300">
            <div className="h-10 bg-slate-550 border-b border-slate-100 flex items-center gap-2 px-5 bg-slate-50/80">
              <span className="w-3.5 h-3.5 rounded-full bg-rose-400" />
              <span className="w-3.5 h-3.5 rounded-full bg-amber-400" />
              <span className="w-3.5 h-3.5 rounded-full bg-emerald-400" />
              <span className="ml-4 text-xs text-slate-400 font-mono font-medium">quad · dashboard</span>
            </div>
            <div className="p-8 grid grid-cols-1 md:grid-cols-3 gap-6 bg-slate-50/20">
              {['my-portfolio', 'api-server', 'ml-demo'].map((name, i) => (
                <div key={name} className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm hover:shadow-md transition-all">
                  <div className="flex items-center justify-between mb-4">
                    <span className="font-bold text-slate-900 text-sm">{name}</span>
                    <span className={`text-xs px-2.5 py-0.5 rounded-full font-bold border ${
                      i === 0 ? 'bg-emerald-50 text-emerald-700 border-emerald-250' :
                      i === 1 ? 'bg-indigo-50 text-indigo-700 border-indigo-250 animate-pulse' :
                      'bg-slate-100 text-slate-500 border-slate-200'
                    }`}>
                      {i === 0 ? 'RUNNING' : i === 1 ? 'BUILDING' : 'STOPPED'}
                    </span>
                  </div>
                  <div className="text-xs text-slate-400 font-mono font-bold uppercase tracking-wider">{['static', 'node:18', 'python:3.11'][i]}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Features */}
        <section className="max-w-6xl mx-auto px-6 pb-28 relative z-10">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-extrabold text-slate-900 mb-3 tracking-tight">Everything in one place</h2>
            <p className="text-slate-500 text-base md:text-lg max-w-md mx-auto font-medium">
              From deployment to community — Quad is the complete platform for student builders.
            </p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {FEATURES.map((f) => {
              const Icon = f.icon;
              return (
                <div key={f.title} className="p-7 rounded-3xl bg-white border border-slate-200 hover:border-indigo-200 hover:shadow-md transition-all duration-300 group">
                  <div className={`w-12 h-12 rounded-2xl ${f.bg} flex items-center justify-center mb-5 shadow-sm group-hover:scale-110 transition-transform duration-300`}>
                    <Icon size={22} className={f.color} />
                  </div>
                  <h3 className="font-extrabold text-slate-900 text-base mb-2.5">{f.title}</h3>
                  <p className="text-slate-500 text-sm leading-relaxed font-medium">{f.desc}</p>
                </div>
              );
            })}
          </div>
        </section>

        {/* CTA */}
        <section className="border-t border-slate-200/80 bg-white py-24 relative z-10">
          <div className="max-w-3xl mx-auto text-center px-6">
            <h2 className="text-4xl font-black text-slate-900 mb-4 tracking-tight">Ready to build?</h2>
            <p className="text-slate-550 mb-8 font-medium text-lg">Create your account and deploy your first app in under 5 minutes.</p>
            <Link
              to={isAuthenticated ? '/dashboard' : '/auth'}
              className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white font-extrabold px-9 py-4.5 rounded-2xl transition-all text-base shadow-lg shadow-indigo-600/15 hover:shadow-indigo-650/30 hover:-translate-y-0.5"
            >
              {isAuthenticated ? 'Go to Dashboard' : 'Start for free'} <ArrowRight size={16} />
            </Link>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-200/80 bg-slate-50 py-8 text-center text-sm text-slate-400 font-semibold">
        <div className="flex items-center justify-center gap-2">
          <div className="w-6 h-6 rounded-lg bg-indigo-600 flex items-center justify-center text-white font-black text-xs shadow-sm shadow-indigo-600/10">Q</div>
          <span>Quad · Self-Hosted Platform · {new Date().getFullYear()}</span>
        </div>
      </footer>
    </div>
  );
};
export default LandingPage;
