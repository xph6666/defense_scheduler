import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useUserStore = defineStore('user', () => {
  const username = ref(localStorage.getItem('username') || '')
  const token = ref(localStorage.getItem('token') || '')
  const isLoggedIn = ref(localStorage.getItem('isLoggedIn') === 'true')

  const login = (name: string, userToken: string = 'mock-token') => {
    username.value = name
    token.value = userToken
    isLoggedIn.value = true
    localStorage.setItem('isLoggedIn', 'true')
    localStorage.setItem('username', name)
    localStorage.setItem('token', userToken)
  }

  const logout = () => {
    username.value = ''
    token.value = ''
    isLoggedIn.value = false
    localStorage.removeItem('isLoggedIn')
    localStorage.removeItem('username')
    localStorage.removeItem('token')
  }

  return {
    username,
    token,
    isLoggedIn,
    login,
    logout
  }
})
