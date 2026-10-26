import { useId, useState, type FormEvent } from 'react'
import { login, logout, register, type Account } from '../api'

type Props = { account: Account | null; busy: boolean; onChange: (account: Account | null) => void }

/** Sign in / create account. Signed-in users' new rosters are private to them. */
export default function AccountPanel({ account, busy, onChange }: Props) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [working, setWorking] = useState(false)
  const errorId = useId()

  async function submit(mode: 'login' | 'register', event?: FormEvent) {
    event?.preventDefault()
    setWorking(true); setError('')
    try {
      const next = mode === 'login' ? await login(email, password) : await register(email, password)
      setPassword('')
      onChange(next)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not sign in.')
    } finally {
      setWorking(false)
    }
  }

  async function signOut() {
    setWorking(true); setError('')
    try { await logout(); onChange(null) }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not sign out.') }
    finally { setWorking(false) }
  }

  const disabled = busy || working
  if (account) {
    return (
      <section className="account-panel card" aria-labelledby="account-heading">
        <h2 id="account-heading">Account</h2>
        <p className="account-state">Signed in as <strong>{account.email}</strong>. Rosters you build are private to you.</p>
        <button type="button" onClick={() => void signOut()} disabled={disabled}>Sign out</button>
        {error && <p className="account-error" role="alert">{error}</p>}
      </section>
    )
  }
  return (
    <section className="account-panel card" aria-labelledby="account-heading">
      <h2 id="account-heading">Account</h2>
      <p className="account-state">Sign in to keep your rosters private. Without an account they are shared with everyone on this machine.</p>
      <form className="account-form" onSubmit={event => void submit('login', event)} aria-describedby={error ? errorId : undefined}>
        <label>Email<input type="email" name="email" autoComplete="email" required value={email} onChange={e => setEmail(e.target.value)} disabled={disabled} /></label>
        <label>Password<input type="password" name="password" autoComplete="current-password" required minLength={10} maxLength={128} value={password} onChange={e => setPassword(e.target.value)} disabled={disabled} aria-describedby={`${errorId}-hint`} /></label>
        <p id={`${errorId}-hint`} className="account-hint">At least 10 characters.</p>
        <div className="account-actions">
          <button type="submit" disabled={disabled}>Sign in</button>
          <button type="button" disabled={disabled} onClick={event => {
            const form = event.currentTarget.form
            if (form && !form.reportValidity()) return
            void submit('register')
          }}>Create account</button>
        </div>
        {error && <p id={errorId} className="account-error" role="alert">{error}</p>}
      </form>
    </section>
  )
}
