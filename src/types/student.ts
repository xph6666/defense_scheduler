export interface Student {
  id: number
  name: string
  studentNo?: string
  gender?: string
  // 真实名单中该列为学科（如"计算机科学与技术"），不再限定为 学硕/专硕
  studentType: string
  mentorName: string
  campus: '创新港' | '兴庆'
  defenseTypes: string[]
  secretaryName: string
  currentGroup?: string
  remark?: string
}
