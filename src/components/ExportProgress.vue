<template>
  <div v-if="status !== 'idle'" class="fixed bottom-8 right-8 z-50 animate-bounce-in">
    <el-card shadow="always" class="border-none bg-opacity-90 backdrop-blur-sm">
      <div class="flex items-center gap-4 min-w-[300px]">
        <div class="flex-shrink-0">
          <el-icon v-if="status === 'exporting'" class="is-loading text-blue-500 text-2xl">
            <Loading />
          </el-icon>
          <el-icon v-else-if="status === 'success'" class="text-green-500 text-2xl">
            <CircleCheck />
          </el-icon>
          <el-icon v-else-if="status === 'error'" class="text-red-500 text-2xl">
            <CircleClose />
          </el-icon>
        </div>
        
        <div class="flex-grow">
          <div class="text-sm font-bold text-gray-800">{{ title }}</div>
          <div class="text-xs text-gray-500 mt-1">{{ message }}</div>
        </div>

        <el-button v-if="status !== 'exporting'" link @click="$emit('close')">
          <el-icon><Close /></el-icon>
        </el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Loading, CircleCheck, CircleClose, Close } from '@element-plus/icons-vue'
import type { ExportStatus } from '../types/export'

const props = defineProps<{
  status: ExportStatus
}>()

defineEmits<{
  (e: 'close'): void
}>()

const title = computed(() => {
  switch (props.status) {
    case 'exporting': return '正在生成导出文件'
    case 'success': return '导出成功'
    case 'error': return '导出失败'
    default: return ''
  }
})

const message = computed(() => {
  switch (props.status) {
    case 'exporting': return '请稍候，系统正在为您处理数据...'
    case 'success': return '文件已开始下载，请检查浏览器下载记录。'
    case 'error': return '导出过程中出现异常，请稍后重试。'
    default: return ''
  }
})
</script>

<style scoped>
.animate-bounce-in {
  animation: bounceIn 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}

@keyframes bounceIn {
  0% { transform: translateY(100px) scale(0.5); opacity: 0; }
  100% { transform: translateY(0) scale(1); opacity: 1; }
}
</style>
