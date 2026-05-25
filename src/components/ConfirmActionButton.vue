<template>
  <el-popconfirm
    :title="confirmTitle"
    :confirm-button-text="confirmText"
    :cancel-button-text="cancelText"
    @confirm="$emit('confirm')"
  >
    <template #reference>
      <el-button
        :type="type"
        :disabled="disabled"
        :loading="loading"
        size="small"
      >
        {{ label }}
      </el-button>
    </template>
  </el-popconfirm>
</template>

<script setup lang="ts">
interface Props {
  label: string
  confirmTitle?: string
  confirmText?: string
  cancelText?: string
  type?: 'primary' | 'success' | 'warning' | 'danger' | 'info'
  disabled?: boolean
  loading?: boolean
}

withDefaults(defineProps<Props>(), {
  confirmTitle: '确定要执行此操作吗？',
  confirmText: '确定',
  cancelText: '取消',
  type: 'primary'
})

defineEmits<{
  (e: 'confirm'): void
}>()
</script>
