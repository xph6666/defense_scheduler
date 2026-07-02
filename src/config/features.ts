const truthy = (value: unknown) => String(value ?? '').toLowerCase() === 'true'

export const enableDemoTools =
  import.meta.env.DEV || truthy(import.meta.env.VITE_ENABLE_DEMO_TOOLS)
