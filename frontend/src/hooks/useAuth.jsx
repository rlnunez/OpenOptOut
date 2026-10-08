import { createContext, useContext, useState, useEffect } from 'react'
import api from '../api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser]     = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (token) {
      api.get('/auth/me')
        .then(r => setUser(r.data))
        .catch(() => localStorage.removeItem('token'))
        .finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [])

  const login = async (email, password) => {
    const form = new URLSearchParams({ username: email, password })
    const { data } = await api.post('/auth/token', form)
    if (data.mfa_required || data.mfa_mandated) {
      return data
    }
    localStorage.setItem('token', data.access_token)
    const me = await api.get('/auth/me')
    setUser(me.data)
    return me.data
  }

  const completeMfaLogin = async (token) => {
    localStorage.setItem('token', token)
    const me = await api.get('/auth/me')
    setUser(me.data)
    return me.data
  }

  const logout = () => {
    localStorage.removeItem('token')
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, setUser, login, completeMfaLogin, logout, loading }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)

// Does this user hold at least one of these permissions? Super admins hold
// every permission; managers hold what /auth/me reports (backend core/access.py).
export function can(user, ...keys) {
  if (!user) return false
  if (user.role === 'super_admin') return true
  return keys.some(k => user.permissions?.includes(k))
}
