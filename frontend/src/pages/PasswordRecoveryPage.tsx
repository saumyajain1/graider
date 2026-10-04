import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { confirmPasswordReset, requestPasswordReset } from '../api/auth'
import { getApiErrorMessage } from '../api/errors'
import { useAuthOptions } from '../hooks/useAuth'

export function PasswordRecoveryPage({ confirm = false }: { confirm?: boolean }) {
  const options = useAuthOptions()
  const queryClient = useQueryClient()
  const [credentials] = useState(() => window.location.hash.slice(1).split('/'))
  const [email, setEmail] = useState('')
  const [passwords, setPasswords] = useState({ new_password: '', confirm_password: '' })
  const mutation = useMutation({
    mutationFn: () =>
      confirm
        ? confirmPasswordReset({
            uid: credentials[0] ?? '',
            token: credentials[1] ?? '',
            ...passwords,
          })
        : requestPasswordReset(email),
    onSuccess: () => {
      if (confirm) queryClient.removeQueries({ queryKey: ['auth', 'me'] })
    },
  })
  useEffect(() => {
    document.title = `${confirm ? 'Reset password' : 'Password recovery'} | Graider`
  }, [confirm])
  const validLink = credentials.length === 2 && credentials.every(Boolean)
  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <section className="app-card w-full max-w-lg p-8">
        <p className="text-sm font-semibold text-fuchsia-700">Graider</p>
        <h1 className="section-title mt-3">
          {confirm ? 'Set a new password' : 'Forgot your password?'}
        </h1>
        <p className="mt-3 text-sm text-slate-600">
          {confirm
            ? 'Choose a password with at least eight characters. Your other sessions will be signed out.'
            : 'Enter your account email to receive a password reset link.'}
        </p>
        {confirm && !validLink ? (
          <p role="alert" className="mt-5 text-sm text-rose-700">
            This reset link is incomplete. Request a new link.
          </p>
        ) : mutation.isSuccess ? (
          <p role="status" className="mt-5 text-sm text-emerald-800">
            {mutation.data.detail}
          </p>
        ) : (
          <form
            className="mt-6 space-y-4"
            onSubmit={(event) => {
              event.preventDefault()
              mutation.mutate()
            }}
          >
            <fieldset disabled={mutation.isPending || options.isPending} className="space-y-4">
              {confirm ? (
                <>
                  <label className="block text-sm font-medium">
                    New password
                    <input
                      required
                      type="password"
                      autoComplete="new-password"
                      minLength={8}
                      value={passwords.new_password}
                      onChange={(event) =>
                        setPasswords((current) => ({
                          ...current,
                          new_password: event.target.value,
                        }))
                      }
                      className="mt-2 w-full rounded-xl border p-3"
                    />
                  </label>
                  <label className="block text-sm font-medium">
                    Confirm new password
                    <input
                      required
                      type="password"
                      autoComplete="new-password"
                      value={passwords.confirm_password}
                      onChange={(event) =>
                        setPasswords((current) => ({
                          ...current,
                          confirm_password: event.target.value,
                        }))
                      }
                      className="mt-2 w-full rounded-xl border p-3"
                    />
                  </label>
                </>
              ) : (
                <label className="block text-sm font-medium">
                  Email
                  <input
                    required
                    type="email"
                    autoComplete="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    className="mt-2 w-full rounded-xl border p-3"
                  />
                </label>
              )}
              <button type="submit" className="workflow-button">
                {mutation.isPending
                  ? 'Please wait…'
                  : confirm
                    ? 'Reset password'
                    : 'Send reset link'}
              </button>
            </fieldset>
            {mutation.isError && (
              <p role="alert" className="text-sm text-rose-700">
                {getApiErrorMessage(mutation.error)}
              </p>
            )}
          </form>
        )}
        <div className="mt-6 flex gap-4 text-sm text-fuchsia-700">
          <Link to="/login" className="underline">
            Back to sign in
          </Link>
          {confirm && (
            <Link to="/forgot-password" className="underline">
              Request a new link
            </Link>
          )}
        </div>
      </section>
    </main>
  )
}
