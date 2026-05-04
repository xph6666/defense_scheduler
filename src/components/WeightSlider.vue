<template>
  <div class="weight-slider flex items-center gap-4 py-2">
    <div class="label-box w-32 shrink-0">
      <span class="text-sm font-medium text-gray-700">{{ label }}</span>
      <p v-if="description" class="text-xs text-gray-400 mt-1">{{ description }}</p>
    </div>
    <el-slider
      v-model="internalValue"
      :min="0"
      :max="10"
      :step="1"
      show-stops
      class="flex-grow"
      @change="handleChange"
    />
    <div class="value-box w-8 text-right">
      <el-tag size="small" :type="internalValue > 7 ? 'danger' : internalValue > 3 ? 'warning' : 'info'">
        {{ internalValue }}
      </el-tag>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

const props = defineProps<{
  modelValue: number
  label: string
  description?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: number): void
}>()

const internalValue = ref(props.modelValue)

watch(() => props.modelValue, (newVal) => {
  internalValue.value = newVal
})

const handleChange = (val: any) => {
  emit('update:modelValue', val as number)
}
</script>

<style scoped>
.weight-slider :deep(.el-slider__runway) {
  margin-right: 12px;
}
</style>
