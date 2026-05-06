const pastelPalette = [
  '#E6F4FF',
  '#E8F5E9',
  '#FFF3E0',
  '#F3E5F5',
  '#E0F2F1',
  '#FCE4EC',
  '#E8EAF6',
  '#F1F8E9',
  '#FFFDE7',
  '#E0F7FA',
  '#F9FBE7',
  '#FBE9E7'
]

const hashString = (str: string) => {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    hash = (hash << 5) - hash + str.charCodeAt(i)
    hash |= 0
  }
  return Math.abs(hash)
}

export const getMentorColor = (name: string) => {
  const idx = hashString(name || 'unknown') % pastelPalette.length
  return pastelPalette[idx]
}
