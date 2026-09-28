import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// Design tokens (Story 2.1) and self-hosted Nunito, for the child-facing screens and
// components under src/components/. index.css's Parent Area rules are untouched by this
// story and stay in their own plain styling until a later story migrates them.
import './styles/tokens.css'
import './styles/fonts.css'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
