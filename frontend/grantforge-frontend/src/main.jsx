import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

function ChristianIdentityBar() {
  return (
    <aside className="christian-identity-bar" aria-label="GrantForgeUSA Christian values statement">
      <div className="christian-identity-inner">
        <span className="christian-identity-mark" aria-hidden="true">✝</span>
        <p>
          <strong>Christian-founded.</strong> Guided by stewardship, integrity, service, and honest work.
          <span className="christian-identity-scripture"> “Whatever you do, work at it with all your heart...” — Colossians 3:23 (NIV)</span>
        </p>
      </div>
    </aside>
  )
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ChristianIdentityBar />
    <App />
  </StrictMode>,
)
