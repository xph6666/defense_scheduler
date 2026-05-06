export interface Student {
  id: number
  name: string
  studentType: '学硕' | '专硕'
  mentorName: string
  campus: '创新港' | '兴庆'
  defenseTypes: string[]
  secretaryName: string
  currentGroup?: string
  remark?: string
}
