<template>
  <el-tag :type="tagType" :effect="effect" size="small">
    {{ displayLabel }}
  </el-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'

export type StatusType = 
  | 'normal' 
  | 'success' 
  | 'warning' 
  | 'error' 
  | 'info' 
  | 'draft' 
  | 'completed'

const props = withDefaults(defineProps<{
  type?: string
  label?: string
  effect?: 'light' | 'dark' | 'plain'
}>(), {
  effect: 'light'
})

const tagType = computed(() => {
  switch (props.type) {
    case 'success':
    case 'completed': return 'success'
    case 'warning': return 'warning'
    case 'error': return 'danger'
    case 'primary': return ''
    case 'info':
    case 'normal': return 'info'
    case 'draft': return ''
    default: return ''
  }
})

const displayLabel = computed(() => {
  if (props.label) return props.label
  
  switch (props.type) {
    case 'normal': return '正常'
    case 'success': return '成功'
    case 'warning': return '警告'
    case 'error': return '错误'
    case 'info': return '提示'
    case 'draft': return '草稿'
    case 'completed': return '已完成'
    default: return '未知'
  }
})
</script>
