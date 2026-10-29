import colorSource from '../../shared/mentor-colors.json'

const palette = colorSource.palette
const hashVectors: Record<string, number> = colorSource.hashVectors

const hashString = (str: string) => {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    hash = (hash << 5) - hash + str.charCodeAt(i)
    hash |= 0
  }
  return Math.abs(hash)
}

/**
 * 导师在共享色板中的槽位。
 * 后端 api/mentor_colors.py 用同一公式取槽位（改取深色变体），
 * 排期内唯一分配由 buildMentorColorPairs 完成，此处只提供首选槽位。
 */
export const getMentorColorIndex = (name: string) =>
  hashString((name || '').trim() || 'unknown') % palette.length

/** 导师标签底色：取该槽位的浅色变体，配合深灰文字使用 */
export const getMentorColor = (name: string, colors?: Record<string, string>) =>
  colors?.[(name || '').trim()] || `#${palette[getMentorColorIndex(name)].light}`

/** Allocate once from ALL groups in the selected version, before filtering. */
export const buildMentorColorPairs = (names: Iterable<string>): Record<string, { light: string; dark: string }> => {
  const result: Record<string, { light: string; dark: string }> = Object.create(null)
  const usedSlots = new Set<number>()
  const usedLight = new Set<string>()
  const usedDark = new Set<string>()
  let overflow = palette.length
  const gcd = (left: number, right: number): number => right ? gcd(right, left % right) : left
  let step = colorSource.collisionStep
  while (gcd(step, palette.length) !== 1) step++
  const colorPair = (slot: number) => {
    if (slot < palette.length) return palette[slot]!
    const offset = slot - palette.length
    if (offset >= 56 ** 3) throw new Error('导师数量超出可分配的独立颜色范围')
    const value = (offset * 4051 + 7919) % (56 ** 3)
    const channels = [value % 56, Math.floor(value / 56) % 56, Math.floor(value / 56 ** 2)]
    const hex = (value: number) => value.toString(16).padStart(2, '0').toUpperCase()
    return { light: channels.map(channel => hex(200 + channel)).join(''),
      dark: channels.map(channel => hex(24 + channel * 2)).join('') }
  }
  // Default JS sorting compares UTF-16 code units; Python uses the same order.
  const ordered = [...new Set([...names].map(name => (name || '').trim()).filter(Boolean))].sort()
  for (const name of ordered) {
    const preferred = getMentorColorIndex(name)
    let slot = -1
    for (let offset = 0; offset < palette.length; offset++) {
      const candidate = (preferred + offset * step) % palette.length
      if (!usedSlots.has(candidate)) { slot = candidate; break }
    }
    if (slot < 0) {
      slot = overflow
      while (usedLight.has(colorPair(slot).light) || usedDark.has(colorPair(slot).dark)) slot++
      overflow = slot + 1
    }
    const pair = colorPair(slot)
    usedSlots.add(slot); usedLight.add(pair.light); usedDark.add(pair.dark)
    result[name] = pair
  }
  return result
}

export const buildMentorColorMap = (names: Iterable<string>): Record<string, string> => {
  const colors: Record<string, string> = Object.create(null)
  for (const [name, pair] of Object.entries(buildMentorColorPairs(names))) colors[name] = `#${pair.light}`
  return colors
}

/**
 * 自检：拿共享 JSON 里的黄金向量校验本文件的哈希实现。
 * 一旦这里的 hashString 与后端 js_hash 出现漂移，槽位就会错开、师生配色失效，
 * 这里直接在控制台报出来，不依赖额外测试框架。
 */
const verifyHashVectors = () => {
  for (const [name, expected] of Object.entries(hashVectors)) {
    const actual = getMentorColorIndex(name)
    if (actual !== expected) {
      console.error(
        `[mentor-color] 哈希槽位与共享色板不一致：${name} 期望 ${expected}，实得 ${actual}。` +
          '请核对 src/utils/color.ts 的 hashString 与 api/mentor_colors.py 的 js_hash。'
      )
      return
    }
  }
}

verifyHashVectors()
