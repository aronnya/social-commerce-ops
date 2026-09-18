type PageStateProps = {
  title?: string
  message: string
}

export function LoadingState({ message = 'Loading…' }: { message?: string }) {
  return (
    <div className="page-state" role="status">
      <p className="page-state__message">{message}</p>
    </div>
  )
}

export function EmptyState({ title = 'Nothing here yet', message }: PageStateProps) {
  return (
    <div className="page-state">
      {title ? <h2 className="page-state__title">{title}</h2> : null}
      <p className="page-state__message">{message}</p>
    </div>
  )
}

export function ErrorState({
  title = 'Unable to load',
  message,
  onRetry,
}: PageStateProps & { onRetry?: () => void }) {
  return (
    <div className="page-state page-state--error" role="alert">
      <h2 className="page-state__title">{title}</h2>
      <p className="page-state__message">{message}</p>
      {onRetry ? (
        <button type="button" className="page-state__retry" onClick={onRetry}>
          Try again
        </button>
      ) : null}
    </div>
  )
}
