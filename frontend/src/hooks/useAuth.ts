import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { fetchCurrentUser, login, logout, register, type AuthPayload } from '../api/auth'
import { ApiError } from '../api/client'

export function useCurrentUser() {
  const query = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: fetchCurrentUser,
  })

  const user =
    query.isError && query.error instanceof ApiError && query.error.status === 401
      ? null
      : (query.data ?? null)

  return {
    ...query,
    user,
    isLoading: query.isPending,
  }
}

export function useLogin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: AuthPayload) => login(payload),
    onSuccess: (user) => {
      queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== 'auth' })
      queryClient.setQueryData(['auth', 'me'], user)
    },
  })
}

export function useRegister() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: AuthPayload) => register(payload),
    onSuccess: (user) => {
      queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== 'auth' })
      queryClient.setQueryData(['auth', 'me'], user)
    },
  })
}

export function useLogout() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: logout,
    onSuccess: () => {
      queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== 'auth' })
      queryClient.setQueryData(['auth', 'me'], null)
    },
  })
}
