<template>
  <el-card shadow="never" class="h-full">
    <template #header>
      <div class="flex items-center justify-between gap-2">
        <div class="font-bold text-gray-800">冲突检测</div>
        <el-button size="small" :loading="loading" @click="emit('check')">重新检测</el-button>
      </div>
    </template>

    <div class="space-y-4">
      <div class="flex flex-wrap gap-2">
        <el-tag type="danger">错误 {{ counts.error }}</el-tag>
        <el-tag type="warning">警告 {{ counts.warning }}</el-tag>
        <el-tag type="info">提示 {{ counts.info }}</el-tag>
      </div>

      <div v-if="conflicts.length === 0" class="text-gray-500">
        当前未发现冲突。
      </div>

      <div v-else class="space-y-3">
        <div
          v-for="c in conflicts"
          :key="c.id"
          class="border rounded-md p-3 bg-white"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="font-medium text-gray-800">{{ c.type }}</span>
              <ConflictTag :level="c.level" />
              <span v-if="c.groupName" class="text-gray-500">｜{{ c.groupName }}</span>
              <span v-else-if="c.relatedGroupIds?.length" class="text-gray-500">｜涉及组：{{ c.relatedGroupIds.join('、') }}</span>
            </div>
            <el-button link type="primary" size="small" @click="emit('view-detail', c)">查看详情</el-button>
          </div>

          <div class="text-sm text-gray-600 mt-2 space-y-1">
            <div><span class="text-gray-500">对象：</span>{{ c.target }}</div>
            <div><span class="text-gray-500">原因：</span>{{ c.reason }}</div>
            <div v-if="c.suggestion"><span class="text-gray-500">建议：</span>{{ c.suggestion }}</div>
          </div>
        </div>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ScheduleConflict } from '../types/conflict'
import ConflictTag from './ConflictTag.vue'
import { getConflictCounts } from '../utils/conflictMock'

const props = defineProps<{
  conflicts: ScheduleConflict[]
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'check'): void
  (e: 'view-detail', c: ScheduleConflict): void
}>()

const counts = computed(() => getConflictCounts(props.conflicts))
</script>

