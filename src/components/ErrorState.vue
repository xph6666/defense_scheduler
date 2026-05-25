<template>
  <div class="flex flex-col items-center justify-center py-10">
    <el-icon class="text-4xl text-red-500 mb-2"><CircleClose /></el-icon>
    <div class="text-lg font-bold text-gray-800">{{ title }}</div>
    <div class="text-sm text-gray-500 mt-1 mb-4">{{ description }}</div>
    <el-button v-if="retryText" type="primary" @click="$emit('retry')">
      {{ retryText }}
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { CircleClose } from '@element-plus/icons-vue'

interface Props {
  title?: string
  description?: string
  retryText?: string
}

withDefaults(defineProps<Props>(), {
  title: '加载失败',
  description: '请稍后重试',
  retryText: '重试'
})

defineEmits<{
  (e: 'retry'): void
}>()
</script>
