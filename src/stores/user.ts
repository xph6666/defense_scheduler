import { defineStore } from 'pinia'
import { ref } from 'vue'
import { login as loginApi } from '../api/auth'

export const useUserStore = defineStore('user', () => {
  const username = ref(localStorage.getItem('username') || '')
  const isLoggedIn = ref(!!localStorage.getItem('authToken'))

  const login = async (name: string, password: string) => {
    const result = await loginApi(name, password)
    username.value = result.username || name
    isLoggedIn.value = true
    localStorage.setItem('authToken', result.token)
    localStorage.setItem('username', result.username || name)
  }

  const logout = () => {
    username.value = ''
    isLoggedIn.value = false
    localStorage.removeItem('authToken')
    localStorage.removeItem('username')
  }

  return {
    username,
    isLoggedIn,
    login,
    logout
  }
})
