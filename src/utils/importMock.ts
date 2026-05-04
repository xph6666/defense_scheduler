import type { ImportModule, ImportPreviewResult, ImportPreviewColumn } from '../types/import'

export async function mockParseImportFile(
  module: ImportModule,
  file: File
): Promise<ImportPreviewResult> {
  // 模拟网络延迟
  await new Promise(resolve => setTimeout(resolve, 800))

  const fileInfo = {
    name: file.name,
    size: file.size,
    type: file.type
  }

  const columns: ImportPreviewColumn[] = getModuleColumns(module)
  const rows = generateImportRows(module)

  return {
    module,
    fileInfo,
    columns,
    rows,
    validCount: rows.length,
    invalidCount: 0,
    warnings: []
  }
}

function getModuleColumns(module: ImportModule): ImportPreviewColumn[] {
  switch (module) {
    case 'teacher':
      return [
        { prop: 'name', label: '姓名', matched: true, required: true },
        { prop: 'college', label: '学院', matched: true, required: true },
        { prop: 'title', label: '职称', matched: true, required: true },
        { prop: 'isExternal', label: '是否外院', matched: true }
      ]
    case 'student':
      return [
        { prop: 'name', label: '姓名', matched: true, required: true },
        { prop: 'studentType', label: '学生类型', matched: true, required: true },
        { prop: 'mentorName', label: '导师', matched: true, required: true },
        { prop: 'campus', label: '校区', matched: true, required: true }
      ]
    case 'classroom':
      return [
        { prop: 'campus', label: '校区', matched: true, required: true },
        { prop: 'name', label: '教室名称', matched: true, required: true },
        { prop: 'capacity', label: '容量', matched: true, required: true }
      ]
  }
}

export function generateImportRows(module: ImportModule): any[] {
  const timestamp = Date.now()
  switch (module) {
    case 'teacher':
      return [1, 2, 3, 4, 5].map(i => ({
        id: timestamp + i,
        name: `新教师${i}`,
        college: '软件学院',
        isExternal: i % 2 === 0,
        title: i % 2 === 0 ? '教授' : '副教授',
        roles: ['普通专家'],
        availableTypes: ['正式答辩'],
        campusPreference: '不限',
        unavailableTimes: '无',
        avoidTeacherNames: '',
        remark: '导入数据'
      }))
    case 'student':
      return [1, 2, 3, 4, 5].map(i => ({
        id: timestamp + i,
        name: `新学生${i}`,
        studentType: i % 2 === 0 ? '学硕' : '专硕',
        mentorName: `导师${i}`,
        campus: '创新港',
        defenseTypes: ['正式答辩'],
        secretaryName: `秘书${i}`,
        remark: '导入数据'
      }))
    case 'classroom':
      return [1, 2, 3, 4, 5].map(i => ({
        id: timestamp + i,
        campus: '创新港',
        name: `新教室A${100 + i}`,
        capacity: 30,
        availableTimes: '周一至周五全天',
        remark: '导入数据'
      }))
  }
}
