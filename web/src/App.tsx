import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from 'react-router'
import { auth } from './api/client'
import { useMe } from './api/hooks'
import LoginPage from './features/auth/LoginPage'
import ExplorePage from './features/explore/ExplorePage'
import OnboardingPage from './features/onboarding/OnboardingPage'
import PlanPage from './features/plan/PlanPage'
import ProfilePage from './features/profile/ProfilePage'
import Layout from './ui/Layout'
import { PageLoading } from './ui/Loading'

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } },
})

function RequireAuth() {
  const location = useLocation()
  const hasToken = !!auth.get()
  const { data: me, isLoading, isError } = useMe(hasToken)

  if (!hasToken || isError) return <Navigate to="/login" replace state={{ from: location }} />
  if (isLoading || !me) return <PageLoading />
  if (!me.onboarded && location.pathname !== '/onboarding') return <Navigate to="/onboarding" replace />
  return <Outlet />
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<RequireAuth />}>
            <Route path="/onboarding" element={<OnboardingPage />} />
            <Route element={<Layout />}>
              <Route path="/plan" element={<PlanPage />} />
              <Route path="/explore/:slotId?" element={<ExplorePage />} />
              <Route path="/profile" element={<ProfilePage />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/plan" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
