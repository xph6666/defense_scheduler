import type { ScheduleResult } from '../types/schedule'
import type { ScheduleConflict } from '../types/conflict'
import { createCsvBlob, downloadBlob } from './download'

export function exportScheduleToCsv(
  result: ScheduleResult,
  conflicts: ScheduleConflict[] = []
) {
  const headers = [
    '答辩类型',
    '组名',
    '日期',
    '时间段',
    '校区',
    '教室',
    '组长/主席',
    '秘书',
    '专家名单',
    '学生名单',
    '学生-导师关系',
    '备注',
    '冲突状态'
  ]

  const rows = result.groups.map(group => {
    const groupConflicts = conflicts.filter(c => c.groupId === group.id)
    const status = groupConflicts.length > 0 
      ? groupConflicts.some(c => c.level === 'error') ? '硬冲突' : '有警告'
      : '正常'

    const teachers = group.teachers.map(t => t.name).join('；')
    const students = group.students.map(s => s.name).join('；')
    const studentMentor = group.students.map(s => `${s.name}-${s.mentorName}`).join('；')

    return [
      group.defenseType,
      group.groupName,
      group.date,
      group.timeRange,
      group.campus,
      group.classroom,
      group.leader || group.chairman || '',
      group.secretary,
      teachers,
      students,
      studentMentor,
      group.remark || '',
      status
    ]
  })

  const csvContent = [
    headers.join(','),
    ...rows.map(row => row.map(cell => `"${(cell || '').toString().replace(/"/g, '""')}"`).join(','))
  ].join('\n')

  const dateStr = result.generatedAt ? result.generatedAt.split(' ')[0] : new Date().toISOString().split('T')[0]
  const fileName = `答辩排期结果_${result.defenseType}_${dateStr}.csv`
  
  const blob = createCsvBlob(csvContent)
  downloadBlob(blob, fileName)

  // 记录导出时间
  localStorage.setItem('last_export_time', new Date().toISOString())
}
