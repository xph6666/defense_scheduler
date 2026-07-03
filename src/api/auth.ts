import request from './request'

const USE_MOCK = (import.meta as any).env?.VITE_USE_MOCK === 'true'

export interface LoginResult {
  token: string
  username: string
  isAdmin: boolean
}

export async function login(username: string, password: string) {
  if (USE_MOCK) {
    if (username === 'admin') {
      return { token: 'mock-token', username, isAdmin: true } satisfies LoginResult
    }
    throw new Error('账号或密码错误')
  }

  return request.post('/auth/login/', { username, password }) as Promise<LoginResult>
}
