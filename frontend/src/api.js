import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

api.interceptors.request.use(config => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  r => r,
  err => {
    if (err.response?.status === 401) {
      // Only force a redirect to /login if the user actually HAD a token
      // (i.e. their session expired). A 401 on a public/background call while
      // logged out — e.g. the branding endpoints on the login page itself —
      // must NOT trigger a redirect, or it creates an infinite refresh loop.
      const hadToken = !!localStorage.getItem('token')
      localStorage.removeItem('token')
      const path = window.location.pathname
      const onAuthPage = path === '/login' || path === '/register' || path === '/'
      if (hadToken && !onAuthPage) {
        window.location.href = '/login'
      }
    }
    return Promise.reject(err)
  }
)

export default api
