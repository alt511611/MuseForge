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
  // The signed-in user's profile row ({ plan, credits }), fetched once per
  // user here rather than independently in every component that needs it --
  // Navbar and IdeaForm each used to run their own `.from("profiles")` query
  // on the same page load, so a single landing-page visit hit the same row
  // twice. null means "not loaded yet or signed out".
  const [profile, setProfile] = useState(null);

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

  useEffect(() => {
    if (!supabase || !user) {
      setProfile(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        // Supabase JS returns query errors (RLS denial, 0/2+ rows from
        // .single()) as { data: null, error } rather than throwing, so check
        // `error` explicitly -- otherwise a denied read is indistinguishable
        // from "free plan, no credits" in the UI, with nothing logged to
        // diagnose it.
        const { data, error } = await supabase
          .from("profiles")
          .select("plan, credits")
          .eq("id", user.id)
          .single();
        if (cancelled) return;
        if (error) {
          console.error("Failed to fetch user profile (plan/credits UI will stay hidden):", error);
          return;
        }
        if (data) setProfile(data);
      } catch (err) {
        if (!cancelled) console.error("Failed to fetch user profile (network/client error):", err);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [supabase, user]);

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
    requireAuth().auth.signUp({
      email,
      password,
      options: {
        emailRedirectTo: `${window.location.origin}/auth/callback`,
      },
    });

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

  const resetPasswordForEmail = async (email) => {
    const client = requireAuth();
    return client.auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/auth/reset-password`,
    });
  };

  const updatePassword = async (newPassword) => {
    return requireAuth().auth.updateUser({ password: newPassword });
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
        profile,
        isAdmin,
        authConfigured,
        signInWithEmail,
        signUpWithEmail,
        signInWithGoogle,
        signOut,
        getAccessToken,
        resetPasswordForEmail,
        updatePassword,
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
