<template>
  <el-card shadow="never" class="conflict-panel">
    <template #header>
      <div class="conflict-panel-heading">
        <div>
          <strong>冲突与待确认</strong>
          <p v-if="counts.error === 0 && conflicts.length" class="conflict-panel-status is-clear">
            无阻断项<span v-if="counts.warning + counts.info"> · {{ counts.warning + counts.info }} 项提醒或提示待查看</span>
          </p>
          <p v-else-if="counts.error" class="conflict-panel-status is-blocked">
            {{ counts.error }} 项错误会阻止发布，请先处理
          </p>
          <p v-else class="conflict-panel-status is-clear">当前版本尚未发现问题</p>
        </div>
        <el-tooltip content="重新检测当前版本的排期" placement="top">
          <el-button size="small" :loading="loading" text @click="emit('check')">
            <el-icon><Refresh /></el-icon>
            <span>重新检测</span>
          </el-button>
        </el-tooltip>
      </div>
    </template>

    <div class="conflict-panel-body">
      <div class="conflict-level-filters" role="group" aria-label="按问题级别筛选">
        <button
          v-for="filter in levelFilters"
          :key="filter.value"
          type="button"
          class="conflict-level-filter"
          :class="[`is-${filter.value}`, { 'is-active': levelFilter === filter.value }]"
          :aria-pressed="levelFilter === filter.value"
          @click="levelFilter = filter.value"
        >
          <span>{{ filter.label }}</span><strong>{{ filter.count }}</strong>
        </button>
      </div>

      <div v-if="!conflicts.length" class="conflict-empty-state">
        <el-icon><CircleCheck /></el-icon>
        <span>当前未发现冲突或待确认事项。</span>
      </div>

      <div v-else-if="visibleGroups.length" class="conflict-category-list">
        <button
          v-for="group in visibleGroups"
          :key="group.key"
          type="button"
          class="conflict-category-card"
          @click="openGroup(group)"
        >
          <div class="conflict-category-topline">
            <span class="conflict-category-title">{{ getTypeLabel(group.type) }}</span>
            <ConflictTag :level="group.level" />
          </div>
          <p class="conflict-category-reason">{{ group.reasonSummary || '查看此类问题的具体记录。' }}</p>
          <div class="conflict-category-meta">
            <span>{{ group.items.length }} 条记录</span>
            <span v-if="group.affectedCount">涉及 {{ group.affectedCount }} 个对象</span>
            <span class="conflict-category-open">查看明细 <el-icon><ArrowRight /></el-icon></span>
          </div>
        </button>
      </div>

      <div v-else class="conflict-empty-state is-filtered">
        <span>此级别暂无问题。</span>
      </div>
    </div>
  </el-card>

  <el-dialog
    v-model="detailsVisible"
    :title="activeGroup ? getTypeLabel(activeGroup.type) : '问题明细'"
    width="min(900px, 94vw)"
    top="7vh"
    class="conflict-group-dialog"
    destroy-on-close
  >
    <template v-if="activeGroup">
      <div class="conflict-dialog-summary">
        <div class="conflict-dialog-summary-line">
          <ConflictTag :level="activeGroup.level" />
          <strong>{{ filteredItems.length }} 条记录</strong>
          <span v-if="activeGroup.affectedCount">涉及 {{ activeGroup.affectedCount }} 个对象</span>
        </div>
        <p>{{ activeGroup.reasonSummary || '该类问题的具体记录如下。' }}</p>
        <p v-if="activeGroup.suggestionSummary" class="conflict-dialog-suggestion">
          建议：{{ activeGroup.suggestionSummary }}
        </p>
      </div>

      <el-input
        v-model="detailSearch"
        class="conflict-detail-search"
        clearable
        :prefix-icon="Search"
        placeholder="搜索对象、分组或原因"
        aria-label="搜索问题明细"
      />

      <div v-if="pagedItems.length" class="conflict-detail-list">
        <article v-for="item in pagedItems" :key="item.id" class="conflict-detail-row">
          <div class="conflict-detail-main">
            <div class="conflict-detail-title-row">
              <strong>{{ objectNameFor(item) || '未标记对象' }}</strong>
              <el-tag v-if="groupNamesFor(item).length" size="small" effect="plain">
                {{ groupNamesFor(item).join('、') }}
              </el-tag>
              <el-tag v-else-if="groupCountFor(item)" size="small" effect="plain" type="info">
                涉及 {{ groupCountFor(item) }} 组
              </el-tag>
            </div>
            <p v-if="item.reason">{{ item.reason }}</p>
            <p v-if="item.suggestion" class="conflict-detail-suggestion">建议：{{ item.suggestion }}</p>
          </div>
          <el-button
            v-if="groupIdsFor(item).length"
            class="conflict-detail-locate"
            link
            type="primary"
            @click="locateIssue(item)"
          >
            <el-icon><Position /></el-icon>定位分组
          </el-button>
        </article>
      </div>
      <el-empty v-else description="没有符合条件的问题。" :image-size="64" />

      <div v-if="filteredItems.length > pageSize" class="conflict-detail-pagination">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50]"
          :total="filteredItems.length"
          layout="total, sizes, prev, pager, next"
          background
          small
        />
      </div>
    </template>
    <template #footer>
      <el-button @click="detailsVisible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowRight, CircleCheck, Position, Refresh, Search } from '@element-plus/icons-vue'
import type { ScheduleGroup } from '../types/schedule'
import type { ConflictLevel, ScheduleConflict } from '../types/conflict'
import ConflictTag from './ConflictTag.vue'
import { getConflictCounts, getTypeLabel } from '../utils/conflictMock'

type LevelFilter = 'all' | ConflictLevel
interface ConflictGroup {
  key: string
  level: ConflictLevel
  type: string
  reasonSummary: string
  suggestionSummary: string
  items: ScheduleConflict[]
  affectedCount: number
}

const props = defineProps<{
  conflicts: ScheduleConflict[]
  groups?: ScheduleGroup[]
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'check'): void
  (e: 'locate', groupIds: number[]): void
}>()

const counts = computed(() => getConflictCounts(props.conflicts))
const levelFilter = ref<LevelFilter>('all')
const detailsVisible = ref(false)
const activeGroup = ref<ConflictGroup | null>(null)
const detailSearch = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
const groupNameById = computed(() => new Map((props.groups || []).map(group => [group.id, group.groupName])))

const levelFilters = computed(() => [
  { value: 'all' as const, label: '全部', count: props.conflicts.length },
  { value: 'error' as const, label: '错误', count: counts.value.error },
  { value: 'warning' as const, label: '警告', count: counts.value.warning },
  { value: 'info' as const, label: '提示', count: counts.value.info }
])

function normalizedText(issue: ScheduleConflict, value: string) {
  let normalized = value || ''
  if (issue.type.includes('教师') && normalized.includes('教师')) {
    normalized = normalized.replace(
      /(教师\s*)[^，,；;。\s]+?(?=\s*(?:尚未|没有|未提供|未标记|未确认|需要核对))/g,
      '$1〈对象〉'
    )
  }
  const dynamicValues = [issue.target, issue.groupName]
    .filter((entry): entry is string => !!entry?.trim())
    .sort((a, b) => b.length - a.length)
  for (const dynamicValue of dynamicValues) normalized = normalized.split(dynamicValue).join('〈对象〉')
  return normalized.replace(/\s+/g, ' ').trim()
}

const groupedConflicts = computed<ConflictGroup[]>(() => {
  const map = new Map<string, ConflictGroup>()
  for (const issue of props.conflicts) {
    const reasonKey = normalizedText(issue, issue.reason)
    const suggestionKey = normalizedText(issue, issue.suggestion || '')
    const key = [issue.level, issue.type, reasonKey, suggestionKey].join('::')
    let group = map.get(key)
    if (!group) {
      group = {
        key,
        level: issue.level,
        type: issue.type,
        reasonSummary: reasonKey,
        suggestionSummary: suggestionKey,
        items: [],
        affectedCount: 0
      }
      map.set(key, group)
    }
    group.items.push(issue)
  }

  return [...map.values()].map(group => {
    const objects = new Set(group.items.map(objectNameFor).filter(Boolean))
    const groupIds = new Set(group.items.flatMap(item => groupIdsFor(item)))
    group.affectedCount = objects.size || groupIds.size
    return group
  }).sort((a, b) => {
    const priority = { error: 0, warning: 1, info: 2 }
    return priority[a.level] - priority[b.level] || b.items.length - a.items.length || getTypeLabel(a.type).localeCompare(getTypeLabel(b.type), 'zh-CN')
  })
})

const visibleGroups = computed(() => levelFilter.value === 'all'
  ? groupedConflicts.value
  : groupedConflicts.value.filter(group => group.level === levelFilter.value))

const filteredItems = computed(() => {
  if (!activeGroup.value) return []
  const query = detailSearch.value.trim().toLocaleLowerCase()
  if (!query) return activeGroup.value.items
  return activeGroup.value.items.filter(item => {
    const searchable = [
      item.target,
      objectNameFor(item),
      item.groupName,
      item.reason,
      item.suggestion,
      ...groupNamesFor(item)
    ].filter(Boolean).join(' ').toLocaleLowerCase()
    return searchable.includes(query)
  })
})

const pagedItems = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredItems.value.slice(start, start + pageSize.value)
})

watch([detailSearch, pageSize], () => { currentPage.value = 1 })
watch(() => filteredItems.value.length, total => {
  const lastPage = Math.max(1, Math.ceil(total / pageSize.value))
  if (currentPage.value > lastPage) currentPage.value = lastPage
})

function openGroup(group: ConflictGroup) {
  activeGroup.value = group
  detailSearch.value = ''
  currentPage.value = 1
  detailsVisible.value = true
}

function groupIdsFor(issue: ScheduleConflict) {
  return [...new Set([
    ...(issue.groupId === undefined ? [] : [issue.groupId]),
    ...(issue.relatedGroupIds || [])
  ])]
}

function groupNamesFor(issue: ScheduleConflict) {
  const names = groupIdsFor(issue).map(id => groupNameById.value.get(id)).filter((name): name is string => !!name)
  if (!names.length && issue.groupName) return [issue.groupName]
  return [...new Set(names)]
}

function groupCountFor(issue: ScheduleConflict) {
  return groupIdsFor(issue).length
}

function objectNameFor(issue: ScheduleConflict) {
  if (issue.target?.trim()) return issue.target.trim()
  if (issue.groupName?.trim()) return issue.groupName.trim()
  if (issue.type.includes('教师')) {
    const match = issue.reason.match(/教师\s*([^，,；;。\s]+?)(?=\s*(?:尚未|没有|未提供|未标记|未确认|需要核对))/)
    if (match?.[1]) return match[1]
  }
  return ''
}

function locateIssue(issue: ScheduleConflict) {
  const ids = groupIdsFor(issue)
  if (!ids.length) return
  emit('locate', ids)
  detailsVisible.value = false
}
</script>

<style scoped>
.conflict-panel :deep(.el-card__header) { padding: 16px 18px; }
.conflict-panel :deep(.el-card__body) { padding: 16px; }
.conflict-panel-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.conflict-panel-heading strong { color: #18384d; font-size: 15px; }
.conflict-panel-status { margin: 5px 0 0; font-size: 11px; line-height: 1.45; }
.conflict-panel-status.is-clear { color: #557563; }
.conflict-panel-status.is-blocked { color: #a94442; }
.conflict-panel-body { display: grid; gap: 13px; }
.conflict-level-filters { display: flex; flex-wrap: wrap; gap: 6px; }
.conflict-level-filter { display: inline-flex; align-items: center; gap: 7px; padding: 5px 8px; border: 1px solid #e1e7ec; border-radius: 7px; background: #fff; color: #687985; cursor: pointer; font: inherit; font-size: 11px; transition: background .15s, border-color .15s; }
.conflict-level-filter strong { font-variant-numeric: tabular-nums; }
.conflict-level-filter.is-error.is-active { border-color: #e8c8c6; background: #fbefee; color: #a94442; }
.conflict-level-filter.is-warning.is-active { border-color: #f0dfc6; background: #fff7eb; color: #aa742c; }
.conflict-level-filter.is-info.is-active { border-color: #d9e2e8; background: #f1f5f7; color: #687985; }
.conflict-level-filter.is-all.is-active { border-color: #b9ccd8; background: #edf3f6; color: #24475c; }
.conflict-category-list { display: grid; gap: 8px; max-height: 520px; overflow-y: auto; padding-right: 2px; }
.conflict-category-card { width: 100%; padding: 12px; border: 1px solid #e0e7eb; border-radius: 8px; background: #fff; color: inherit; text-align: left; cursor: pointer; transition: border-color .15s, box-shadow .15s, transform .15s; }
.conflict-category-card:hover, .conflict-category-card:focus-visible { border-color: #9db6c6; box-shadow: 0 3px 12px #123a5610; outline: none; }
.conflict-category-card:active { transform: translateY(1px); }
.conflict-category-topline { display: flex; align-items: center; gap: 8px; }
.conflict-category-title { min-width: 0; color: #273f50; font-size: 13px; font-weight: 650; }
.conflict-category-reason { display: -webkit-box; margin: 8px 0; overflow: hidden; color: #667782; font-size: 11px; line-height: 1.5; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.conflict-category-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; color: #85929a; font-size: 10px; }
.conflict-category-open { display: inline-flex; align-items: center; gap: 2px; margin-left: auto; color: #285978; font-weight: 600; }
.conflict-empty-state { display: flex; align-items: center; gap: 8px; padding: 14px 10px; color: #557563; font-size: 12px; }
.conflict-empty-state :deep(.el-icon) { color: #5e9076; font-size: 17px; }
.conflict-empty-state.is-filtered { color: #77858e; }
.conflict-dialog-summary { padding: 14px 16px; border: 1px solid #e2e9ed; border-radius: 8px; background: #f7f9fa; }
.conflict-dialog-summary-line { display: flex; flex-wrap: wrap; align-items: center; gap: 9px; color: #6d7e88; font-size: 12px; }
.conflict-dialog-summary-line strong { color: #2a4658; }
.conflict-dialog-summary p { margin: 10px 0 0; color: #526674; font-size: 13px; line-height: 1.65; }
.conflict-dialog-summary .conflict-dialog-suggestion { margin-top: 5px; color: #71818b; font-size: 12px; }
.conflict-detail-search { margin: 14px 0 10px; }
.conflict-detail-list { display: grid; max-height: min(52vh, 520px); overflow-y: auto; border-top: 1px solid #e7ecef; }
.conflict-detail-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding: 13px 4px; border-bottom: 1px solid #edf0f2; }
.conflict-detail-main { min-width: 0; flex: 1; }
.conflict-detail-title-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.conflict-detail-title-row strong { color: #304a5b; font-size: 13px; }
.conflict-detail-main p { margin: 6px 0 0; color: #687984; font-size: 12px; line-height: 1.55; overflow-wrap: anywhere; }
.conflict-detail-main p.conflict-detail-suggestion { color: #89959c; font-size: 11px; }
.conflict-detail-locate { flex: 0 0 auto; margin-top: 1px; }
.conflict-detail-pagination { display: flex; justify-content: flex-end; margin-top: 12px; overflow-x: auto; }
@media (max-width: 640px) {
  .conflict-panel :deep(.el-card__header) { padding: 13px; }
  .conflict-panel :deep(.el-card__body) { padding: 12px; }
  .conflict-detail-row { gap: 8px; }
  .conflict-detail-locate { font-size: 11px; }
  .conflict-detail-pagination { justify-content: flex-start; }
}
</style>
