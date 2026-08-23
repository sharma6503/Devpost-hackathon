"use client";

import { useEffect, useState } from "react";
import { getUserProfile, setUserProfile, type UserProfile } from "@/lib/session";
import { LoginGate } from "@/components/landing/LoginGate";

/** Renders the app underneath a blurred overlay until a valid BigQuery-backed
 * login succeeds — the chat interface stays mounted, just visually blocked,
 * rather than swapping to a separate login page.
 * `undefined` means "haven't checked localStorage yet" (avoids a login-flash
 * on first paint); `null` means "checked, not logged in". */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const [profile, setProfile] = useState<UserProfile | null | undefined>(undefined);

  useEffect(() => {
    setProfile(getUserProfile());
  }, []);

  return (
    <>
      {children}
      {profile === null && (
        <LoginGate
          onSuccess={(p) => {
            // The dashboard behind this overlay already mounted and cached
            // the old auto-generated userId in its own state/effects before
            // login completed — a full reload is the only way to make every
            // one of those call sites pick up the freshly-authenticated
            // identity instead of just this component's local state.
            setUserProfile(p);
            window.location.reload();
          }}
        />
      )}
    </>
  );
}
