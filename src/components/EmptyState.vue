<template>
  <el-empty :description="description">
    <template #default>
      <div v-if="title" class="text-gray-400 mb-2">{{ title }}</div>
      <el-button v-if="actionText" type="primary" link @click="$emit('action')">
        {{ actionText }}
      </el-button>
    </template>
  </el-empty>
</template>

<script setup lang="ts">
interface Props {
  title?: string
  description?: string
  actionText?: string
}

withDefaults(defineProps<Props>(), {
  description: '暂无数据'
})

defineEmits<{
  (e: 'action'): void
}>()
</script>
