import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  changePassword,
  disconnectGoogle,
  requestPasswordReset,
  updateProfile,
  type CurrentUser,
} from '../api/auth'
import { getApiErrorMessage } from '../api/errors'
import { AuthNotice } from '../components/AuthNotice'
import { GoogleButton } from '../components/GoogleButton'
import { GoogleIcon } from '../components/GoogleIcon'
import { useCurrentUser } from '../hooks/useAuth'
import { useDraft } from '../hooks/useDraftSaves'

export function ProfilePage() {
  const { user } = useCurrentUser()
  const queryClient = useQueryClient()
  const [name, setName] = useState(user?.full_name ?? '')
  const [password, setPassword] = useState({
    current_password: '',
    new_password: '',
    confirm_password: '',
  })
  const [disconnectPassword, setDisconnectPassword] = useState('')
  const [disconnectOpen, setDisconnectOpen] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    setName(user?.full_name ?? '')
  }, [user?.full_name])
  const success = (current: CurrentUser, text: string) => {
    queryClient.setQueryData(['auth', 'me'], current)
    setMessage(text)
    setError(null)
  }
  const failure = (error: unknown) => {
    setError(getApiErrorMessage(error))
    setMessage(null)
  }
  const profile = useMutation({
    mutationFn: () => updateProfile(name),
    onSuccess: (current) => success(current, 'Name saved.'),
    onError: failure,
  })
  const passwordMutation = useMutation({
    mutationFn: () => changePassword(password),
    onSuccess: (current) => {
      setPassword({ current_password: '', new_password: '', confirm_password: '' })
      success(current, 'Password changed. Other sessions have been signed out.')
    },
    onError: failure,
  })
  const disconnect = useMutation({
    mutationFn: () => disconnectGoogle(disconnectPassword),
    onSuccess: (current) => {
      setDisconnectOpen(false)
      setDisconnectPassword('')
      success(current, 'Google disconnected. Sign in with your email and password.')
    },
    onError: failure,
  })
  const reset = useMutation({
    mutationFn: () => requestPasswordReset(user!.email),
    onSuccess: (result) => {
      setMessage(result.detail)
      setError(null)
    },
    onError: failure,
  })
  const busy =
    profile.isPending || passwordMutation.isPending || disconnect.isPending || reset.isPending
  useDraft('profile-name', {
    dirty: name !== user?.full_name,
    validate: () => {
      if (!name.trim()) throw new Error('Enter your name before saving.')
    },
    save: () => profile.mutateAsync(),
  })
  useDraft('profile-password', {
    dirty: Object.values(password).some(Boolean),
    validate: () => {
      if (
        !password.current_password ||
        !password.new_password ||
        password.new_password !== password.confirm_password
      )
        throw new Error('Finish the password fields and confirm the new password, or clear them.')
    },
    save: () => passwordMutation.mutateAsync(),
  })
  const googleAccount = user?.connected_accounts.find((account) => account.provider === 'google')
  return (
    <div className="max-w-2xl space-y-6">
      <AuthNotice />
      {message && (
        <p role="status" className="rounded-2xl bg-emerald-50 p-4 text-sm text-emerald-800">
          {message}
        </p>
      )}
      {error && (
        <p role="alert" className="rounded-2xl bg-rose-50 p-4 text-sm text-rose-700">
          {error}
        </p>
      )}
      <section className="rounded-3xl border border-slate-200 bg-white p-6">
        <h1 className="section-title">Your profile</h1>
        <form
          className="mt-6 space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            profile.mutate()
          }}
        >
          <fieldset disabled={busy} className="space-y-4">
            <label className="block text-sm font-medium">
              Name
              <input
                required
                maxLength={255}
                autoComplete="name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                className="mt-2 w-full rounded-xl border p-3"
              />
            </label>
            <p className="text-sm text-slate-600">Email: {user?.email}</p>
            <button type="submit" className="workflow-button">
              {profile.isPending ? 'Saving…' : 'Save name'}
            </button>
          </fieldset>
        </form>
      </section>
      <section className="rounded-3xl border border-slate-200 bg-white p-6">
        <h2 className="text-lg font-semibold">Password</h2>
        {user?.has_password ? (
          <form
            className="mt-5 space-y-4"
            onSubmit={(event) => {
              event.preventDefault()
              passwordMutation.mutate()
            }}
          >
            <fieldset disabled={busy} className="space-y-4">
              {(
                [
                  ['current_password', 'Current password'],
                  ['new_password', 'New password'],
                  ['confirm_password', 'Confirm new password'],
                ] as const
              ).map(([key, label]) => (
                <label key={key} className="block text-sm font-medium">
                  {label}
                  <input
                    required
                    type="password"
                    autoComplete={key === 'current_password' ? 'current-password' : 'new-password'}
                    minLength={key === 'new_password' ? 8 : undefined}
                    value={password[key]}
                    onChange={(event) =>
                      setPassword((current) => ({ ...current, [key]: event.target.value }))
                    }
                    className="mt-2 w-full rounded-xl border p-3"
                  />
                </label>
              ))}
              <button type="submit" className="workflow-button">
                {passwordMutation.isPending ? 'Changing…' : 'Change password'}
              </button>
            </fieldset>
            <Link className="inline-block text-sm text-fuchsia-700 underline" to="/forgot-password">
              Forgot your password?
            </Link>
          </form>
        ) : (
          <div className="mt-4 space-y-3 text-sm text-slate-600">
            <p>
              You currently sign in with Google. Set a password through a link sent to your account
              email before disconnecting Google.
            </p>
            <button
              type="button"
              disabled={busy}
              onClick={() => reset.mutate()}
              className="workflow-button"
            >
              Send password setup link
            </button>
          </div>
        )}
      </section>
      <section className="rounded-3xl border border-slate-200 bg-white p-6">
        <h2 className="text-lg font-semibold">Connected accounts</h2>
        <p className="mt-2 text-sm text-slate-600">
          Connect Google to sign in to this account with your existing assignments and results.
        </p>
        {googleAccount ? (
          <div className="mt-5 space-y-4 rounded-2xl border bg-slate-50 p-4">
            <p className="flex items-center gap-2 font-medium">
              <GoogleIcon /> Google
            </p>
            <p className="break-all text-sm text-slate-600">{googleAccount.email}</p>
            {!user?.has_password ? (
              <p className="text-sm text-slate-600">
                Google is your only sign-in method. Set a password before disconnecting it.
              </p>
            ) : disconnectOpen ? (
              <form
                className="space-y-3"
                onSubmit={(event) => {
                  event.preventDefault()
                  disconnect.mutate()
                }}
              >
                <p className="text-sm text-slate-600">
                  Your assignments stay in this account. You will sign in with your email and
                  password.
                </p>
                <label className="block text-sm font-medium">
                  Password to disconnect Google
                  <input
                    required
                    type="password"
                    autoComplete="current-password"
                    value={disconnectPassword}
                    onChange={(event) => setDisconnectPassword(event.target.value)}
                    className="mt-2 w-full rounded-xl border p-3"
                  />
                </label>
                <button type="submit" disabled={busy} className="workflow-button">
                  Confirm disconnect
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    setDisconnectOpen(false)
                    setDisconnectPassword('')
                  }}
                  className="workflow-button ml-3"
                >
                  Cancel
                </button>
              </form>
            ) : (
              <button
                type="button"
                disabled={busy}
                onClick={() => setDisconnectOpen(true)}
                className="workflow-button"
              >
                Disconnect Google
              </button>
            )}
          </div>
        ) : (
          <div className="mt-5 max-w-sm">
            <GoogleButton process="connect" disabled={busy} />
          </div>
        )}
      </section>
    </div>
  )
}
