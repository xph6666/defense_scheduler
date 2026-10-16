<template>
  <div class="space-y-4">
    <WorkflowSteps v-if="!guided" :current="result?.status === 'published' ? 4 : 3" />
    <div class="bg-white p-6 rounded-lg shadow-sm">
      <div v-if="!guided" class="flex items-start justify-between gap-4">
        <div>
          <div class="text-lg font-bold text-gray-800">答辩安排与导出</div>
        </div>
        <LegendTag />
      </div>

      <div :class="{ 'mt-5': !guided }">
        <ScheduleToolbar
          v-model:defenseType="defenseType"
          v-model:viewMode="viewMode"
          :loading="loading || publishing || moving || adjustSaving"
          :has-result="!!result?.groups.length"
          :can-manage="canManage"
          :guided="guided"
          @generate="prepareGeneration"
          @refresh="handleRefresh"
          @check-conflicts="handleCheckConflicts"
          @export="handleExportClick"
        />
        <el-button v-if="canManage && defenseType !== '中期答辩' && (!guided || guidedStage === 'review')" class="mt-3" :disabled="loading || publishing || moving" @click="prepareLinkedGeneration">联合生成预答辩与正式答辩</el-button>
      </div>
    </div>

    <div v-if="!loading && !errorMsg" class="workflow-note compact-status" aria-live="polite">
      <strong>{{ nextStepTitle }}</strong>
      <div class="compact-links">
        <el-button v-if="guided" link type="primary" @click="emit('requirements')">返回第 3 步修改要求 →</el-button>
        <RouterLink v-else :to="workflowLink('/rule-config')" class="text-link">查看或修改安排要求 →</RouterLink>
        <el-button v-if="guided" link type="primary" @click="emit('materials')">返回第 2 步检查资料 →</el-button>
        <RouterLink v-else :to="workflowLink('/dashboard')" class="text-link">返回工作台检查资料 →</RouterLink>
      </div>
    </div>

    <div v-if="versions.length" class="bg-white p-4 rounded-lg shadow-sm flex flex-wrap items-center gap-3">
      <span class="text-sm text-gray-600">排期版本</span>
      <el-select v-model="selectedVersion" placeholder="当前版本（下拉可查看历史）" clearable class="w-64" @change="fetchResult">
        <el-option
          v-for="v in versions" :key="v.id" :value="v.id"
          :label="`v${v.version} · ${v.status === 'published' ? '已发布' : '草稿'}${v.is_current ? ' · 当前' : ''}`"
        />
      </el-select>
      <el-tag :type="result?.status === 'published' ? 'success' : 'warning'">
        {{ result?.status === 'published' ? '已发布 · 内容已锁定' : '草稿 · 请核对后发布' }}
      </el-tag>
      <el-button v-if="canEdit && result?.versionId && (!guided || guidedStage === 'publish')" :loading="publishing" :disabled="loading" type="primary" @click="handlePublish">校验并发布</el-button>
      <el-button v-if="canEdit && result?.versionId" :disabled="loading" @click="editingRevision = result?.revision; moveVisible = true">移动学生</el-button>
    </div>

    <el-alert
      v-if="errorMsg"
      type="error"
      :closable="false"
      show-icon
      :title="errorMsg"
    />

    <div class="bg-white p-6 rounded-lg shadow-sm">
      <div class="flex flex-wrap items-center gap-x-8 gap-y-2 text-sm text-gray-700">
        <div><span class="text-gray-500">当前答辩类型：</span>{{ defenseType }}</div>
        <div><span class="text-gray-500">生成时间：</span>{{ meta.generatedAt || '-' }}</div>
        <div><span class="text-gray-500">总组数：</span>{{ meta.groupCount }}</div>
        <div><span class="text-gray-500">总学生数：</span>{{ meta.studentCount }}</div>
        <div><span class="text-gray-500">总专家数：</span>{{ meta.teacherCount }}</div>
        <div><span class="text-gray-500">冲突数量：</span>{{ meta.conflictCount }}</div>
      </div>
    </div>

    <div v-if="result?.groups.length" class="schedule-filters">
      <el-select v-model="dateFilter" aria-label="按日期筛选" placeholder="全部日期" clearable style="width: 160px"><el-option v-for="date in availableDates" :key="date" :value="date" :label="date || '日期待安排'" /></el-select>
      <el-select v-model="campusFilter" aria-label="按校区筛选" placeholder="全部校区" clearable style="width: 130px"><el-option label="创新港" value="创新港" /><el-option label="兴庆" value="兴庆" /></el-select>
      <el-checkbox v-model="onlyProblems">只看有问题的分组</el-checkbox>
      <span>显示 {{ filteredGroups.length }} / {{ result.groups.length }} 组</span>
      <el-button v-if="dateFilter || campusFilter || onlyProblems" link type="primary" @click="resetFilters">清除筛选</el-button>
      <p v-if="onlyProblems" class="section-tip w-full">全局问题（如未分组学生）仍显示在冲突检测中，不一定属于某个分组。</p>
    </div>

    <div v-if="loading" class="bg-white p-6 rounded-lg shadow-sm">
      <el-skeleton :rows="6" animated />
    </div>

    <div v-else-if="!result?.groups.length" class="bg-white p-10 rounded-lg shadow-sm">
      <el-empty :description="emptyResultDescription" />
    </div>

    <div v-else class="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div class="lg:col-span-2 space-y-4">
        <el-empty v-if="!filteredGroups.length" description="当前筛选下没有分组，可清除筛选查看全部安排。"><el-button @click="resetFilters">查看全部分组</el-button></el-empty>
        <ScheduleAgenda v-else-if="viewMode === 'agenda'" :groups="filteredGroups" :conflicts="conflicts" :can-manage="canEdit" @adjust="openAdjust" @problem="openGroupProblem" />
        <div v-else-if="viewMode === 'card'" class="space-y-4">
          <el-row :gutter="16">
            <el-col
              v-for="g in filteredGroups"
              :key="g.id"
              :xs="24" :md="12"
            >
              <ScheduleGroupCard
                :group="g"
                :status="groupStatusMap[g.id] || 'normal'"
                :conflict-count="groupConflictCountMap[g.id] || 0"
                :can-manage="canEdit"
                @adjust="openAdjust"
              />
            </el-col>
          </el-row>
        </div>

        <div v-else class="bg-white p-6 rounded-lg shadow-sm">
          <ScheduleTable :groups="filteredGroups" :group-status="groupStatusMap" :can-manage="canEdit" @adjust="openAdjust" />
        </div>
      </div>

      <div class="lg:col-span-1 space-y-4">
        <ConflictPanel
          :conflicts="conflicts"
          :loading="conflictLoading"
          @check="handleCheckConflicts"
          @view-detail="openConflictDetail"
        />
        <details class="secondary-details"><summary>查看分组质量评分</summary><SoftConstraintPanel :summary="optimizationSummary" /></details>
      </div>
    </div>
  </div>

  <el-dialog v-model="generationVisible" title="生成前，确认这次安排" width="min(560px, 94vw)" :close-on-click-modal="false">
    <template v-if="generationConfig">
      <p class="mb-4">确认后生成新草稿，历史版本保留。</p>
      <el-descriptions :column="1" border>
        <el-descriptions-item label="答辩类型">{{ defenseType }}</el-descriptions-item>
        <el-descriptions-item label="答辩日期">{{ generationConfig.startDate || '未设置' }} 至 {{ generationConfig.endDate || '未设置' }}</el-descriptions-item>
        <el-descriptions-item label="每组人数">学生 {{ generationConfig.studentCount.target }} 人 / 专家 {{ generationConfig.expertCount.target }} 人 / 秘书 1 人</el-descriptions-item>
        <el-descriptions-item label="参与学生">{{ generationStudentCount }} 人</el-descriptions-item>
        <el-descriptions-item label="导师安排">{{ defenseType !== '正式答辩' ? '导师与学生同组' : generationConfig.mentorAvoidance ? '导师回避自己的学生' : '不要求导师回避' }}</el-descriptions-item>
      </el-descriptions>
      <el-alert v-if="!generationConfig.enabled" title="此答辩类型尚未启用，请先修改安排要求。" type="warning" :closable="false" class="mt-4" />
      <el-alert v-else-if="!generationStudentCount" title="还没有参加本次答辩的学生，请先在学生名单中补充参与环节。" type="warning" :closable="false" class="mt-4" />
    </template>
    <template #footer>
      <el-button @click="generationVisible = false">暂不生成</el-button>
      <el-button @click="generationVisible = false; guided ? emit('requirements') : router.push(workflowLink('/rule-config'))">修改要求</el-button>
      <el-button type="primary" :disabled="!generationConfig?.enabled || !generationStudentCount" @click="handleGenerate">确认生成草稿</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="linkedVisible" title="联合生成两阶段答辩安排" width="min(680px, 94vw)" :close-on-click-modal="false">
    <p class="mb-4">会创建两份新草稿，并为本轮重新分配秘书；正式答辩沿用本轮预答辩的学生分组和秘书。历史版本保留。</p>
    <el-descriptions v-if="linkedConfigs" :column="1" border>
      <el-descriptions-item v-for="config in linkedConfigs" :key="config.defenseType" :label="config.defenseType">{{ config.startDate }} 至 {{ config.endDate }}；学生 {{ config.studentCount.target }} 人/组；专家 {{ config.expertCount.target }} 人（含主席/组长）</el-descriptions-item>
    </el-descriptions>
    <el-alert v-if="linkedError" class="mt-4" :title="linkedError" type="warning" :closable="false" show-icon />
    <template #footer><el-button @click="linkedVisible = false">取消</el-button><el-button @click="linkedVisible = false; router.push(workflowLink('/rule-config'))">修改两阶段要求</el-button><el-button type="primary" :disabled="!linkedConfigs || !!linkedError" @click="handleGenerateLinked">确认联合生成</el-button></template>
  </el-dialog>

  <el-dialog v-model="moveVisible" title="移动学生" width="480px">
    <div class="space-y-4">
      <p class="text-sm text-gray-500">学生移动后保留导师和秘书关系，预答辩/中期同时调整导师所在组，并重新校验冲突。</p>
      <el-select v-model="moveStudentId" filterable placeholder="选择学生和原组" class="w-full">
        <el-option v-for="s in moveChoices" :key="s.id" :value="s.id" :label="s.label" />
      </el-select>
      <el-select v-model="moveTargetId" placeholder="选择目标组" class="w-full">
        <el-option v-for="g in result?.groups || []" :key="g.id" :value="g.id" :label="g.groupName" :disabled="g.id === moveChoices.find(choice => choice.id === moveStudentId)?.groupId" />
      </el-select>
      <el-checkbox v-model="preserveSecretary">保留该学生的秘书关系</el-checkbox>
      <el-select v-if="!preserveSecretary" v-model="replacementSecretaryId" filterable placeholder="明确选择改绑的秘书" class="w-full">
        <el-option v-for="teacher in teacherOptions.filter(teacher => teacher.roles.includes('秘书'))" :key="teacher.id" :value="teacher.id" :label="teacher.name" />
      </el-select>
      <p v-if="!preserveSecretary" class="text-xs text-orange-600">确认移动时会更新秘书绑定，并再次检测秘书与学生同组等冲突。</p>
    </div>
    <template #footer><el-button @click="moveVisible = false">取消</el-button><el-button type="primary" :loading="moving" :disabled="!moveStudentId || !moveTargetId || (!preserveSecretary && !replacementSecretaryId)" @click="handleMoveStudent">确认移动</el-button></template>
  </el-dialog>

  <ScheduleAdjustDrawer
    v-model="adjustVisible"
    :defense-type="defenseType"
    :group="currentGroup"
    :teachers="teacherOptions"
    :students="studentOptions"
    :classrooms="classroomOptions"
    :saving="adjustSaving"
    :readonly="!canEdit"
    @save="handleSaveAdjust"
  />

  <ConflictDetailDialog v-model="conflictDetailVisible" :conflict="currentConflict" />

  <ExportDialog
    v-model="exportDialogVisible"
    :options="{ defenseType: defenseType }"
    :stats="exportStats"
    @confirm="handleExportConfirm"
  />

  <ExportProgress
    :status="exportStatus"
    @close="exportStatus = 'idle'"
  />
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import WorkflowSteps from '../../components/WorkflowSteps.vue'
import { useDefenseType, workflowLink } from '../../utils/useDefenseType'
import type { RuleConfig } from '../../types/ruleConfig'
import ScheduleAgenda from '../../components/ScheduleAgenda.vue'
import ScheduleToolbar from '../../components/ScheduleToolbar.vue'
import ScheduleGroupCard from '../../components/ScheduleGroupCard.vue'
import ScheduleTable from '../../components/ScheduleTable.vue'
import LegendTag from '../../components/LegendTag.vue'
import ScheduleAdjustDrawer from '../../components/ScheduleAdjustDrawer.vue'
import ConflictPanel from '../../components/ConflictPanel.vue'
import ConflictDetailDialog from '../../components/ConflictDetailDialog.vue'
import ExportDialog from '../../components/ExportDialog.vue'
import ExportProgress from '../../components/ExportProgress.vue'
import SoftConstraintPanel from '../../components/SoftConstraintPanel.vue'
import type { ScheduleGroup, ScheduleResult, ScheduleStudent, ScheduleTeacher, ScheduleWorkflowState } from '../../types/schedule'
import { generateSchedule, generateLinkedSchedule, getScheduleResults, listScheduleVersions, publishSchedule, moveScheduleStudent, type ScheduleVersionOption } from '../../api/schedule'
import { checkScheduleConflicts } from '../../api/conflict'
import { updateScheduleGroup } from '../../api/adjustment'
import type { ScheduleConflict } from '../../types/conflict'
import { getGroupConflictCount, getGroupStatus } from '../../utils/conflictMock'
import { exportScheduleExcel, exportScheduleWord, exportSchedulePdf } from '../../api/export'
import type { ExportStatus } from '../../types/export'
import type { OptimizationSummary } from '../../types/optimization'
import { evaluateSoftConstraints } from '../../utils/optimization'
import { getRuleConfig } from '../../api/ruleConfig'
import { listTeachers } from '../../api/teacher'
import { listStudents } from '../../api/student'
import { listClassrooms } from '../../api/classroom'
import type { Classroom } from '../../types/classroom'
import { useScheduleContext, type ScheduleContext } from '../../composables/useScheduleContext'
import { getScheduleExperts } from '../../domain/scheduleExperts'
import { validateWizardRules } from '../../utils/wizardValidation'
import { useAdminGuard } from '../../utils/adminGuard'

const props = defineProps<{ guided?: boolean; guidedStage?: 'review' | 'publish' }>()
const emit = defineEmits<{
  (event: 'state', state: ScheduleWorkflowState): void
  (event: 'requirements'): void
  (event: 'materials'): void
}>()
const defenseType = useDefenseType()
const router = useRouter()
const generationVisible = ref(false)
const linkedVisible = ref(false)
const linkedConfigs = ref<[RuleConfig, RuleConfig] | null>(null)
const linkedError = ref('')
const generationConfig = ref<RuleConfig | null>(null)
const generationStudentCount = ref(0)
const viewMode = ref<'agenda' | 'card' | 'table'>(props.guided ? 'agenda' : 'card')
const loading = ref(false)
const errorMsg = ref('')
const result = ref<ScheduleResult | null>(null)
const { canManage, requireAdmin } = useAdminGuard()

const selectedVersion = ref<number | undefined>()
const versions = ref<ScheduleVersionOption[]>([])
const workspace = useScheduleContext(defenseType, selectedVersion, result)
const editingRevision = ref<number | undefined>()
const canEdit = computed(() => canManage.value && result.value?.status !== 'published' && result.value?.isCurrent !== false && !loading.value && !publishing.value && !moving.value)
const publishing = ref(false)
const moving = ref(false)
const moveVisible = ref(false)
const moveStudentId = ref<number>()
const moveTargetId = ref<number>()
const preserveSecretary = ref(true)
const replacementSecretaryId = ref<number>()
const moveChoices = computed(() => result.value?.groups.flatMap(g => g.students.map(student => ({
  id: student.id, groupId: g.id, label: `${student.name}（${g.groupName}）`
}))) || [])

const handlePublish = async () => {
  if (!requireAdmin() || !canEdit.value || !result.value?.versionId || result.value.revision === undefined) return
  const context = workspace.capture()
  const current = result.value
  publishing.value = true
  try {
    const published = await publishSchedule(current.versionId!, current.revision!)
    if (!workspace.isCurrent(context, true)) return
    result.value = published
    applyConflictsFromResult(published)
    const options = await listScheduleVersions(context.defenseType)
    if (!workspace.isCurrent(context)) return
    versions.value = options
    ElMessage.success('已发布并锁定该版本，后续修改请生成新草稿')
  } catch (error) {
    if (workspace.isCurrent(context)) ElMessage.error(error instanceof Error ? error.message : '发布失败')
  } finally { if (workspace.isCurrent(context)) publishing.value = false }
}

const handleMoveStudent = async () => {
  const choice = moveChoices.value.find(student => student.id === moveStudentId.value)
  if (!requireAdmin() || !choice || !moveTargetId.value || !result.value || !canEdit.value || (!preserveSecretary.value && !replacementSecretaryId.value)) return
  const context = workspace.capture()
  moving.value = true
  try {
    await moveScheduleStudent(choice.id, choice.groupId, moveTargetId.value, editingRevision.value, { preserveSecretary: preserveSecretary.value, moveMentor: true, secretaryId: replacementSecretaryId.value })
    if (!workspace.isCurrent(context, true)) return
    moveVisible.value = false
    moving.value = false
    await fetchResult()
    ElMessage.success('学生已移动，导师/秘书关系与冲突检测已更新')
  } catch (error) {
    if (workspace.isCurrent(context)) ElMessage.error(error instanceof Error ? error.message : '移动失败')
  } finally { if (workspace.isCurrent(context)) moving.value = false }
}

const conflicts = ref<ScheduleConflict[]>([])
const conflictLoading = ref(false)

const adjustVisible = ref(false)
const adjustSaving = ref(false)
const currentGroup = ref<ScheduleGroup | null>(null)

const currentConflict = ref<ScheduleConflict | null>(null)
const conflictDetailVisible = ref(false)

const exportDialogVisible = ref(false)
const exportStatus = ref<ExportStatus>('idle')

const optimizationSummary = ref<OptimizationSummary | null>(null)

const teacherOptions = ref<ScheduleTeacher[]>([])
const studentOptions = ref<ScheduleStudent[]>([])
const classroomOptions = ref<{ campus: '创新港' | '兴庆'; name: string }[]>([])

const updateOptimizationScore = async (scheduleResult: ScheduleResult, context: ScheduleContext) => {
  try {
    const config = await getRuleConfig(context.defenseType)
    if (!workspace.isCurrent(context) || result.value?.versionId !== scheduleResult.versionId || result.value?.revision !== scheduleResult.revision) return
    optimizationSummary.value = evaluateSoftConstraints(scheduleResult, config)
  } catch {
    if (workspace.isCurrent(context)) optimizationSummary.value = null
  }
}

const openAdjust = (group: ScheduleGroup) => {
  if (!requireAdmin()) return
  if (!canEdit.value) return
  editingRevision.value = result.value?.revision
  currentGroup.value = group
  adjustVisible.value = true
}

const openConflictDetail = (c: ScheduleConflict) => {
  currentConflict.value = c
  conflictDetailVisible.value = true
}

const handleExportClick = () => {
  if (!result.value) return
  exportDialogVisible.value = true
}

const handleExportConfirm = async (format: 'excel' | 'word' | 'pdf' = 'excel') => {
  const type = defenseType.value
  const versionId = result.value?.versionId
  exportStatus.value = 'exporting'
  try {
    if (format === 'pdf') {
      await exportSchedulePdf(type, versionId)
    } else if (format === 'word') {
      await exportScheduleWord(type, versionId)
    } else {
      await exportScheduleExcel(type, versionId)
    }
    exportStatus.value = 'success'
  } catch (error) {
    exportStatus.value = 'error'
    ElMessage.error(error instanceof Error ? error.message : '导出失败，请稍后重试')
  }
}

const loadOptions = async (context: ScheduleContext) => {
  const [teachers, students, classrooms] = await Promise.all([
    listTeachers(),
    listStudents(),
    listClassrooms()
  ])

  if (!workspace.isCurrent(context)) return
  teacherOptions.value = teachers.filter(t => t.isActive !== false).map(t => ({
    id: t.id,
    name: t.name,
    title: t.title,
    roles: t.roles,
    college: t.college,
    isExternal: t.isExternal,
    isActive: t.isActive, memberEligible: t.memberEligible, isSoftwareTeacher: t.isSoftwareTeacher
  }))

  studentOptions.value = students.map(s => ({
    id: s.id,
    name: s.name,
    studentType: s.studentType,
    mentorName: s.mentorName,
    mentorId: s.mentorId, secretaryId: s.secretaryId, studentNo: s.studentNo, remark: s.remark,
    secretaryName: s.secretaryName
  }))

  classroomOptions.value = (classrooms as Classroom[]).map(c => ({ campus: c.campus, name: c.name }))
}

// 后端排期响应自带生成时的冲突快照；带了就直接用，否则回退到本地/远程检测
const applyConflictsFromResult = (scheduleResult: ScheduleResult): boolean => {
  if (Array.isArray(scheduleResult.conflicts)) {
    conflicts.value = scheduleResult.conflicts
    currentConflict.value = null
    return true
  }
  return false
}

const fetchResult = async () => {
  const context = workspace.begin()
  loading.value = true
  errorMsg.value = ''
  conflictLoading.value = false
  publishing.value = false
  moving.value = false
  try {
    const [scheduleResult, versionOptions] = await Promise.all([
      getScheduleResults(context.defenseType, context.versionId), listScheduleVersions(context.defenseType)
    ])
    if (!workspace.isCurrent(context)) return
    result.value = scheduleResult
    versions.value = versionOptions
    conflicts.value = []
    currentConflict.value = null
    optimizationSummary.value = null
    await loadOptions(context)
    if (!workspace.isCurrent(context) || !scheduleResult) return
    if (!applyConflictsFromResult(scheduleResult)) {
      const checked = await checkScheduleConflicts(context.defenseType, scheduleResult)
      if (!workspace.isCurrent(context)) return
      conflicts.value = checked
    }
    await updateOptimizationScore(scheduleResult, context)
  } catch (error) {
    if (!workspace.isCurrent(context)) return
    errorMsg.value = error instanceof Error ? error.message : '排期结果加载失败'
    result.value = null
    conflicts.value = []
    currentConflict.value = null
    optimizationSummary.value = null
  } finally { if (workspace.isCurrent(context)) loading.value = false }
}

const prepareGeneration = async () => {
  if (!requireAdmin() || loading.value || publishing.value || moving.value) return
  const context = workspace.capture()
  loading.value = true
  try {
    const [config, students] = await Promise.all([getRuleConfig(context.defenseType), listStudents()])
    if (!workspace.isCurrent(context)) return
    generationConfig.value = config
    generationStudentCount.value = students.filter(student => student.defenseTypes.includes(context.defenseType)).length
    generationVisible.value = true
  } catch (error) { if (workspace.isCurrent(context)) ElMessage.error(error instanceof Error ? error.message : '无法读取安排要求，请重试') }
  finally { if (workspace.isCurrent(context)) loading.value = false }
}

const prepareLinkedGeneration = async () => {
  if (!requireAdmin() || loading.value || publishing.value || moving.value) return
  const context = workspace.capture()
  loading.value = true
  try {
    const [pre, formal, students] = await Promise.all([getRuleConfig('预答辩'), getRuleConfig('正式答辩'), listStudents()])
    if (!workspace.isCurrent(context)) return
    linkedConfigs.value = [pre, { ...formal, preservePreDefenseGroups: true }]
    const errors = [...validateWizardRules(pre), ...validateWizardRules(formal)]
    if (!students.some(student => student.defenseTypes.includes('预答辩') && student.defenseTypes.includes('正式答辩'))) errors.push('请先为联合安排的学生勾选预答辩与正式答辩两个参与环节。')
    linkedError.value = errors.join(' ')
    linkedVisible.value = true
  } catch (error) { if (workspace.isCurrent(context)) ElMessage.error(error instanceof Error ? error.message : '两阶段要求读取失败') }
  finally { if (workspace.isCurrent(context)) loading.value = false }
}

const handleGenerateLinked = async () => {
  if (!requireAdmin() || !linkedConfigs.value || linkedError.value || loading.value) return
  const configs = linkedConfigs.value
  linkedVisible.value = false
  selectedVersion.value = undefined
  const context = workspace.begin()
  loading.value = true
  try {
    await generateLinkedSchedule(configs[0], configs[1])
    if (!workspace.isCurrent(context)) return
    ElMessage.success('两阶段草稿已生成，请分别核对冲突后发布')
    await fetchResult()
  } catch (error) {
    if (!workspace.isCurrent(context)) return
    errorMsg.value = error instanceof Error ? error.message : '联合生成失败'
    ElMessage.error(`${errorMsg.value}。若请求超时，可重试获取同一联合生成结果。`)
  } finally { if (workspace.isCurrent(context)) loading.value = false }
}

const handleGenerate = async () => {
  if (!requireAdmin() || !generationConfig.value || loading.value) return
  const config = generationConfig.value
  const ruleErrors = validateWizardRules(config)
  if (ruleErrors.length) { ElMessage.error(ruleErrors.join(' ')); return }
  generationVisible.value = false
  selectedVersion.value = undefined
  const context = workspace.begin()
  loading.value = true
  errorMsg.value = ''
  conflicts.value = []
  currentConflict.value = null
  try {
    const scheduleResult = await generateSchedule(context.defenseType, config)
    if (!workspace.isCurrent(context)) return
    result.value = scheduleResult
    const options = await listScheduleVersions(context.defenseType)
    if (!workspace.isCurrent(context)) return
    versions.value = options
    ElMessage.success('草稿已生成，请核对冲突后发布')
    if (!applyConflictsFromResult(scheduleResult)) {
      const checked = await checkScheduleConflicts(context.defenseType, scheduleResult)
      if (!workspace.isCurrent(context)) return
      conflicts.value = checked
    }
    await loadOptions(context)
    if (!workspace.isCurrent(context)) return
    await updateOptimizationScore(scheduleResult, context)
  } catch (error) {
    if (!workspace.isCurrent(context)) return
    errorMsg.value = error instanceof Error ? error.message : '生成失败'
    conflicts.value = []
    currentConflict.value = null
    ElMessage.error(`${errorMsg.value}。若请求超时，可重试获取同一生成结果。`)
  } finally { if (workspace.isCurrent(context)) loading.value = false }
}

const handleRefresh = async () => {
  await fetchResult()
}

let conflictRequest = 0
const handleCheckConflicts = async () => {
  const current = result.value
  if (!current || loading.value) return
  const context = workspace.capture()
  const requestId = ++conflictRequest
  conflictLoading.value = true
  try {
    const checked = await checkScheduleConflicts(context.defenseType, current)
    if (!workspace.isCurrent(context, true) || requestId !== conflictRequest) return
    conflicts.value = checked
  } catch (error) {
    if (workspace.isCurrent(context, true) && requestId === conflictRequest) ElMessage.error(error instanceof Error ? error.message : '冲突检测失败')
  } finally { if (workspace.isCurrent(context) && requestId === conflictRequest) conflictLoading.value = false }
}

const handleSaveAdjust = async (groupData: ScheduleGroup) => {
  if (!requireAdmin() || !result.value || !canEdit.value) return
  const context = workspace.capture()
  adjustSaving.value = true
  try {
    await updateScheduleGroup({ defenseType: context.defenseType, groupId: groupData.id, expectedRevision: editingRevision.value, groupData })
    if (!workspace.isCurrent(context, true)) return
    adjustVisible.value = false
    adjustSaving.value = false
    ElMessage.success('调整保存成功')
    await fetchResult()
  } catch (error) {
    if (workspace.isCurrent(context)) ElMessage.error(error instanceof Error ? error.message : '保存失败，请稍后重试')
  } finally { if (workspace.isCurrent(context)) adjustSaving.value = false }
}

watch(selectedVersion, () => { adjustVisible.value = false; moveVisible.value = false; generationVisible.value = false; linkedVisible.value = false; publishing.value = false; moving.value = false; adjustSaving.value = false })
watch(moveVisible, visible => { if (visible) { preserveSecretary.value = true; replacementSecretaryId.value = undefined; moveStudentId.value = undefined; moveTargetId.value = undefined } })

watch(defenseType, async () => {
  selectedVersion.value = undefined
  adjustVisible.value = false
  moveVisible.value = false
  generationVisible.value = false
  linkedVisible.value = false
  publishing.value = false
  moving.value = false
  adjustSaving.value = false
  result.value = null
  conflicts.value = []
  currentConflict.value = null
  optimizationSummary.value = null
  await fetchResult()
})

watch(canManage, isAllowed => {
  if (!isAllowed) {
    adjustVisible.value = false
    currentGroup.value = null
  }
})

onMounted(() => { void fetchResult() })

const groupStatusMap = computed(() => {
  const map: Record<number, 'normal' | 'warning' | 'error'> = {}
  if (!result.value) return map
  for (const g of result.value.groups) {
    map[g.id] = getGroupStatus(g.id, conflicts.value)
  }
  return map
})

const groupConflictCountMap = computed(() => {
  const map: Record<number, number> = {}
  if (!result.value) return map
  for (const g of result.value.groups) {
    map[g.id] = getGroupConflictCount(g.id, conflicts.value)
  }
  return map
})

const nextStepTitle = computed(() => {
  if (!result.value?.groups.length) return canManage.value ? '下一步：生成一份草稿' : '等待管理员发布安排'
  if (result.value.status === 'published') return '安排已发布，下一步可以导出文件'
  if (result.value.isCurrent === false) return '正在查看历史版本'
  const errors = conflicts.value.filter(c => c.level === 'error').length
  return errors ? `下一步：处理 ${errors} 项问题` : '下一步：核对分组，确认后发布'
})
const dateFilter = ref('')
const campusFilter = ref('')
const onlyProblems = ref(false)
const availableDates = computed(() => [...new Set(result.value?.groups.map(group => group.date) || [])].sort())
const filteredGroups = computed(() => (result.value?.groups || []).filter(group =>
  (!dateFilter.value || group.date === dateFilter.value)
  && (!campusFilter.value || group.campus === campusFilter.value)
  && (!onlyProblems.value || groupConflictCountMap.value[group.id] > 0)))
const resetFilters = () => { dateFilter.value = ''; campusFilter.value = ''; onlyProblems.value = false }
const openGroupProblem = (groupId: number) => {
  const conflict = conflicts.value.find(item => item.groupId === groupId || item.relatedGroupIds?.includes(groupId))
  if (conflict) openConflictDetail(conflict)
}
watch([defenseType, selectedVersion], resetFilters)
watch(() => ({
  hasResult: !!result.value?.groups.length && !errorMsg.value,
  status: result.value?.status === 'published' ? 'published' as const : 'draft' as const,
  errorCount: conflicts.value.filter(conflict => conflict.level === 'error').length,
  busy: loading.value || publishing.value || moving.value || adjustSaving.value || conflictLoading.value || generationVisible.value || linkedVisible.value || adjustVisible.value || moveVisible.value || exportDialogVisible.value || exportStatus.value === 'exporting'
}), state => emit('state', state), { immediate: true })

const emptyResultDescription = computed(() => {
  return canManage.value
    ? '还没有分组。资料和要求确认后，点击上方“生成排期草稿”。'
    : '当前暂无排期结果，请联系管理员生成排期。'
})

const exportStats = computed(() => ({
  groupCount: meta.value.groupCount,
  studentCount: meta.value.studentCount,
  conflictCount: meta.value.conflictCount,
  errorCount: conflicts.value.filter(c => c.level === 'error').length,
  warningCount: conflicts.value.filter(c => c.level === 'warning').length
}))

const meta = computed(() => {
  if (!result.value) {
    return {
      generatedAt: '',
      groupCount: 0,
      studentCount: 0,
      teacherCount: 0,
      conflictCount: 0
    }
  }

  const teacherSet = new Set<number>()
  let studentCount = 0
  for (const g of result.value.groups) {
    for (const t of getScheduleExperts(g)) teacherSet.add(t.id)
    studentCount += g.students.length
  }

  return {
    generatedAt: result.value.generatedAt ? new Date(result.value.generatedAt).toLocaleString() : '',
    groupCount: result.value.groups.length,
    studentCount,
    teacherCount: teacherSet.size,
    conflictCount: conflicts.value.length
  }
})
</script>
