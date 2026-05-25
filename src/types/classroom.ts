export interface Classroom {
  id: number
  campus: '创新港' | '兴庆'
  name: string
  capacity: number
  availableTimes: string
  remark?: string
}
