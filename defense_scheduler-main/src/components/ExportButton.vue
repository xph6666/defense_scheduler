<template>
  <el-button
    type="success"
    :loading="loading"
    :disabled="disabled"
    @click="$emit('export')"
  >
    <template #icon>
      <el-icon><Download /></el-icon>
    </template>
    导出 Excel
  </el-button>
</template>

<script setup lang="ts">
import { Download } from '@element-plus/icons-vue'

defineProps<{
  disabled?: boolean
  loading?: boolean
}>()

defineEmits<{
  (e: 'export'): void
}>()
</script>
