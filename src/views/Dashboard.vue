<template>
  <div class="workbench">
    <header class="workbench-heading">
      <h1>答辩安排工作台</h1>
      <el-button :loading="loading" @click="load">刷新进度</el-button>
    </header>
    <section v-if="canManage" class="wizard-entry">
      <h2>新建答辩安排</h2>
      <el-button type="primary" size="large" @click="router.push(workflowLink('/schedule-wizard'))">开始一次答辩安排 →</el-button>
    </section>
    <div class="type-picker">
      <span>本次要安排</span><el-radio-group v-model="defenseType" aria-label="本次答辩类型">
        <el-radio-button v-for="type in defenseTypes" :key="type" :label="type">{{ type }}</el-radio-button>
      </el-radio-group>
    </div>
    <WorkflowSteps :current="!canManage ? 4 : currentResult?.groups.length ? (currentResult.status === 'published' ? 4 : 3) : materials.every(item => !!item.count) ? 2 : 1" />
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="mb-4" />
    <section class="next-action" aria-live="polite">
      <div><h2>{{ nextAction.title }}</h2></div>
      <el-button type="primary" size="large" :disabled="loading || !!error" @click="router.push(workflowLink(nextAction.path))">{{ nextAction.button }} <span class="ml-2" aria-hidden="true">→</span></el-button>
    </section>
    <section aria-labelledby="materials-title">
      <div class="section-heading"><h2 id="materials-title">1. 资料准备</h2></div>
      <div class="material-grid">
        <RouterLink v-for="item in materials" :key="item.path" :to="workflowLink(item.path)" class="material-card">
          <div class="material-top"><span class="material-label">{{ item.title }}</span><span class="material-state" :class="{ missing: item.count === 0 }">{{ item.count === null ? '尚未读取' : item.count ? '已有资料' : '待准备' }}</span></div>
          <div class="material-count">{{ item.count ?? '—' }}<small>{{ item.unit }}</small></div>
          <span class="material-link">{{ canManage && item.count === 0 ? '去导入资料' : '查看与补充' }} <span aria-hidden="true">→</span></span>
        </RouterLink>
      </div>
    </section>
    <section class="workbench-bottom">
      <div class="workbench-panel">
        <div class="section-heading"><h2>2. 确认本次要求</h2></div>
        <el-button @click="router.push(workflowLink('/rule-config'))">{{ canManage ? '设置日期与人数' : '查看安排要求' }}</el-button>
      </div>
      <div class="workbench-panel">
        <div class="section-heading"><h2>3. 本次安排进度</h2><el-tag v-if="currentResult?.groups.length" :type="currentResult.status === 'published' ? 'success' : 'warning'">{{ currentResult.status === 'published' ? '已发布' : '草稿' }}</el-tag></div>
        <template v-if="currentResult?.groups.length"><p>{{ currentResult.groups.length }} 个分组 · {{ scheduledStudents }} 名学生<span v-if="errorCount"> · {{ errorCount }} 项问题需要处理</span></p><el-button @click="router.push(workflowLink('/schedule-results'))">{{ currentResult.status === 'published' ? '查看并导出安排' : '检查分组安排' }}</el-button></template>
        <p v-else>{{ loading || error ? '读取成功后将在这里显示安排进度。' : canManage ? '还没有安排。准备资料并确认要求后，就可以生成草稿。' : '管理员发布安排后，会显示在这里。' }}</p>
      </div>
    </section>
    <details class="secondary-details">
      <summary>查看全部类型的统计与管理工具</summary><div class="overview-detail">
        <span>全部教师 {{ teachers?.length ?? '—' }} 人</span><span>全部学生 {{ students?.length ?? '—' }} 人</span><span>已有 {{ scheduleOverview.typeCount }} 类安排，共 {{ scheduleOverview.totalGroups }} 组</span><span>最近生成：{{ scheduleOverview.latestGeneratedAt }}</span>
        <span>最近检测：{{ conflictOverview.errorCount }} 项错误、{{ conflictOverview.warningCount }} 项提醒（{{ conflictOverview.checkedAt }}）</span>
        <el-button v-if="enableDemoTools && canManage" type="warning" plain @click="handleResetDemoData">重置演示数据</el-button>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listTeachers } from '../api/teacher'
import { listStudents } from '../api/student'
import { listClassrooms } from '../api/classroom'
import { getScheduleResults } from '../api/schedule'
import type { Teacher } from '../types/teacher'
import type { Student } from '../types/student'
import type { Classroom } from '../types/classroom'
import type { DefenseType, ScheduleResult } from '../types/schedule'
import { summarizeConflictOverview, summarizeScheduleOverview } from '../utils/dashboardOverview'
import { resetDemoData } from '../utils/demoSeed'
import { addOperationLog } from '../utils/operationLogStorage'
import { enableDemoTools } from '../config/features'
import { useAdminGuard } from '../utils/adminGuard'
import { defenseTypes, useDefenseType, workflowLink } from '../utils/useDefenseType'
import WorkflowSteps from '../components/WorkflowSteps.vue'
const router = useRouter()
const defenseType = useDefenseType()
const { canManage, requireAdmin } = useAdminGuard()
const teachers = ref<Teacher[] | null>(null)
const students = ref<Student[] | null>(null)
const classrooms = ref<Classroom[] | null>(null)
const results = ref<Partial<Record<DefenseType, ScheduleResult>>>({})
const loading = ref(true)
const error = ref('')
const currentResult = computed(() => results.value[defenseType.value])
const errorCount = computed(() => currentResult.value?.conflicts?.filter(c => c.level === 'error').length || 0)
const scheduledStudents = computed(() => new Set(currentResult.value?.groups.flatMap(g => g.students.map(s => s.id))).size)
const scheduleOverview = computed(() => summarizeScheduleOverview(Object.values(results.value)))
const conflictOverview = computed(() => summarizeConflictOverview(Object.values(results.value)))
const materials = computed(() => [
  { title: '学生名单', path: '/students', count: students.value?.filter(s => s.defenseTypes.includes(defenseType.value)).length ?? null, unit: '人', hint: `参加${defenseType.value}的学生。请核对学号、导师与参与环节。` },
  { title: '教师与专家', path: '/teachers', count: teachers.value?.filter(t => !t.availableTypes?.length || t.availableTypes.includes(defenseType.value)).length ?? null, unit: '人', hint: '可参加本次答辩的教师。请补充职称和不可用时间。' },
  { title: '教室与时间', path: '/classrooms', count: classrooms.value?.length ?? null, unit: '间', hint: '核对教室校区、容量，以及实际可以使用的日期和时间。' }
])
const nextAction = computed(() => {
  if (loading.value) return { title: '正在查看已有资料…', description: '稍等片刻，读取后会告诉您可以从哪里继续。', button: '读取中', path: '/dashboard' }
  if (error.value) return { title: '暂时无法确认进度', description: '请点击上方“刷新进度”重试，避免把读取失败当作没有资料。', button: '等待重新读取', path: '/dashboard' }
  if (!canManage.value) return { title: '查看已发布的答辩安排', description: '您可以查看分组、答辩时间，并下载 Word 或 Excel 文件。', button: '查看安排', path: '/schedule-results' }
  const missing = materials.value.find(item => !item.count)
  if (missing) return { title: `先准备${missing.title}`, description: missing.hint + ' 已有 Excel 文件可以直接导入。', button: `准备${missing.title}`, path: missing.path }
  if (currentResult.value?.groups.length) return { title: currentResult.value.status === 'published' ? '安排已发布，可以导出了' : errorCount.value ? `草稿已生成，还有 ${errorCount.value} 项问题需要处理` : '草稿已生成，请核对分组', description: '您可以继续查看本次安排。修改已发布内容时，需要生成新的草稿。', button: currentResult.value.status === 'published' ? '查看并导出' : '继续检查安排', path: '/schedule-results' }
  return { title: '资料已有，接下来确认日期和人数', description: '先核对本次要求，再生成分组草稿。高级要求可按需展开。', button: '确认安排要求', path: '/rule-config' }
})
async function load() {
  loading.value = true; error.value = ''
  try {
    const [t, s, c, ...schedules] = await Promise.all([listTeachers(), listStudents(), listClassrooms(), ...defenseTypes.map(getScheduleResultsForType)])
    teachers.value = t as Teacher[]; students.value = s as Student[]; classrooms.value = c as Classroom[]
    results.value = Object.fromEntries(defenseTypes.map((type, index) => [type, schedules[index]]))
  } catch (e) { error.value = e instanceof Error ? e.message : '资料读取失败，请重试' }
  finally { loading.value = false }
}
const getScheduleResultsForType = (type: DefenseType) => getScheduleResults(type)
async function handleResetDemoData() {
  if (!requireAdmin()) return
  try {
    await ElMessageBox.confirm('确定重置演示资料和排期结果吗？', '重置演示数据', { type: 'warning' })
    resetDemoData(); addOperationLog({ type: '重置演示数据', module: 'Dashboard', description: '重置演示资料与排期' })
    await load(); ElMessage.success('演示数据已重置')
  } catch { /* cancelled */ }
}
onMounted(load)
</script>
