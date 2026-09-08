import { useEffect, useState } from 'react'

type HealthState = 'checking' | 'ok' | 'error'

function App() {
  const [health, setHealth] = useState<HealthState>('checking')
  const [detail, setDetail] = useState('')

  useEffect(() => {
    fetch('/health')
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }
        const body = (await response.json()) as { status?: string }
        if (body.status !== 'ok') {
          throw new Error('Unexpected health payload')
        }
        setHealth('ok')
      })
      .catch((error: unknown) => {
        setHealth('error')
        setDetail(error instanceof Error ? error.message : 'Unknown error')
      })
  }, [])

  return (
    <main>
      <h1>Social Commerce Operations Platform</h1>
      <p>Private internal operations app. UI design will come from Figma later.</p>
      <p>
        Backend health:{' '}
        {health === 'checking' && 'checking…'}
        {health === 'ok' && 'ok'}
        {health === 'error' && `unavailable (${detail})`}
      </p>
    </main>
  )
}

export default App
