import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from 'react-router'
import { auth } from './api/client'
import { useMe } from './api/hooks'
import LoginPage from './features/auth/LoginPage'
import PlanPage from './features/plan/PlanPage'
import Layout from './ui/Layout'

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } },
})

function RequireAuth() {
  const location = useLocation()
  const hasToken = !!auth.get()
  const { data: me, isLoading, isError } = useMe(hasToken)

  if (!hasToken || isError) return <Navigate to="/login" replace state={{ from: location }} />
  if (isLoading || !me) return <div className="p-10 text-muted">Loading…</div>
  return <Outlet />
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<RequireAuth />}>
            <Route element={<Layout />}>
              <Route path="/plan" element={<PlanPage />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/plan" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
