export function downloadBlob(blob: Blob, fileName: string) {
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}

export function createCsvBlob(content: string): Blob {
  // \uFEFF 用于避免中文 CSV 在 Excel 中乱码
  return new Blob(['\uFEFF' + content], {
    type: 'text/csv;charset=utf-8;'
  })
}
