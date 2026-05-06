<template>
  <div class="flex flex-wrap items-center justify-between gap-3">
    <div class="flex flex-wrap items-center gap-3">
      <el-radio-group
        :model-value="defenseType"
        @update:model-value="val => emit('update:defenseType', val as any)"
        :disabled="loading"
      >
        <el-radio-button label="预答辩">预答辩</el-radio-button>
        <el-radio-button label="正式答辩">正式答辩</el-radio-button>
        <el-radio-button label="中期答辩">中期答辩</el-radio-button>
      </el-radio-group>

      <el-radio-group
        :model-value="viewMode"
        @update:model-value="val => emit('update:viewMode', val as any)"
        :disabled="loading"
      >
        <el-radio-button label="card">卡片视图</el-radio-button>
        <el-radio-button label="table">表格视图</el-radio-button>
      </el-radio-group>
    </div>

    <div class="flex items-center gap-2">
      <el-button type="primary" :loading="loading" @click="emit('generate')">
        一键生成排期
      </el-button>
      <el-button :loading="loading" @click="emit('refresh')">
        刷新
      </el-button>
      <el-button :loading="loading" @click="emit('check-conflicts')">
        重新检测冲突
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { DefenseType } from '../types/schedule'

defineProps<{
  defenseType: DefenseType
  viewMode: 'card' | 'table'
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:defenseType', v: DefenseType): void
  (e: 'update:viewMode', v: 'card' | 'table'): void
  (e: 'generate'): void
  (e: 'refresh'): void
  (e: 'check-conflicts'): void
}>()
</script>
