import { defineStore } from 'pinia'
import { ref } from 'vue'
import { login as loginApi, logout as logoutApi } from '../api/auth'

export const useUserStore = defineStore('user', () => {
  const username = ref(localStorage.getItem('username') || '')
  const isAdmin = ref(localStorage.getItem('isAdmin') === 'true')
  const isLoggedIn = ref(!!localStorage.getItem('authToken'))

  const login = async (name: string, password: string) => {
    const result = await loginApi(name, password)
    username.value = result.username || name
    isAdmin.value = result.isAdmin
    isLoggedIn.value = true
    localStorage.setItem('authToken', result.token)
    localStorage.setItem('username', result.username || name)
    localStorage.setItem('isAdmin', String(result.isAdmin))
  }

  const logout = async () => {
    await logoutApi()
    username.value = ''
    isAdmin.value = false
    isLoggedIn.value = false
    localStorage.removeItem('authToken')
    localStorage.removeItem('username')
    localStorage.removeItem('isAdmin')
  }

  return {
    username,
    isAdmin,
    isLoggedIn,
    login,
    logout
  }
})
