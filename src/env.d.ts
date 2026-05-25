/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string
  readonly VITE_API_PROXY_TARGET?: string
  readonly VITE_USE_MOCK: string
  readonly VITE_USE_REMOTE_CONFLICT_CHECK?: string
  readonly VITE_USE_REMOTE_RULE_CONFIG?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
