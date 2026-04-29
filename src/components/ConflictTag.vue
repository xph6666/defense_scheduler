<template>
  <el-tag :type="tagType" size="small">{{ text }}</el-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ConflictLevel } from '../types/conflict'

const props = defineProps<{
  level?: ConflictLevel
  status?: 'normal' | 'warning' | 'error'
}>()

const tagType = computed(() => {
  if (props.level) {
    if (props.level === 'error') return 'danger'
    if (props.level === 'warning') return 'warning'
    return 'info'
  }
  if (props.status === 'error') return 'danger'
  if (props.status === 'warning') return 'warning'
  return 'success'
})

const text = computed(() => {
  if (props.level) {
    if (props.level === 'error') return '错误'
    if (props.level === 'warning') return '警告'
    return '提示'
  }
  if (props.status === 'error') return '有冲突'
  if (props.status === 'warning') return '有提示'
  return '正常'
})
</script>

