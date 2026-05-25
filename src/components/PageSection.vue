<template>
  <div class="mb-6">
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-xl font-bold text-gray-800">{{ title }}</h2>
        <p v-if="description" class="text-sm text-gray-500 mt-1">{{ description }}</p>
      </div>
      <div v-if="$slots.extra">
        <slot name="extra"></slot>
      </div>
    </div>
    <div class="mt-4">
      <slot></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  description?: string
}>()
</script>
