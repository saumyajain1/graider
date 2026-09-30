import { useState } from 'react'

import { getApiErrorMessage } from '../api/errors'
import { useLogin, useRegister } from '../hooks/useAuth'

type AuthMode = 'login' | 'register'

export function LoginPage() {
  const loginMutation = useLogin()
  const registerMutation = useRegister()
  const [mode, setMode] = useState<AuthMode>('login')
  const [form, setForm] = useState({
    full_name: '',
    email: '',
    password: '',
  })

  const activeMutation = mode === 'login' ? loginMutation : registerMutation
  const errorMessage = activeMutation.isError
    ? getApiErrorMessage(activeMutation.error, 'Something went wrong. Please try again.')
    : null

  return (
    <div className="mx-auto flex min-h-screen max-w-7xl flex-col justify-center px-4 py-10 text-white md:px-6">
      <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        <section className="glass-panel overflow-hidden p-8 md:p-10">
          <div className="max-w-xl">
            <p className="text-sm font-semibold tracking-[0.28em] text-fuchsia-100/60 uppercase">
              Graider MVP
            </p>
            <h1 className="mt-4 font-['Space_Grotesk'] text-5xl font-bold leading-tight">
              Grade written work with a structured AI workflow.
            </h1>
            <p className="mt-6 text-base text-fuchsia-50/78">
              Build assignments, generate grading artifacts, review AI suggestions, and finalize
              marks without turning the product into a chatbot.
            </p>
          </div>

          <div className="mt-10 grid gap-4 md:grid-cols-3">
            {['Teacher-owned workflow', 'Editable AI outputs', 'Question-by-question review'].map(
              (value) => (
                <div
                  key={value}
                  className="rounded-3xl border border-white/10 bg-white/5 p-5 text-sm text-fuchsia-50/75"
                >
                  {value}
                </div>
              ),
            )}
          </div>
        </section>

        <section className="app-card p-8 md:p-10">
          <div className="inline-flex rounded-full bg-slate-100 p-1">
            {(['login', 'register'] as AuthMode[]).map((entry) => (
              <button
                key={entry}
                type="button"
                onClick={() => setMode(entry)}
                className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                  mode === entry ? 'bg-slate-950 text-white' : 'text-slate-600 hover:text-slate-950'
                }`}
              >
                {entry === 'login' ? 'Sign in' : 'Create account'}
              </button>
            ))}
          </div>

          <h2 className="mt-6 section-title">
            {mode === 'login' ? 'Welcome back' : 'Create your teacher account'}
          </h2>
          <p className="mt-3 text-sm text-slate-600">
            This is a self-serve MVP. Registration signs you in immediately.
          </p>

          <form
            className="mt-8 space-y-4"
            onSubmit={async (event) => {
              event.preventDefault()

              if (mode === 'login') {
                await loginMutation.mutateAsync(form)
              } else {
                await registerMutation.mutateAsync(form)
              }
            }}
          >
            {mode === 'register' ? (
              <label className="block">
                <span className="mb-2 block text-sm font-medium text-slate-700">Full name</span>
                <input
                  required
                  value={form.full_name}
                  onChange={(event) =>
                    setForm((current) => ({ ...current, full_name: event.target.value }))
                  }
                  className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none transition focus:border-fuchsia-500"
                  placeholder="Ava Teacher"
                />
              </label>
            ) : null}

            <label className="block">
              <span className="mb-2 block text-sm font-medium text-slate-700">Email</span>
              <input
                required
                type="email"
                value={form.email}
                onChange={(event) =>
                  setForm((current) => ({ ...current, email: event.target.value }))
                }
                className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none transition focus:border-fuchsia-500"
                placeholder="teacher@example.com"
              />
            </label>

            <label className="block">
              <span className="mb-2 block text-sm font-medium text-slate-700">Password</span>
              <input
                required
                type="password"
                value={form.password}
                onChange={(event) =>
                  setForm((current) => ({ ...current, password: event.target.value }))
                }
                className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none transition focus:border-fuchsia-500"
                placeholder="Minimum 8 characters"
              />
              {mode === 'register' ? (
                <div className="mt-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
                  <p className="font-medium text-slate-700">Password requirements</p>
                  <ul className="mt-2 list-disc space-y-1 pl-5">
                    <li>At least 8 characters</li>
                    <li>Cannot be too similar to your name or email</li>
                    <li>Cannot be a common password</li>
                    <li>Cannot be entirely numeric</li>
                  </ul>
                </div>
              ) : null}
            </label>

            {errorMessage ? (
              <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                {errorMessage}
              </div>
            ) : null}

            <button
              type="submit"
              disabled={activeMutation.isPending}
              className="w-full rounded-2xl bg-slate-950 px-4 py-3 font-semibold text-white transition hover:bg-fuchsia-700 disabled:cursor-not-allowed disabled:opacity-70"
            >
              {activeMutation.isPending
                ? mode === 'login'
                  ? 'Signing in...'
                  : 'Creating account...'
                : mode === 'login'
                  ? 'Sign in'
                  : 'Create account'}
            </button>
          </form>
        </section>
      </div>
    </div>
  )
}
