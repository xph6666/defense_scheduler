<template>
  <el-table :data="groups" border style="width: 100%" :scrollbar-always-on="true" :row-class-name="rowClassName">
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
    <el-table-column label="专家人数" width="90">
      <template #default="{ row }">{{ row.teachers?.length || 0 }}</template>
    </el-table-column>
    <el-table-column label="学生人数" width="90">
      <template #default="{ row }">{{ row.students?.length || 0 }}</template>
    </el-table-column>
    <el-table-column label="专家名单" min-width="220">
      <template #default="{ row }">
        <div class="flex flex-wrap gap-1">
          <el-tag v-for="t in row.teachers" :key="t.id" size="small">
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
    <el-table-column label="操作" width="100" fixed="right">
      <template #default="{ row }">
        <el-button link type="primary" size="small" @click="emit('adjust', row)">调整</el-button>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import type { ScheduleGroup } from '../types/schedule'
import { getMentorColor } from '../utils/color'
import ConflictTag from './ConflictTag.vue'

const props = defineProps<{
  groups: ScheduleGroup[]
  groupStatus: Record<number, 'normal' | 'warning' | 'error'>
}>()

const emit = defineEmits<{
  (e: 'adjust', group: ScheduleGroup): void
}>()

const getStatus = (groupId: number) => props.groupStatus[groupId] || 'normal'

const rowClassName = ({ row }: { row: ScheduleGroup }) => {
  const s = getStatus(row.id)
  if (s === 'error') return 'row-error'
  if (s === 'warning') return 'row-warning'
  return ''
}

const getStudentTagStyle = (mentorName: string) => {
  const color = getMentorColor(mentorName)
  return {
    backgroundColor: color,
    borderColor: color,
    color: '#374151'
  }
}
</script>

<style scoped>
.row-error td {
  background-color: #fef2f2;
}
.row-warning td {
  background-color: #fffbeb;
}
</style>
