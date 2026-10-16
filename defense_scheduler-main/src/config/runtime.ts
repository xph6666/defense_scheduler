const truthy = (value: unknown) => String(value ?? '').toLowerCase() === 'true'

export const runtimeConfig = Object.freeze({
  useMock: truthy(import.meta.env.VITE_USE_MOCK),
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL || '/api',
  enableDemoTools: import.meta.env.DEV || truthy(import.meta.env.VITE_ENABLE_DEMO_TOOLS)
})
