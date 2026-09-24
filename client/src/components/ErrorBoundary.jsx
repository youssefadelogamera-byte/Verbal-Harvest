import { Component } from 'react';

// Shows a friendly message (and the error) instead of a blank page if rendering fails.
export default class ErrorBoundary extends Component {
  state = { error: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error('Verbal Harvest crashed:', error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <main className="narrow" style={{ padding: '80px 0' }}>
        <div className="card">
          <h2>Something went wrong</h2>
          <p className="muted">Please reload the page. If the problem continues, share this message with support:</p>
          <pre className="alert alert-error" style={{ whiteSpace: 'pre-wrap', fontSize: '.85rem' }}>{String(this.state.error?.stack || this.state.error)}</pre>
          <button className="btn btn-primary" onClick={() => window.location.reload()}>Reload</button>
        </div>
      </main>
    );
  }
}
