<template>
  <div class="schedule-wizard">
    <header class="page-intro">
      <div><h1 ref="stepHeading" tabindex="-1">{{ steps[step - 1].title }}</h1></div>
      <RouterLink :to="workflowLink('/dashboard')" class="text-link">返回工作台</RouterLink>
    </header>
    <el-alert v-if="!canManage" title="当前账号可查看和导出安排；创建安排需要管理员操作。" type="info" :closable="false" />
    <RouterLink v-if="!canManage" :to="workflowLink('/schedule-results')" class="text-link">查看答辩安排 →</RouterLink>
    <template v-else>
      <ol class="wizard-progress" aria-label="安排向导进度">
        <li v-for="(item, index) in steps" :key="item.title" :class="{ active: step === index + 1, passed: step > index + 1 }" :aria-current="step === index + 1 ? 'step' : undefined">
          <span class="step-number">{{ index + 1 }}</span><span>{{ item.label }}</span>
        </li>
      </ol>
      <div class="wizard-context"><span>第 {{ step }} / 5 步</span><strong>{{ defenseType }}</strong></div>

      <section v-if="step === 1" class="workbench-panel">
        <h2 class="wizard-section-title">本次要安排哪一类答辩？</h2>
        <div class="defense-choice-grid" role="group" aria-label="选择答辩类型">
          <button v-for="item in typeChoices" :key="item.type" type="button" class="defense-choice" :class="{ selected: defenseType === item.type }" :aria-pressed="defenseType === item.type" @click="selectType(item.type)">
            <span class="choice-check" aria-hidden="true">{{ defenseType === item.type ? '✓' : '○' }}</span><strong>{{ item.type }}</strong>
          </button>
        </div>
      </section>

      <section v-else-if="step === 2" class="workbench-panel" v-loading="loading">
        <div class="section-heading"><h2>核对三份资料</h2><el-button :loading="loading" @click="loadInputs">重新检查资料</el-button></div>
        <el-alert v-if="loadError" :title="loadError" type="error" :closable="false" class="mb-4" show-icon />
        <div class="wizard-materials">
          <article v-for="item in materials" :key="item.kind" class="wizard-material">
            <div class="material-top"><h3>{{ item.title }}</h3><el-tag :type="item.count ? 'success' : 'warning'">{{ loading || loadError ? '待确认' : item.count ? `已有 ${item.count} ${item.unit}` : '需要补充' }}</el-tag></div>
            
            <div class="flex flex-wrap gap-2"><el-button @click="importKind = item.kind; importVisible = true">导入{{ item.shortTitle }}</el-button><RouterLink :to="preparationLink(item.path)" class="text-link">查看 / 新增 / 修改 →</RouterLink></div>
          </article>
        </div>
        <div v-if="!loading && !loadError" class="workflow-note mt-4" aria-live="polite">
          <strong>{{ missingMaterials.length ? `还需补充：${missingMaterials.map(item => item.title).join('、')}` : '三份资料均有记录，可以继续确认安排要求。' }}</strong>
        </div>
        <div v-if="mentorWarnings.length && !loading && !loadError" class="wizard-attention">
          <strong>建议先核对导师信息</strong><p>{{ mentorWarnings.slice(0, 5).join('；') }}{{ mentorWarnings.length > 5 ? `；另有 ${mentorWarnings.length - 5} 项` : '' }}</p>
          <RouterLink :to="preparationLink('/students')" class="text-link">去核对学生名单 →</RouterLink>
        </div>
      </section>

      <section v-else-if="step === 3" class="workbench-panel" v-loading="loading">
        <el-alert v-if="loadError" :title="loadError" type="error" :closable="false" show-icon />
        <el-button v-if="loadError" @click="loadInputs">重新读取</el-button>
        <div v-if="ruleErrors.length" class="wizard-attention" role="alert"><strong>还需要确认以下内容</strong><ul><li v-for="message in ruleErrors" :key="message">{{ message }}</li></ul></div>
        <RuleConfigForm v-if="config && !loading && !loadError" v-model="config" :saving="saving" hide-actions />
        <el-button v-if="config && !loading && !loadError" :disabled="saving" @click="restoreDefaults">恢复默认要求</el-button>
      </section>

      <section v-else class="wizard-results">
        <div v-if="step === 5" class="wizard-finish-note"><strong>{{ resultState.status === 'published' ? '已发布，可以下载安排表了' : '最后一步：发布并下载安排表' }}</strong></div>
        <ScheduleResult :key="defenseType" guided :guided-stage="step === 5 ? 'publish' : 'review'" @state="resultState = $event" @requirements="go(3)" @materials="go(2)" />
      </section>

      <footer class="wizard-footer">
        <el-button v-if="step > 1" :disabled="busy" @click="go(step - 1)">← 上一步</el-button>
        <RouterLink v-else :to="workflowLink('/dashboard')" class="text-link">稍后再安排</RouterLink>
        <div class="wizard-footer-next">
          <span v-if="step === 2 && missingMaterials.length">补齐资料后即可继续</span>
          <span v-if="step === 4 && !resultState.hasResult">先生成草稿，再继续</span>
          <el-button v-if="step < 5" type="primary" size="large" :loading="saving" :disabled="!canContinue" @click="next">{{ nextLabels[step - 1] }} →</el-button>
          <el-button v-else type="primary" size="large" :disabled="busy" @click="router.push(workflowLink('/dashboard'))">返回工作台</el-button>
        </div>
      </footer>
    </template>
    <ImportDialog v-if="canManage" v-model="importVisible" :type="importKind" @success="loadInputs" />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listTeachers } from '../api/teacher'
import { listStudents } from '../api/student'
import { listClassrooms } from '../api/classroom'
import { getRuleConfig, saveRuleConfig } from '../api/ruleConfig'
import { getDefaultRuleConfig } from '../utils/ruleConfigStorage'
import { useAdminGuard } from '../utils/adminGuard'
import { useDefenseType, workflowLink } from '../utils/useDefenseType'
import { validateWizardRules } from '../utils/wizardValidation'
import type { DefenseType, RuleConfig } from '../types/ruleConfig'
import type { Teacher } from '../types/teacher'
import type { Student } from '../types/student'
import type { Classroom } from '../types/classroom'
import type { ScheduleWorkflowState } from '../types/schedule'
import RuleConfigForm from '../components/RuleConfigForm.vue'
import ImportDialog from '../components/ImportDialog.vue'
import ScheduleResult from './schedule/ScheduleResult.vue'

const router = useRouter()
const route = useRoute()
const defenseType = useDefenseType()
const stepHeading = ref<HTMLElement>()
const { canManage, requireAdmin } = useAdminGuard()
const step = computed(() => Math.min(5, Math.max(1, Math.trunc(Number(route.query.step)) || 1)))
const steps = [
  { label: '选择类型', title: '先选本次答辩类型', description: '跟着向导逐步完成安排，完整管理功能仍可从左侧进入。' },
  { label: '准备资料', title: '准备好学生、教师和教室', description: '已有资料直接核对；缺少哪份，就在这里导入或补充。' },
  { label: '确认要求', title: '确认日期和每组人数', description: '先看常用设置，其他要求按需展开。保存成功后进入下一步。' },
  { label: '生成与核对', title: '生成草稿，核对分组安排', description: '按日期查看安排，查看问题提示；需要时可直接调整具体分组。' },
  { label: '发布与导出', title: '确认发布，下载安排表', description: '发布后锁定本版本；以后需要修改，可以再生成一份新草稿。' }
]
const typeChoices: { type: DefenseType; description: string }[] = [
  { type: '预答辩', description: '安排预答辩分组、教师和时间。' },
  { type: '正式答辩', description: '安排正式答辩，核对导师回避等要求。' },
  { type: '中期答辩', description: '安排中期考核，核对每组人数与导师安排。' }
]
const nextLabels = ['下一步：准备资料', '资料已核对，确认要求', '保存要求，去生成草稿', '已核对，去发布与导出']
const loading = ref(false)
const saving = ref(false)
const loadError = ref('')
const config = ref<RuleConfig | null>(null)
const savedFingerprint = ref('')
const dirty = computed(() => !!config.value && !!savedFingerprint.value && JSON.stringify(config.value) !== savedFingerprint.value)
const teachers = ref<Teacher[]>([])
const students = ref<Student[]>([])
const rooms = ref<Classroom[]>([])
const ruleErrors = ref<string[]>([])
const importKind = ref<'student' | 'teacher' | 'classroom'>('student')
const importVisible = ref(false)
const resultState = ref<ScheduleWorkflowState>({ hasResult: false, status: 'draft', errorCount: 0, busy: true })
const participants = computed(() => students.value.filter(student => student.defenseTypes.includes(defenseType.value)))
const materials = computed(() => [
  { kind: 'student' as const, title: '学生名单', shortTitle: '学生', path: '/students', count: participants.value.length, unit: '人', hint: `参加${defenseType.value}的学生。请核对学号、导师和参与环节。` },
  { kind: 'teacher' as const, title: '教师与专家', shortTitle: '教师', path: '/teachers', count: teachers.value.filter(t => !t.availableTypes.length || t.availableTypes.includes(defenseType.value)).length, unit: '人', hint: '核对职称、可担任角色、不可用时间。课表可在教师管理中导入。' },
  { kind: 'classroom' as const, title: '教室资料', shortTitle: '教室', path: '/classrooms', count: rooms.value.length, unit: '间', hint: '核对校区、容量，以及实际可使用的日期和时段。' }
])
const missingMaterials = computed(() => materials.value.filter(item => !item.count))
const mentorWarnings = computed(() => participants.value.flatMap(student => !student.mentorName ? [`${student.name}尚未填写导师`] : !teachers.value.some(t => t.name === student.mentorName) ? [`${student.name}的导师“${student.mentorName}”未在教师名单中`] : []))
const busy = computed(() => loading.value || saving.value || (step.value >= 4 && resultState.value.busy))
const canContinue = computed(() => !busy.value && (step.value === 1 || (step.value === 2 ? !loadError.value && !missingMaterials.value.length : step.value === 3 ? !!config.value && !loadError.value : resultState.value.hasResult)))
const preparationLink = (path: string) => ({ path, query: { type: defenseType.value, wizard: '1' } })
async function go(value: number) { await router.push({ path: '/schedule-wizard', query: { type: defenseType.value, step: value } }) }
async function confirmDiscard() {
  if (!dirty.value) return true
  try {
    await ElMessageBox.confirm('安排要求尚未保存。离开会丢失这些修改，是否仍然离开？', '尚有未保存的要求', { confirmButtonText: '离开', cancelButtonText: '继续填写', type: 'warning' })
    return true
  } catch { return false }
}
async function selectType(type: DefenseType) {
  if (type === defenseType.value || !await confirmDiscard()) return
  config.value = null; savedFingerprint.value = ''; ruleErrors.value = []; defenseType.value = type
}
onBeforeRouteLeave(confirmDiscard)
onBeforeRouteUpdate(to => to.query.type !== route.query.type ? confirmDiscard() : true)
let requestNumber = 0
async function loadInputs() {
  if (!canManage.value) return
  const request = ++requestNumber
  const type = defenseType.value
  loading.value = true; loadError.value = ''
  try {
    const [t, s, r, rules] = await Promise.all([listTeachers(), listStudents(), listClassrooms(), getRuleConfig(type)])
    if (request !== requestNumber || type !== defenseType.value) return
    teachers.value = t; students.value = s; rooms.value = r
    if (!dirty.value) { config.value = rules; savedFingerprint.value = JSON.stringify(rules) }
    if (step.value >= 3 && missingMaterials.value.length) { await go(2); ElMessage.warning('请先补齐本次答辩所需资料') }
  } catch (error) {
    if (request !== requestNumber || type !== defenseType.value) return
    loadError.value = error instanceof Error ? error.message : '资料读取失败，请重试'
    if (step.value >= 4) await go(2)
  } finally { if (request === requestNumber) loading.value = false }
}
async function next() {
  if (!canContinue.value || !requireAdmin()) return
  if (step.value === 3 && config.value) {
    ruleErrors.value = validateWizardRules(config.value)
    if (ruleErrors.value.length) return
    saving.value = true
    try {
      config.value = await saveRuleConfig(config.value)
      savedFingerprint.value = JSON.stringify(config.value)
      await go(4)
      ElMessage.success('要求已保存，接下来生成并核对草稿')
    } catch (error) { ruleErrors.value = [error instanceof Error ? error.message : '保存失败，请重试；当前填写内容已保留。'] }
    finally { saving.value = false }
  } else { await go(step.value + 1) }
}
async function restoreDefaults() {
  try {
    await ElMessageBox.confirm('将替换当前填写内容，点击底部保存按钮后才会生效。', '恢复默认要求')
    config.value = getDefaultRuleConfig(defenseType.value); ruleErrors.value = []
  } catch { /* user cancelled */ }
}
watch(step, async (value, previous) => {
  if (value === 2 && previous !== 2) void loadInputs()
  await nextTick()
  stepHeading.value?.closest('.el-main')?.scrollTo({ top: 0 })
  stepHeading.value?.focus({ preventScroll: true })
})
watch(defenseType, () => { config.value = null; ruleErrors.value = []; if (step.value > 1) void go(1) })
onMounted(() => { if (step.value > 1) void loadInputs() })
</script>
