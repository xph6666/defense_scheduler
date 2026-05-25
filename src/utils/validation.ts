export function requiredRule(message: string) {
  return { required: true, message, trigger: ['blur', 'change'] }
}

export function numberRangeRule(min: number, max: number, message: string) {
  return {
    type: 'number',
    min,
    max,
    message,
    trigger: ['blur', 'change']
  }
}

export function validateTimeRange(value: string): boolean {
  const pattern = /^\d{2}:\d{2}-\d{2}:\d{2}$/
  if (!pattern.test(value)) return false
  const [start, end] = value.split('-')
  return start < end
}

export function validateDateString(value: string): boolean {
  const pattern = /^\d{4}-\d{2}-\d{2}$/
  if (!pattern.test(value)) return false
  const date = new Date(value)
  return !isNaN(date.getTime())
}
