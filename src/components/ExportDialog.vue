<template>
  <el-dialog
    v-model="visible"
    title="导出确认"
    width="500px"
    destroy-on-close
  >
    <div class="space-y-4">
      <div class="grid grid-cols-2 gap-4">
        <div class="p-3 bg-gray-50 rounded">
          <div class="text-xs text-gray-500">答辩类型</div>
          <div class="font-bold">{{ options.defenseType }}</div>
        </div>
        <div class="p-3 bg-gray-50 rounded">
          <div class="text-xs text-gray-500">总组数</div>
          <div class="font-bold">{{ stats.groupCount }}</div>
        </div>
        <div class="p-3 bg-gray-50 rounded">
          <div class="text-xs text-gray-500">总学生数</div>
          <div class="font-bold">{{ stats.studentCount }}</div>
        </div>
        <div class="p-3 bg-gray-50 rounded">
          <div class="text-xs text-gray-500">冲突数量</div>
          <div class="font-bold" :class="stats.conflictCount > 0 ? 'text-orange-500' : ''">
            {{ stats.conflictCount }}
          </div>
        </div>
      </div>

      <div v-if="stats.errorCount > 0" class="p-4 bg-red-50 border border-red-200 rounded flex items-start gap-3">
        <el-icon class="text-red-500 mt-1"><WarningFilled /></el-icon>
        <div>
          <div class="text-red-700 font-bold text-sm">当前排期存在硬冲突</div>
          <div class="text-red-600 text-xs mt-1">系统检测到 {{ stats.errorCount }} 处严重冲突，建议先处理后再导出。是否仍然继续导出？</div>
        </div>
      </div>

      <div v-else-if="stats.warningCount > 0" class="p-4 bg-orange-50 border border-orange-200 rounded flex items-start gap-3">
        <el-icon class="text-orange-500 mt-1"><InfoFilled /></el-icon>
        <div>
          <div class="text-orange-700 font-bold text-sm">当前排期存在提示项</div>
          <div class="text-orange-600 text-xs mt-1">系统检测到 {{ stats.warningCount }} 处警告，导出后请人工复核。</div>
        </div>
      </div>

      <div class="text-xs text-gray-400 p-2">
        <el-icon class="mr-1"><InfoFilled /></el-icon>
        提示：当前版本优先导出排期基础字段，颜色导出将在后续版本支持。
      </div>
    </div>

    <template #footer>
      <div class="flex justify-end gap-3">
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" @click="handleConfirm">继续导出</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { WarningFilled, InfoFilled } from '@element-plus/icons-vue'
import type { ExportOptions } from '../types/export'

const props = defineProps<{
  modelValue: boolean
  options: ExportOptions
  stats: {
    groupCount: number
    studentCount: number
    conflictCount: number
    errorCount: number
    warningCount: number
  }
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'confirm'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const handleConfirm = () => {
  visible.value = false
  emit('confirm')
}
</script>
