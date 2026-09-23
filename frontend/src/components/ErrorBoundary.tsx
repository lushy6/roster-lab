import { Component, type ErrorInfo, type ReactNode } from 'react'

type State = { error: Error | null }

/** Last line of defence: a render error shows a recoverable message instead of a blank page. */
export default class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Roster Lab crashed while rendering', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <main className="page-shell">
        <section className="empty-result" role="alert">
          <h2>Something went wrong.</h2>
          <p>{this.state.error.message}</p>
          <button type="button" className="primary-button" onClick={() => this.setState({ error: null })}>Try again</button>
        </section>
      </main>
    )
  }
}
