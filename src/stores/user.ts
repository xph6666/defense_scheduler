import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useUserStore = defineStore('user', () => {
  const username = ref('admin')
  const isLoggedIn = ref(true)

  const login = (name: string) => {
    username.value = name
    isLoggedIn.value = true
  }

  const logout = () => {
    username.value = ''
    isLoggedIn.value = false
  }

  return {
    username,
    isLoggedIn,
    login,
    logout
  }
})
