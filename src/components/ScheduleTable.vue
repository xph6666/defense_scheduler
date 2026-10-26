<template>
  <el-table
    ref="tableRef"
    :data="groups"
    border
    style="width: 100%"
    :scrollbar-always-on="true"
    :row-class-name="rowClassName"
    row-key="id"
  >
    <el-table-column prop="groupName" label="组名" width="140" fixed="left" />
    <el-table-column label="状态" width="90">
      <template #default="{ row }">
        <ConflictTag :status="getStatus(row.id)" />
      </template>
    </el-table-column>
    <el-table-column prop="defenseType" label="答辩类型" width="100" />
    <el-table-column prop="date" label="日期" width="120" />
    <el-table-column prop="timeRange" label="时间" width="120" />
    <el-table-column prop="campus" label="校区" width="90" />
    <el-table-column prop="classroom" label="教室" width="120" />
    <el-table-column label="组长/主席" width="120">
      <template #default="{ row }">
        <span v-if="row.leader">{{ row.leader }}</span>
        <span v-else-if="row.chairman">{{ row.chairman }}</span>
        <span v-else class="text-gray-400">-</span>
      </template>
    </el-table-column>
    <el-table-column prop="secretary" label="秘书" width="120" />
    <el-table-column label="专家总数" width="100">
      <template #default="{ row }">{{ getScheduleExperts(row).length }}</template>
    </el-table-column>
    <el-table-column label="学生人数" width="90">
      <template #default="{ row }">{{ row.students?.length || 0 }}</template>
    </el-table-column>
    <el-table-column label="专家名单" min-width="220">
      <template #default="{ row }">
        <div class="flex flex-wrap gap-1">
          <el-tag
            v-for="t in getScheduleExperts(row)"
            :key="t.id"
            size="small"
            :style="assignedMentorColors[t.name.trim()] ? getStudentTagStyle(t.name) : undefined"
          >
            {{ t.name }}
          </el-tag>
        </div>
      </template>
    </el-table-column>
    <el-table-column label="学生名单" min-width="320">
      <template #default="{ row }">
        <div class="flex flex-wrap gap-1">
          <el-tag
            v-for="s in row.students"
            :key="s.id"
            size="small"
            :style="getStudentTagStyle(s.mentorName)"
          >
            {{ s.name }}
          </el-tag>
        </div>
      </template>
    </el-table-column>
    <el-table-column prop="remark" label="备注" min-width="200" show-overflow-tooltip />
    <el-table-column v-if="canManage" label="操作" width="100" fixed="right">
      <template #default="{ row }">
        <el-button link type="primary" size="small" @click="emit('adjust', row)">调整</el-button>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'
import { getScheduleExperts } from '../domain/scheduleExperts'
import type { ScheduleGroup } from '../types/schedule'
import { buildMentorColorMap, getMentorColor } from '../utils/color'
import ConflictTag from './ConflictTag.vue'
import type { ElTable } from 'element-plus'

const props = defineProps<{
  groups: ScheduleGroup[]
  groupStatus: Record<number, 'normal' | 'warning' | 'error'>
  canManage?: boolean
  highlightedGroupIds?: number[]
  mentorColors?: Record<string, string>
}>()

const emit = defineEmits<{
  (e: 'adjust', group: ScheduleGroup): void
}>()

const tableRef = ref<InstanceType<typeof ElTable> | null>(null)

const getStatus = (groupId: number) => props.groupStatus[groupId] || 'normal'

const isHighlighted = (groupId: number) => (props.highlightedGroupIds || []).includes(groupId)

const rowClassName = ({ row }: { row: ScheduleGroup }) => {
  const s = getStatus(row.id)
  const classes: string[] = []
  if (s === 'error') classes.push('row-error')
  else if (s === 'warning') classes.push('row-warning')
  if (isHighlighted(row.id)) classes.push('row-highlighted')
  return classes.join(' ')
}

const assignedMentorColors = computed(() => props.mentorColors
  || buildMentorColorMap(props.groups.flatMap(group => group.students.map(student => student.mentorName))))
const getStudentTagStyle = (mentorName: string) => {
  const color = getMentorColor(mentorName, assignedMentorColors.value)
  return {
    backgroundColor: color,
    borderColor: color,
    color: '#374151'
  }
}

// 高亮时滚动到第一个高亮行
watch(() => props.highlightedGroupIds || [], async (ids) => {
  if (!ids.length) return
  await nextTick()
  const firstId = ids[0]
  const rowIndex = props.groups.findIndex(g => g.id === firstId)
  if (rowIndex >= 0 && tableRef.value) {
    tableRef.value.scrollTo({ top: rowIndex * 48, behavior: 'smooth' })
  }
}, { flush: 'post' })
</script>

<style scoped>
:deep(.row-error td) {
  background-color: #fef2f2;
}
:deep(.row-warning td) {
  background-color: #fffbeb;
}
:deep(.row-highlighted td) {
  animation: tableRowHighlight 2s ease-out;
  background-color: #edf3f9 !important;
  border-top: 2px solid #00467f;
  border-bottom: 2px solid #00467f;
}
:deep(.row-highlighted td:first-child) {
  border-left: 2px solid #00467f;
}
:deep(.row-highlighted td:last-child) {
  border-right: 2px solid #00467f;
}

@keyframes tableRowHighlight {
  0% {
    background-color: #d6e6f2 !important;
  }
  50% {
    background-color: #e8f0f7 !important;
  }
  100% {
    background-color: #edf3f9 !important;
  }
}
</style>
