import { AuthNotice } from '../components/AuthNotice'
import { GoogleButton } from '../components/GoogleButton'
import { useCurrentUser } from '../hooks/useAuth'

export function ProfilePage() {
  const { user } = useCurrentUser()
  const googleAccount = user?.connected_accounts.find((account) => account.provider === 'google')

  return (
    <div className="max-w-2xl space-y-6">
      <AuthNotice />
      <section className="rounded-3xl border border-slate-200 bg-white p-6">
        <h1 className="section-title">Your profile</h1>
        <dl className="mt-6 space-y-5">
          <div>
            <dt className="text-sm text-slate-500">Name</dt>
            <dd className="mt-1 break-words font-medium">{user?.full_name}</dd>
          </div>
          <div>
            <dt className="text-sm text-slate-500">Email</dt>
            <dd className="mt-1 break-all font-medium">{user?.email}</dd>
          </div>
        </dl>
      </section>
      <section className="rounded-3xl border border-slate-200 bg-white p-6">
        <h2 className="text-lg font-semibold">Connected accounts</h2>
        <p className="mt-2 text-sm text-slate-600">
          Connect Google to sign in to this account with your existing assignments and results.
        </p>
        {googleAccount ? (
          <div className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div>
              <p className="font-medium">Google</p>
              <p className="mt-1 break-all text-sm text-slate-600">{googleAccount.email}</p>
            </div>
            <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-800">
              Connected
            </span>
          </div>
        ) : (
          <div className="mt-5 max-w-sm space-y-4">
            <p className="text-sm text-slate-500">No Google account connected.</p>
            <GoogleButton process="connect" />
          </div>
        )}
      </section>
    </div>
  )
}
