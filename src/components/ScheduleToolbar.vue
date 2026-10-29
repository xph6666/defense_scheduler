<template>
  <div class="flex flex-wrap items-center justify-between gap-3">
    <div class="flex flex-wrap items-center gap-3">
      <el-radio-group
        v-if="!guided"
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
        <el-radio-button label="agenda">日程视图</el-radio-button>
        <el-radio-button label="card">卡片视图</el-radio-button>
        <el-radio-button label="table">表格视图</el-radio-button>
      </el-radio-group>
    </div>

    <div class="flex flex-wrap items-center gap-2">
      <el-button v-if="canManage" type="primary" :loading="loading" @click="emit('generate')">
        {{ defenseType === '正式答辩' ? '沿用预答辩生成正式答辩' : defenseType === '预答辩' ? '生成预答辩草稿' : (hasResult ? '生成新草稿' : '生成排期草稿') }}
      </el-button>
      <el-button v-if="canManage && defenseType !== '中期答辩'" :disabled="loading" @click="emit('generate-linked')">联合生成两阶段</el-button>
      <el-dropdown trigger="click" :disabled="loading" @command="command => emit('refresh')">
        <el-button :disabled="loading">更多操作 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="refresh">刷新安排</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-button type="primary" plain :disabled="!hasResult || loading" @click="emit('export')">
        <template #icon><el-icon><Download /></el-icon></template>
        导出 Excel/Word/PDF
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Download } from '@element-plus/icons-vue'
import type { DefenseType } from '../types/schedule'

defineProps<{
  defenseType: DefenseType
  viewMode: 'agenda' | 'card' | 'table'
  loading?: boolean
  hasResult?: boolean
  canManage?: boolean
  guided?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:defenseType', v: DefenseType): void
  (e: 'update:viewMode', v: 'agenda' | 'card' | 'table'): void
  (e: 'generate'): void
  (e: 'generate-linked'): void
  (e: 'refresh'): void
  (e: 'export'): void
}>()
</script>
