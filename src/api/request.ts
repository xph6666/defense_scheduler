import axios, { type AxiosResponse } from 'axios'
import { ElMessage } from 'element-plus'

interface ApiEnvelope<T = unknown> {
  success?: boolean
  data?: T
  message?: string
  error?: string
}

const request = axios.create({
  baseURL: (import.meta as any).env?.VITE_API_BASE_URL || '/api',
  timeout: 10000
})

const unwrapResponse = (response: AxiosResponse) => {
  const body = response.data as ApiEnvelope | unknown
  
  // 如果是文件流（导出Excel），直接返回
  if (response.config.responseType === 'blob') {
    return response
  }
  
  // 处理新的API格式：{ success, message, data }
  if (body && typeof body === 'object' && 'success' in body) {
    const envelope = body as ApiEnvelope
    if (envelope.success === false) {
      return Promise.reject(new Error(envelope.message || envelope.error || '请求失败'))
    }
    // 成功时返回 data 字段（可能是对象、数组或 null）
    return envelope.data
  }
  
  // 兼容旧格式（直接返回数据）
  return body
}

request.interceptors.request.use(
  config => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
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
    const status = error.response?.status
    const body = error.response?.data as ApiEnvelope | undefined
    const message = body?.message || body?.error || error.message || '网络请求失败'
    
    ElMessage.error(message)

    if (status === 401) {
      localStorage.removeItem('isLoggedIn')
      localStorage.removeItem('username')
      localStorage.removeItem('token')
      window.location.href = '/login'
    }

    return Promise.reject(new Error(message))
  }
)

export default request
