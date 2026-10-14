import { useSyncExternalStore } from 'react'

export function useMediaQuery(query: string) {
  return useSyncExternalStore(
    (onChange) => {
      const mql = window.matchMedia(query)
      mql.addEventListener('change', onChange)
      // some environments (device emulation, older WebViews) resize without a change event
      window.addEventListener('resize', onChange)
      return () => {
        mql.removeEventListener('change', onChange)
        window.removeEventListener('resize', onChange)
      }
    },
    () => window.matchMedia(query).matches,
    () => false,
  )
}
