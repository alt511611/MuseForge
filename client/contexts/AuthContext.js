"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { createClient } from "../lib/supabase";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  // Memoized so we don't call createClient() fresh on every render, and so
  // it's created lazily rather than as a top-level module side effect.
  const supabase = useMemo(() => createClient(), []);
  const authConfigured = supabase !== null;

  const [user, setUser] = useState(null);
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(authConfigured);

  useEffect(() => {
    if (!supabase) {
      // Supabase isn't configured (no NEXT_PUBLIC_SUPABASE_URL/ANON_KEY) —
      // treat everyone as logged out instead of crashing. This keeps public
      // pages (landing, pricing, legal) working even before auth is wired up.
      setLoading(false);
      return;
    }

    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session);
      setUser(session?.user ?? null);
      setLoading(false);
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session);
      setUser(session?.user ?? null);
    });

    return () => subscription.unsubscribe();
  }, [supabase]);

  const requireAuth = () => {
    if (!supabase) {
      throw new Error(
        "Authentication is not configured (missing NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY)."
      );
    }
    return supabase;
  };

  const signInWithEmail = (email, password) =>
    requireAuth().auth.signInWithPassword({ email, password });

  const signUpWithEmail = (email, password) =>
    requireAuth().auth.signUp({ email, password });

  const signInWithGoogle = () =>
    requireAuth().auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: `${window.location.origin}/auth/callback` },
    });

  const signOut = () => (supabase ? supabase.auth.signOut() : Promise.resolve());

  const getAccessToken = async () => {
    if (!supabase) return null;
    const { data } = await supabase.auth.getSession();
    return data?.session?.access_token ?? null;
  };

  const isAdmin =
    user?.app_metadata?.role === "admin" ||
    user?.user_metadata?.role === "admin";

  return (
    <AuthContext.Provider
      value={{
        user,
        session,
        loading,
        isAdmin,
        authConfigured,
        signInWithEmail,
        signUpWithEmail,
        signInWithGoogle,
        signOut,
        getAccessToken,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
