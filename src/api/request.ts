import { runtimeConfig } from '../config/runtime'
import axios, { type AxiosError, type AxiosResponse } from 'axios'

interface ApiEnvelope<T = unknown> {
  success?: boolean
  data?: T
  message?: string
  error?: string
}

export class ApiRequestError extends Error {
  status?: number
  /** 后端错误信封中的 data，或未封装时的原始 body（可含 errors 等） */
  data?: unknown

  constructor(message: string, status?: number, data?: unknown) {
    super(message)
    this.name = 'ApiRequestError'
    this.status = status
    this.data = data
  }
}

export const isNotFoundError = (error: unknown) => {
  return error instanceof ApiRequestError && error.status === 404
}

const request = axios.create({
  baseURL: runtimeConfig.apiBaseUrl,
  timeout: 10000
})

const clearAuthState = () => {
  if (typeof window === 'undefined') return
  window.localStorage.removeItem('authToken')
  window.localStorage.removeItem('username')
  window.localStorage.removeItem('isAdmin')
}

const redirectToLogin = () => {
  if (typeof window === 'undefined' || window.location.pathname === '/login') return
  const redirect = `${window.location.pathname}${window.location.search}${window.location.hash}`
  window.location.assign(`/login?redirect=${encodeURIComponent(redirect)}`)
}

const unwrapResponse = (response: AxiosResponse) => {
  const body = response.data as ApiEnvelope | unknown
  if (body && typeof body === 'object' && 'success' in body) {
    const envelope = body as ApiEnvelope
    if (envelope.success === false) {
      return Promise.reject(
        new ApiRequestError(
          envelope.message || envelope.error || '请求失败',
          response.status,
          envelope.data
        )
      )
    }
    return envelope.data
  }
  return body
}

// 没有后端提示时给出可读的中文说明，避免把 Axios 英文报错直接展示给用户
const fallbackMessage = (error: AxiosError) => {
  const status = error.response?.status
  if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') return '请求超时，请稍后重试'
  if (!status) return '无法连接服务器，请检查网络后重试'
  if (status === 401) return '登录已过期，请重新登录'
  if (status === 403) return '没有权限执行该操作'
  if (status === 404) return '请求的数据不存在，可能已被删除'
  if (status >= 500) return '服务暂时不可用，请稍后重试'
  return '请求失败，请稍后重试'
}

request.interceptors.request.use(
  config => {
    const token = typeof window !== 'undefined' ? window.localStorage.getItem('authToken') : ''
    if (token && token !== 'mock-token') {
      config.headers.Authorization = `Token ${token}`
    }
    return config
  },
  error => {
    return Promise.reject(error)
  }
)

request.interceptors.response.use(
  unwrapResponse as (response: AxiosResponse) => AxiosResponse,
  error => {
    const body = error.response?.data as ApiEnvelope | Record<string, unknown> | undefined
    let message = fallbackMessage(error)
    let data: unknown = body

    if (body && typeof body === 'object') {
      if ('success' in body) {
        const envelope = body as ApiEnvelope
        message = envelope.message || envelope.error || message
        data = envelope.data
      } else {
        message =
          (typeof body.message === 'string' && body.message) ||
          (typeof body.error === 'string' && body.error) ||
          message
      }
    }

    if (error.response?.status === 401) {
      clearAuthState()
      redirectToLogin()
    }
    return Promise.reject(new ApiRequestError(message, error.response?.status, data))
  }
)

export default request
