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
 * 因此同一导师在网页标签与导出文件中恒定同色。
 */
export const getMentorColorIndex = (name: string) =>
  hashString((name || '').trim() || 'unknown') % palette.length

/** 导师标签底色：取该槽位的浅色变体，配合深灰文字使用 */
export const getMentorColor = (name: string) =>
  `#${palette[getMentorColorIndex(name)].light}`

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
