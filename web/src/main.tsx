import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './index.css'

async function start() {
  if (import.meta.env.VITE_MOCK === '1') {
    const { setupWorker } = await import('msw/browser')
    const { handlers } = await import('./mocks/handlers')
    await setupWorker(...handlers).start({ onUnhandledRequest: 'bypass' })
  }
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
}

start()
