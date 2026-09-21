import request from './request'

const USE_MOCK = (import.meta as any).env?.VITE_USE_MOCK === 'true'

export interface LoginResult {
  token: string
  username: string
  isAdmin: boolean
}

export async function login(username: string, password: string) {
  // 账号与密码两端空白一律忽略：从 app-data/INITIAL_ADMIN.txt 复制初始随机密码时
  // 容易连带行尾空格，曾直接表现为"账号或密码错误"。
  const name = username.trim()
  const secret = password.trim()

  if (USE_MOCK) {
    if (name === 'admin') {
      return { token: 'mock-token', username: name, isAdmin: true } satisfies LoginResult
    }
    throw new Error('账号或密码错误')
  }

  return request.post('/auth/login/', { username: name, password: secret }) as Promise<LoginResult>
}

export interface ChangePasswordResult {
  token: string
}

export async function changePassword(oldPassword: string, newPassword: string) {
  // 与登录保持同一口径：两端空白一律忽略，避免设置出带空格的密码
  const oldSecret = oldPassword.trim()
  const newSecret = newPassword.trim()

  if (USE_MOCK) {
    return { token: 'mock-token' } satisfies ChangePasswordResult
  }

  return request.post('/auth/change-password/', {
    oldPassword: oldSecret,
    newPassword: newSecret
  }) as Promise<ChangePasswordResult>
}

export async function logout() {
  if (!USE_MOCK) await request.post('/auth/logout/')
}
