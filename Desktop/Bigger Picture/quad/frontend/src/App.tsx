import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './lib/auth';
import { Layout } from './components/Layout';

import LandingPage from './pages/LandingPage';
import AuthPage from './pages/AuthPage';
import Dashboard from './pages/Dashboard';
import DeployPage from './pages/DeployPage';
import TunnelPage from './pages/TunnelPage';
import ShowcasePage from './pages/ShowcasePage';
import LeaderboardPage from './pages/LeaderboardPage';
import DSATrackerPage from './pages/DSATrackerPage';
import ProfilePage from './pages/ProfilePage';
import AIPage from './pages/AIPage';
import DevPanelPage from './pages/DevPanelPage';
import FeedPage from './pages/FeedPage';
import FacultyDashboard from './pages/FacultyDashboard';
import HackathonPage from './pages/HackathonPage';

import NotFoundPage from './pages/NotFoundPage';

// Route Guard for authenticated routes
const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/auth" replace />;
  }

  return <Layout>{children}</Layout>;
};

const PublicLayoutRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated } = useAuth();
  if (isAuthenticated) {
    return <Layout>{children}</Layout>;
  }
  return <div className="min-h-screen bg-white text-gray-900">{children}</div>;
};

const RoleRoute: React.FC<{ roles: string[]; children: React.ReactNode }> = ({ roles, children }) => {
  const { isAuthenticated, isLoading, user } = useAuth();
  if (isLoading) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }
  if (!isAuthenticated) {
    return <Navigate to="/auth" replace />;
  }
  if (!user || !roles.includes(user.role)) {
    return <Navigate to="/dashboard" replace />;
  }
  return <Layout>{children}</Layout>;
};

export const App: React.FC = () => {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Public Landing Pages */}
          <Route path="/" element={<LandingPage />} />
          <Route path="/auth" element={<AuthPage />} />

          {/* Protected Routes */}
          <Route 
            path="/dashboard" 
            element={
              <ProtectedRoute>
                <Dashboard />
              </ProtectedRoute>
            } 
          />
          <Route 
            path="/deploy" 
            element={
              <ProtectedRoute>
                <DeployPage />
              </ProtectedRoute>
            } 
          />
          <Route 
            path="/tunnels" 
            element={
              <ProtectedRoute>
                <TunnelPage />
              </ProtectedRoute>
            } 
          />
          <Route
            path="/dsa"
            element={
              <PublicLayoutRoute>
                <DSATrackerPage />
              </PublicLayoutRoute>
            }
          />
          <Route
            path="/feed"
            element={
              <PublicLayoutRoute>
                <FeedPage />
              </PublicLayoutRoute>
            }
          />
          <Route
            path="/dev/:appName"
            element={
              <ProtectedRoute>
                <DevPanelPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/ai/:appName"
            element={
              <ProtectedRoute>
                <AIPage />
              </ProtectedRoute>
            }
          />

          {/* Optional Layout/Public Hybrid Routes */}
          <Route 
            path="/showcase" 
            element={
              <PublicLayoutRoute>
                <ShowcasePage />
              </PublicLayoutRoute>
            } 
          />
          <Route 
            path="/leaderboard" 
            element={
              <PublicLayoutRoute>
                <LeaderboardPage />
              </PublicLayoutRoute>
            } 
          />
          <Route 
            path="/profile" 
            element={
              <PublicLayoutRoute>
                <ProfilePage />
              </PublicLayoutRoute>
            } 
          />

          <Route
            path="/hackathons"
            element={
              <PublicLayoutRoute>
                <HackathonPage />
              </PublicLayoutRoute>
            }
          />
          <Route
            path="/faculty"
            element={
              <RoleRoute roles={['faculty', 'admin']}>
                <FacultyDashboard />
              </RoleRoute>
            }
          />

          {/* Catch All */}
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
};

export default App;
