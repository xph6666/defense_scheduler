import axios, { type AxiosResponse } from 'axios'

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
  if (body && typeof body === 'object' && 'success' in body) {
    const envelope = body as ApiEnvelope
    if (envelope.success === false) {
      return Promise.reject(new Error(envelope.message || envelope.error || '请求失败'))
    }
    return envelope.data
  }
  return body
}

request.interceptors.request.use(
  config => {
    return config
  },
  error => {
    return Promise.reject(error)
  }
)

request.interceptors.response.use(
  unwrapResponse as (response: AxiosResponse) => AxiosResponse,
  error => {
    const body = error.response?.data as ApiEnvelope | undefined
    const message = body?.message || body?.error || error.message || '网络请求失败'
    return Promise.reject(new Error(message))
  }
)

export default request
