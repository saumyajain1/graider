import { useEffect, useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { getApiErrorMessage } from '../../api/errors'
import { useCurrentUser, useLogout } from '../../hooks/useAuth'

export function ProfileMenu() {
  const { user } = useCurrentUser()
  const logout = useLogout()
  const navigate = useNavigate()
  const details = useRef<HTMLDetailsElement>(null)

  useEffect(() => {
    const closeOutside = (event: PointerEvent) => {
      if (event.target instanceof Node && !details.current?.contains(event.target)) {
        details.current?.removeAttribute('open')
      }
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && details.current?.open) {
        details.current.removeAttribute('open')
        details.current.querySelector('summary')?.focus()
      }
    }
    document.addEventListener('pointerdown', closeOutside)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('pointerdown', closeOutside)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [])

  return (
    <details ref={details} className="relative z-20">
      <summary className="flex cursor-pointer list-none items-center gap-3 rounded-full border border-white/15 bg-white/10 px-3 py-2 text-sm transition hover:bg-white/20 [&::-webkit-details-marker]:hidden">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-fuchsia-100 font-semibold text-fuchsia-900">
          {(user?.full_name || user?.email || 'G').slice(0, 1).toUpperCase()}
        </span>
        <span className="max-w-[160px] truncate">{user?.full_name || 'Your account'}</span>
        <svg aria-hidden="true" viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor">
          <path d="m5 7 5 5 5-5H5Z" />
        </svg>
        <span className="sr-only">Open profile menu</span>
      </summary>
      <div className="absolute left-0 mt-3 w-72 max-w-[calc(100vw-3rem)] rounded-2xl border border-slate-200 bg-white p-5 text-slate-900 shadow-xl md:right-0 md:left-auto">
        <p className="break-words font-semibold">{user?.full_name || 'Your account'}</p>
        <p className="mt-1 break-all text-sm text-slate-500">{user?.email}</p>
        <div className="my-4 border-y border-slate-100 py-3">
          <p className="text-xs font-semibold tracking-wide text-slate-500 uppercase">
            Connected accounts
          </p>
          {user?.connected_accounts.length ? (
            user.connected_accounts.map((account) => (
              <div key={account.provider} className="mt-2 text-sm">
                <p className="font-medium capitalize">{account.provider}</p>
                <p className="break-all text-xs text-slate-500">{account.email}</p>
              </div>
            ))
          ) : (
            <p className="mt-2 text-sm text-slate-500">None connected</p>
          )}
        </div>
        <Link
          to="/profile"
          onClick={() => details.current?.removeAttribute('open')}
          className="block rounded-xl px-3 py-2 text-sm font-medium transition hover:bg-slate-100"
        >
          Manage account
        </Link>
        <button
          type="button"
          disabled={logout.isPending}
          onClick={() =>
            logout.mutate(undefined, { onSuccess: () => navigate('/login', { replace: true }) })
          }
          className="mt-1 w-full rounded-xl px-3 py-2 text-left text-sm font-medium transition hover:bg-slate-100 disabled:opacity-60"
        >
          {logout.isPending ? 'Signing out…' : 'Sign out'}
        </button>
        {logout.isError ? (
          <p role="alert" className="mt-3 text-sm text-rose-700">
            {getApiErrorMessage(logout.error, 'Could not sign out. Please try again.')}
          </p>
        ) : null}
      </div>
    </details>
  )
}
