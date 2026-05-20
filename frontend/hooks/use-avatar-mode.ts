"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  deleteAvatarProfile,
  getAvatarProfile,
  updateAvatarProfile,
  type AvatarProfilePatch,
} from "@/lib/avatar-mode-api";

export const avatarProfileQueryKey = ["avatar-mode", "profile"] as const;

export function useAvatarProfile() {
  return useQuery({
    queryKey: avatarProfileQueryKey,
    queryFn: getAvatarProfile,
    staleTime: 5 * 60 * 1000,
    gcTime: 30 * 60 * 1000,
    refetchOnWindowFocus: false,
  });
}

export function useUpdateAvatarProfile() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (patch: AvatarProfilePatch) => updateAvatarProfile(patch),
    onSuccess: (profile) => {
      queryClient.setQueryData(avatarProfileQueryKey, profile);
      void queryClient.invalidateQueries({ queryKey: avatarProfileQueryKey });
    },
  });
}

export function useDeleteAvatarProfile() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: deleteAvatarProfile,
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: avatarProfileQueryKey });
      void queryClient.invalidateQueries({ queryKey: avatarProfileQueryKey });
    },
  });
}
