import React, { createContext, useState, useEffect, useContext } from 'react';
import api from './api';

interface User {
  id: number;
  username: string;
  email: string;
  display_name?: string;
  avatar_initial: string;
  role: string;
  college?: string;
  department?: string;
  year_of_study?: number;
  bio?: string;
  github_url?: string;
  linkedin_url?: string;
  dsa_streak: number;
  dsa_total_solved: number;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (usernameOrEmail: string, password: string) => Promise<User>;
  register: (payload: any) => Promise<User>;
  logout: () => void;
  updateUser: (updatedUser: User) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Hydrate auth state from localStorage and verify with /auth/me
  useEffect(() => {
    const fetchMe = async () => {
      // OPEN TESTING MODE — skip auth, use testadmin
      const OPEN_TESTING = true;
      if (OPEN_TESTING) {
        const fakeToken = 'open-testing';
        localStorage.setItem('quad_token', fakeToken);
        setToken(fakeToken);
        try {
          const resp = await api.get('/auth/me');
          setUser(resp.data);
        } catch {
          setUser({ id: 6, username: 'testadmin', email: 'testadmin@quad.dev',
            avatar_initial: 'T', role: 'admin', dsa_streak: 0, dsa_total_solved: 0 });
        }
        setIsLoading(false);
        return;
      }

      const storedToken = localStorage.getItem('quad_token');
      if (storedToken) {
        setToken(storedToken);
        try {
          const resp = await api.get('/auth/me');
          setUser(resp.data);
        } catch (e) {
          // Token expired or invalid
          localStorage.removeItem('quad_token');
          setToken(null);
          setUser(null);
        }
      }
      setIsLoading(false);
    };

    fetchMe();

    // Listen to global logout event
    const handleGlobalLogout = () => {
      setToken(null);
      setUser(null);
    };
    window.addEventListener('quad_logout', handleGlobalLogout);
    return () => window.removeEventListener('quad_logout', handleGlobalLogout);
  }, []);

  const login = async (usernameOrEmail: string, password: string): Promise<User> => {
    const resp = await api.post('/auth/login', {
      username_or_email: usernameOrEmail,
      password
    });
    const { access_token, user: loggedUser } = resp.data;
    localStorage.setItem('quad_token', access_token);
    setToken(access_token);
    setUser(loggedUser);
    return loggedUser;
  };

  const register = async (payload: any): Promise<User> => {
    const resp = await api.post('/auth/register', payload);
    return resp.data;
  };

  const logout = async () => {
    try {
      await api.post('/auth/logout');
    } catch (e) {
      // Ignore errors on logout endpoint
    }
    localStorage.removeItem('quad_token');
    setToken(null);
    setUser(null);
  };

  const updateUser = (updatedUser: User) => {
    setUser(updatedUser);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: !!token,
        isLoading,
        login,
        register,
        logout,
        updateUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
