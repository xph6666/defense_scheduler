<template>
  <div class="max-w-4xl mx-auto space-y-8">
    <div class="text-center">
      <h2 class="text-3xl font-bold text-gray-800">系统演示指南</h2>
      <p class="text-gray-500 mt-2">请按照以下步骤完成一次完整的 P0 功能演示</p>
    </div>

    <div class="grid grid-cols-1 gap-6">
      <el-card v-for="(step, index) in steps" :key="index" shadow="hover" class="relative overflow-visible">
        <div class="absolute -left-4 -top-4 w-10 h-10 bg-blue-600 text-white rounded-full flex items-center justify-center font-bold text-lg shadow-lg">
          {{ index + 1 }}
        </div>
        <div class="flex items-start gap-4 ml-4">
          <div class="flex-grow">
            <h3 class="text-xl font-bold text-gray-800">{{ step.title }}</h3>
            <p class="text-gray-600 mt-2 leading-relaxed">{{ step.content }}</p>
            <div class="mt-4 flex gap-2">
              <el-button 
                v-for="btn in step.actions" 
                :key="btn.label" 
                size="small" 
                :type="btn.type || 'primary'"
                @click="router.push(btn.path)"
              >
                {{ btn.label }}
              </el-button>
            </div>
          </div>
        </div>
      </el-card>
    </div>

    <div class="bg-blue-50 p-6 rounded-lg border border-blue-100 flex items-center justify-between">
      <div>
        <div class="font-bold text-blue-800">演示前准备</div>
        <div class="text-sm text-blue-600 mt-1">建议演示前先重置演示数据，以获得最佳体验。</div>
      </div>
      <el-button type="primary" @click="router.push('/dashboard')">前往 Dashboard 重置数据</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()

interface StepAction {
  label: string
  path: string
  type?: 'primary' | 'success' | 'warning' | 'danger' | 'info'
}

interface Step {
  title: string
  content: string
  actions: StepAction[]
}

const steps: Step[] = [
  {
    title: '初始化演示数据',
    content: '打开 Dashboard，点击“重置演示数据”，说明系统当前 P0 能力并确保基础数据完整。',
    actions: [{ label: '前往 Dashboard', path: '/dashboard' }]
  },
  {
    title: '基础数据维护',
    content: '进入教师、学生、教室管理页面，展示基础数据的增删改查及模拟导入功能。',
    actions: [
      { label: '教师管理', path: '/teachers', type: 'info' },
      { label: '学生管理', path: '/students', type: 'info' }
    ]
  },
  {
    title: '一键生成排期',
    content: '进入排期结果页，选择答辩类型（如预答辩），点击一键生成排期，展示系统自动化能力。',
    actions: [{ label: '前往排期结果', path: '/schedule-results' }]
  },
  {
    title: '排期展示与冲突检测',
    content: '展示卡片/表格视图、导师-学生同色预览，说明右侧冲突检测面板如何辅助人工复核。',
    actions: [{ label: '查看排期结果', path: '/schedule-results', type: 'success' }]
  },
  {
    title: '人工微调与导出',
    content: '对某个分组进行微调（修改教室或成员），展示实时冲突更新。最后点击导出 Excel 完成闭环。',
    actions: [{ label: '前往排期结果', path: '/schedule-results', type: 'success' }]
  },
  {
    title: '规则配置与优化',
    content: '进入规则配置中心，调整人数规则或软约束权重，观察排期结果页的评分变化。',
    actions: [{ label: '规则配置中心', path: '/rule-config' }]
  },
  {
    title: '操作日志审计',
    content: '进入操作日志页面，查看刚才进行的所有生成、调整、配置修改等操作的详细记录。',
    actions: [{ label: '查看操作日志', path: '/operation-log', type: 'info' }]
  }
]
</script>
