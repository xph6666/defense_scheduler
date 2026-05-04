import type { TestChecklistItem } from '../types/test'

export function getDefaultChecklist(): TestChecklistItem[] {
  return [
    { id: 1, module: '核心', title: 'Dashboard 能正常打开', description: '首页能加载并展示基础统计数据', expectedResult: '数据展示正确，无报错', status: 'pending' },
    { id: 2, module: '教师管理', title: '可以新增教师', description: '点击新增按钮，填写表单并保存', expectedResult: '列表新增一条记录', status: 'pending' },
    { id: 3, module: '教师管理', title: '可以编辑教师', description: '点击编辑按钮，修改内容并保存', expectedResult: '记录内容更新', status: 'pending' },
    { id: 4, module: '教师管理', title: '可以删除教师', description: '点击删除按钮并确认', expectedResult: '记录从列表移除', status: 'pending' },
    { id: 5, module: '学生管理', title: '可以新增学生', description: '点击新增按钮，填写表单并保存', expectedResult: '列表新增一条记录', status: 'pending' },
    { id: 11, module: '排期生成', title: '可以选择答辩类型', description: '在排期页面切换不同答辩类型', expectedResult: '切换正常', status: 'pending' },
    { id: 12, module: '排期生成', title: '可以一键生成排期', description: '点击一键生成按钮', expectedResult: '生成成功并展示结果', status: 'pending' },
    { id: 16, module: '冲突检测', title: '生成后自动冲突检测', description: '排期生成后，侧边栏自动显示冲突列表', expectedResult: '冲突项展示正确', status: 'pending' },
    { id: 18, module: '人工调整', title: '可以人工调整分组', description: '打开调整抽屉，修改教室并保存', expectedResult: '分组信息更新，冲突重新检测', status: 'pending' },
    { id: 20, module: '导出', title: '可以导出排期结果', description: '点击导出按钮', expectedResult: '成功下载 CSV/Excel 文件', status: 'pending' },
    { id: 24, module: '导入', title: '导入预览弹窗可以打开', description: '点击导入并选择文件', expectedResult: '显示模拟解析预览表格', status: 'pending' },
    { id: 26, module: '规则配置', title: '规则配置页面可以打开', description: '进入规则配置中心', expectedResult: '页面展示正常，包含三类答辩 Tabs', status: 'pending' },
    { id: 27, module: '规则配置', title: '规则配置可以保存', description: '修改学生目标人数并点击保存', expectedResult: '显示保存成功，且切换 Tab 后再切回数据依然保持', status: 'pending' },
    { id: 28, module: '规则配置', title: '三类答辩规则独立', description: '修改预答辩规则，确认不影响正式答辩规则', expectedResult: '配置互不干扰', status: 'pending' },
    { id: 29, module: '排期展示', title: '可以展示软约束评分', description: '生成排期后查看右侧评分面板', expectedResult: '展示综合得分及分项详情', status: 'pending' },
    { id: 30, module: '操作日志', title: '生成排期后新增日志', description: '执行生成排期操作后进入日志页', expectedResult: '能看到刚才的操作记录', status: 'pending' },
    { id: 31, module: '操作日志', title: '可以清空操作日志', description: '点击清空日志按钮', expectedResult: '列表被清空', status: 'pending' }
  ]
}
