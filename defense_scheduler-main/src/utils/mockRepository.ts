export function createMockRepository<T extends { id: number }>(key: string, seed: T[]) {
  const copy = (value: T[]) => JSON.parse(JSON.stringify(value)) as T[]
  return {
    read(): T[] {
      const raw = localStorage.getItem(key)
      if (raw) {
        try {
          const items = JSON.parse(raw)
          if (Array.isArray(items)) return items
        } catch { /* replace malformed demo state with seed */ }
      }
      const items = copy(seed)
      localStorage.setItem(key, JSON.stringify(items))
      return items
    },
    write(items: T[]) { localStorage.setItem(key, JSON.stringify(items)) }
  }
}
