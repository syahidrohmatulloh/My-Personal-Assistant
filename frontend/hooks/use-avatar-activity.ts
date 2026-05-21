"use client";

import { useEffect, useState } from "react";

import {
  AVATAR_ACTIVITY_EVENT,
  type AvatarActivityDetail,
  type AvatarActivityState,
} from "@/lib/avatar-activity";

export function useAvatarActivity(): AvatarActivityState {
  const [state, setState] = useState<AvatarActivityState>("idle");

  useEffect(() => {
    function handleActivity(event: Event) {
      const detail = (event as CustomEvent<AvatarActivityDetail>).detail;
      if (!detail?.state) return;
      setState(detail.state);
    }

    window.addEventListener(AVATAR_ACTIVITY_EVENT, handleActivity);

    return () => {
      window.removeEventListener(AVATAR_ACTIVITY_EVENT, handleActivity);
    };
  }, []);

  return state;
}
