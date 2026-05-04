<template>
  <el-card shadow="never" class="soft-constraint-panel">
    <template #header>
      <div class="flex items-center justify-between">
        <div class="font-bold text-gray-800 flex items-center gap-2">
          <el-icon class="text-blue-500"><Histogram /></el-icon>
          软约束优化评分
        </div>
        <el-tag v-if="summary" size="small" type="info">生成时间：{{ summary.generatedAt }}</el-tag>
      </div>
    </template>

    <div v-if="!summary" class="py-10 text-center">
      <el-empty description="暂无软约束评分，请先生成排期结果。" />
    </div>

    <div v-else class="space-y-6">
      <!-- 总分展示 -->
      <div class="score-summary text-center p-4 bg-blue-50 rounded-lg border border-blue-100">
        <div class="text-xs text-blue-600 font-medium mb-1">综合优化得分</div>
        <div class="flex items-baseline justify-center gap-1">
          <span class="text-4xl font-black text-blue-600">{{ summary.totalScore }}</span>
          <span class="text-sm text-blue-400">/ {{ summary.maxScore }}</span>
        </div>
        <el-progress 
          :percentage="Math.round((summary.totalScore / summary.maxScore) * 100)" 
          :show-text="false"
          :stroke-width="10"
          class="mt-3"
          color="#2563eb"
        />
      </div>

      <!-- 分项评分 -->
      <div class="item-scores space-y-4">
        <div v-for="item in summary.scores" :key="item.key" class="score-item">
          <div class="flex justify-between items-center mb-1">
            <span class="text-sm font-medium text-gray-700">{{ item.label }}</span>
            <span class="text-xs font-bold text-gray-500">{{ item.score }} / {{ item.maxScore }}</span>
          </div>
          <el-progress 
            :percentage="Math.round((item.score / item.maxScore) * 100)" 
            :show-text="false"
            :stroke-width="6"
            size="small"
          />
          <p class="text-[10px] text-gray-400 mt-1">{{ item.description }}</p>
        </div>
      </div>

      <!-- 优化建议 -->
      <div v-if="summary.suggestions.length > 0" class="suggestions mt-6 pt-6 border-t border-gray-100">
        <div class="text-sm font-bold text-gray-800 mb-3 flex items-center gap-2">
          <el-icon class="text-orange-500"><InfoFilled /></el-icon>
          优化建议
        </div>
        <div class="space-y-2">
          <el-alert
            v-for="s in summary.suggestions"
            :key="s.id"
            :title="s.title"
            :type="s.level"
            :description="s.description"
            show-icon
            :closable="false"
          />
        </div>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { Histogram, InfoFilled } from '@element-plus/icons-vue'
import type { OptimizationSummary } from '../types/optimization'

defineProps<{
  summary: OptimizationSummary | null
}>()
</script>

<style scoped>
.soft-constraint-panel :deep(.el-card__header) {
  padding: 12px 20px;
}
</style>
