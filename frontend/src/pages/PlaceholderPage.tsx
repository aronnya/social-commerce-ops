type PlaceholderPageProps = {
  title: string
  purpose: string
}

export function PlaceholderPage({ title, purpose }: PlaceholderPageProps) {
  return (
    <header className="page-header">
      <h1>{title}</h1>
      <p>{purpose}</p>
    </header>
  )
}
