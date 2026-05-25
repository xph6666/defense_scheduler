<template>
  <el-form ref="formRef" :model="form" label-width="140px" class="rule-config-form">
    <!-- 基础规则 -->
    <el-card shadow="never" class="mb-4">
      <template #header>
        <div class="font-bold text-gray-800 flex items-center gap-2">
          <el-icon><Setting /></el-icon>基础规则
        </div>
      </template>
      <el-row :gutter="20">
        <el-col :span="8">
          <el-form-item label="启用该答辩类型">
            <el-switch v-model="form.enabled" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="启用导师回避">
            <el-switch v-model="form.mentorAvoidance" />
          </el-form-item>
        </el-col>
      </el-row>
    </el-card>

    <!-- 人数规则 -->
    <el-card shadow="never" class="mb-4">
      <template #header>
        <div class="font-bold text-gray-800 flex items-center gap-2">
          <el-icon><User /></el-icon>人数规则
        </div>
      </template>
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-8">
        <el-form-item label="学生目标人数">
          <el-input-number v-model="form.studentCount.target" :min="1" controls-position="right" class="w-full" />
        </el-form-item>
        <el-form-item label="学生最少人数">
          <el-input-number v-model="form.studentCount.min" :min="1" controls-position="right" class="w-full" />
        </el-form-item>
        <el-form-item label="学生最多人数">
          <el-input-number v-model="form.studentCount.max" :min="1" controls-position="right" class="w-full" />
        </el-form-item>
        <el-form-item label="专家目标人数">
          <el-input-number v-model="form.expertCount.target" :min="1" controls-position="right" class="w-full" />
        </el-form-item>
        <el-form-item label="专家最少人数">
          <el-input-number v-model="form.expertCount.min" :min="1" controls-position="right" class="w-full" />
        </el-form-item>
        <el-form-item label="秘书人数">
          <el-input-number v-model="form.secretaryCount" :min="1" controls-position="right" class="w-full" />
        </el-form-item>
      </div>
    </el-card>

    <!-- 角色资格规则 -->
    <el-card shadow="never" class="mb-4">
      <template #header>
        <div class="font-bold text-gray-800 flex items-center gap-2">
          <el-icon><Avatar /></el-icon>角色资格规则
        </div>
      </template>
      <el-row :gutter="20">
        <el-col :span="12" v-if="form.defenseType !== '正式答辩'">
          <el-form-item label="组长最低职称">
            <el-select v-model="form.roleQualification.leaderMinTitle" style="width: 100%">
              <el-option label="教授" value="教授" />
              <el-option label="副教授" value="副教授" />
              <el-option label="讲师" value="讲师" />
              <el-option label="其他" value="其他" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12" v-if="form.defenseType === '正式答辩'">
          <el-form-item label="主席最低职称">
            <el-select v-model="form.roleQualification.chairmanMinTitle" style="width: 100%">
              <el-option label="教授" value="教授" />
              <el-option label="副教授" value="副教授" />
              <el-option label="讲师" value="讲师" />
              <el-option label="其他" value="其他" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="秘书最低职称">
            <el-select v-model="form.roleQualification.secretaryMinTitle" style="width: 100%">
              <el-option label="教授" value="教授" />
              <el-option label="副教授" value="副教授" />
              <el-option label="讲师" value="讲师" />
              <el-option label="其他" value="其他" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="高级职称优先">
            <el-switch v-model="form.roleQualification.preferSeniorTitle" />
            <span class="ml-2 text-xs text-gray-400">优先安排正高职称担任主席/组长</span>
          </el-form-item>
        </el-col>
      </el-row>
    </el-card>

    <!-- 时间规则 -->
    <el-card shadow="never" class="mb-4">
      <template #header>
        <div class="font-bold text-gray-800 flex items-center gap-2">
          <el-icon><Calendar /></el-icon>时间规则
        </div>
      </template>
      <el-row :gutter="20">
        <el-col :span="8">
          <el-form-item label="排期开始日期">
            <el-date-picker
              v-model="form.startDate"
              type="date"
              placeholder="选择日期"
              value-format="YYYY-MM-DD"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="避开周末">
            <el-switch v-model="form.avoidWeekend" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="避开节假日">
            <el-switch v-model="form.avoidHoliday" />
          </el-form-item>
        </el-col>
      </el-row>
    </el-card>

    <!-- 软约束权重 -->
    <el-card shadow="never" class="mb-6">
      <template #header>
        <div class="font-bold text-gray-800 flex items-center gap-2">
          <el-icon><Operation /></el-icon>软约束权重 (0-10)
        </div>
      </template>
      <div class="space-y-4">
        <WeightSlider 
          v-model="form.softWeights.balanceStudentCount" 
          label="学生人数均衡" 
          description="尽量使各组学生人数接近目标值" 
        />
        <WeightSlider 
          v-model="form.softWeights.preferSeniorTeacher" 
          label="正高专家优先" 
          description="优先安排教授担任组长或主席" 
        />
        <WeightSlider 
          v-model="form.softWeights.avoidCrossCampus" 
          label="减少跨校区" 
          description="尽量减少教师在同一天跨校区排期" 
        />
        <WeightSlider 
          v-model="form.softWeights.externalMentorConcentration" 
          label="外院导师集中" 
          description="尽量将同一外院导师的学生集中排期" 
        />
        <WeightSlider 
          v-model="form.softWeights.preferAcademicMasterFirst" 
          label="学硕优先排期" 
          description="在场次选择上优先考虑学术型硕士" 
        />
      </div>
    </el-card>

    <div class="flex justify-center gap-4 py-4">
      <el-button @click="$emit('reset', form.defenseType)">恢复默认</el-button>
      <el-button type="primary" @click="$emit('save', form)">保存配置</el-button>
    </div>
  </el-form>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Setting, User, Avatar, Calendar, Operation } from '@element-plus/icons-vue'
import type { RuleConfig } from '../types/ruleConfig'
import WeightSlider from './WeightSlider.vue'

const props = defineProps<{
  modelValue: RuleConfig
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: RuleConfig): void
  (e: 'save', val: RuleConfig): void
  (e: 'reset', type: string): void
}>()

const form = ref<RuleConfig>(JSON.parse(JSON.stringify(props.modelValue)))

// 同步外部 props 到内部 form
watch(() => props.modelValue, (newVal) => {
  // 只有当内容真正改变时才更新，且使用合并而非替换，以保持引用稳定性
  const newStr = JSON.stringify(newVal)
  const oldStr = JSON.stringify(form.value)
  if (newStr !== oldStr) {
    form.value = JSON.parse(newStr)
  }
}, { deep: true })

// 监听内部 form 变化并通知外部
watch(form, (newVal) => {
  emit('update:modelValue', newVal)
}, { deep: true })
</script>

<style scoped>
.rule-config-form :deep(.el-card__header) {
  padding: 12px 20px;
  background-color: #f8fafc;
}
</style>
