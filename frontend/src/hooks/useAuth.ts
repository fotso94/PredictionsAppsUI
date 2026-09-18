/**
 * useAuth — access the authentication context.
 *
 * Lives outside contexts/AuthContext.tsx so that file exports components only: mixing a hook in
 * breaks React Fast Refresh for every component that imports it (react-refresh/only-export-components).
 */

import { useContext } from 'react'
import AuthContext from '@/contexts/AuthContext'
import type { AuthContextType } from '@/types/auth'

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext)

  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }

  return context
}

export default useAuth
