<template>
  <el-table
    ref="tableRef"
    :data="groups"
    border
    style="width: 100%"
    :row-class-name="rowClassName"
    row-key="id"
    @row-click="selectGroup"
  >
    <el-table-column label="状态" width="92" fixed="left">
      <template #default="{ row }"><ConflictTag :status="getStatus(row.id)" /></template>
    </el-table-column>
    <el-table-column prop="groupName" label="固定组号" width="118" />
    <el-table-column label="日期与时间" min-width="170">
      <template #default="{ row }">
        <strong>{{ row.date || '日期待安排' }}</strong>
        <span class="schedule-table-subline">{{ row.timeRange || '时间待安排' }}</span>
      </template>
    </el-table-column>
    <el-table-column prop="campus" label="校区" width="100" />
    <el-table-column label="学生" width="100">
      <template #default="{ row }"><strong>{{ row.students?.length || 0 }}</strong> 人</template>
    </el-table-column>
    <el-table-column label="组长 / 主席" min-width="140" show-overflow-tooltip>
      <template #default="{ row }">{{ row.leader || row.chairman || '待安排' }}</template>
    </el-table-column>
    <el-table-column prop="secretary" label="秘书" min-width="120" show-overflow-tooltip />
    <el-table-column label="专家" min-width="190" show-overflow-tooltip>
      <template #default="{ row }">
        <div class="flex flex-wrap gap-1">
          <el-tag v-for="teacher in getScheduleExperts(row)" :key="teacher.id" size="small" :style="mentorStyle(row, teacher.name)">{{ teacher.name }}</el-tag>
        </div>
      </template>
    </el-table-column>
    <el-table-column label="操作" :width="canManage ? 142 : 82" fixed="right">
      <template #default="{ row }">
        <el-button link type="primary" size="small" @click.stop="emit('select', row)">查看</el-button>
        <el-button v-if="canManage" link type="primary" size="small" @click.stop="emit('adjust', row)">调整</el-button>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'
import { buildMentorColors, groupMentorColors, neutralMentorColor, type MentorColorMap } from '../domain/mentorColors'
import { getScheduleExperts } from '../domain/scheduleExperts'
import type { ScheduleGroup } from '../types/schedule'
import ConflictTag from './ConflictTag.vue'
import type { ElTable } from 'element-plus'

const props = defineProps<{
  groups: ScheduleGroup[]
  groupStatus: Record<number, 'normal' | 'warning' | 'error'>
  canManage?: boolean
  highlightedGroupIds?: number[]
  mentorColors?: MentorColorMap
}>()

const emit = defineEmits<{
  (e: 'adjust', group: ScheduleGroup): void
  (e: 'select', group: ScheduleGroup): void
}>()

const tableRef = ref<InstanceType<typeof ElTable> | null>(null)
const colors = computed(() => Object.fromEntries(props.groups.map(group => [group.id,
  groupMentorColors(group, props.mentorColors ?? buildMentorColors(props.groups))])))
const mentorStyle = (group: ScheduleGroup, name: string) => colors.value[group.id]?.[name.trim()] ?? neutralMentorColor
const getStatus = (groupId: number) => props.groupStatus[groupId] || 'normal'
const isHighlighted = (groupId: number) => (props.highlightedGroupIds || []).includes(groupId)
const rowClassName = ({ row }: { row: ScheduleGroup }) => {
  const status = getStatus(row.id)
  const classes: string[] = ['schedule-table-row']
  if (status === 'error') classes.push('row-error')
  else if (status === 'warning') classes.push('row-warning')
  if (isHighlighted(row.id)) classes.push('row-highlighted')
  return classes.join(' ')
}
const selectGroup = (row: ScheduleGroup) => emit('select', row)

watch(() => props.highlightedGroupIds || [], async ids => {
  if (!ids.length) return
  await nextTick()
  const rowIndex = props.groups.findIndex(group => group.id === ids[0])
  if (rowIndex >= 0 && tableRef.value) tableRef.value.scrollTo({ top: rowIndex * 48, behavior: 'smooth' })
}, { flush: 'post' })
</script>

<style scoped>
.schedule-table-subline { display: block; margin-top: 3px; color: #6d7f8b; font-size: 12px; }
:deep(.schedule-table-row) { cursor: pointer; }
:deep(.row-error td) { background-color: #fef2f2; }
:deep(.row-warning td) { background-color: #fffbeb; }
:deep(.row-highlighted td) { animation: tableRowHighlight 2s ease-out; background-color: #edf3f9 !important; border-top: 2px solid #00467f; border-bottom: 2px solid #00467f; }
:deep(.row-highlighted td:first-child) { border-left: 2px solid #00467f; }
:deep(.row-highlighted td:last-child) { border-right: 2px solid #00467f; }
@keyframes tableRowHighlight {
  0% { background-color: #d6e6f2 !important; }
  50% { background-color: #e8f0f7 !important; }
  100% { background-color: #edf3f9 !important; }
}
</style>
