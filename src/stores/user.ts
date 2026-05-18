import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useUserStore = defineStore('user', () => {
  const username = ref(localStorage.getItem('username') || '')
  const isLoggedIn = ref(localStorage.getItem('isLoggedIn') === 'true')

  const login = (name: string) => {
    username.value = name
    isLoggedIn.value = true
    localStorage.setItem('isLoggedIn', 'true')
    localStorage.setItem('username', name)
  }

  const logout = () => {
    username.value = ''
    isLoggedIn.value = false
    localStorage.removeItem('isLoggedIn')
    localStorage.removeItem('username')
  }

  return {
    username,
    isLoggedIn,
    login,
    logout
  }
})
