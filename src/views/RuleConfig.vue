<template>
  <main class="rule-config-container">
    <header class="page-intro">
      <div>
        <span class="eyebrow">{{ activeType }} · 第二步</span>
        <h1>{{ activeType }}安排要求</h1>
        <p>只配置当前答辩类型。保存后进入排期方案生成草稿。</p>
      </div>
      <RouterLink :to="defenseLink('/dashboard', activeType)" class="text-link">返回{{ activeType }}概览 →</RouterLink>
    </header>

    <el-alert v-if="!canManage" title="当前账号可以查看安排要求；修改规则需要管理员操作。" type="info" :closable="false" class="mb-4" />
    <el-alert v-if="loadError" :title="loadError" type="error" :closable="false" show-icon class="mb-4">
      <template #default><el-button link type="primary" @click="loadConfigs">重新读取</el-button></template>
    </el-alert>

    <div v-loading="loading" class="rule-config-panel">
      <RuleConfigForm
        v-if="!loadError && !loading"
        v-model="activeConfig"
        :readonly="!canManage"
        :saving="saving"
        @save="handleSave"
        @reset="handleReset"
      />
    </div>

    <div class="rule-next-step">
      <div><strong>准备好核对排期方案了吗？</strong><p>生成后可在同一页面查看分组、处理问题、发布和导出。</p></div>
      <RouterLink :to="defenseLink('/schedule-results', activeType)" class="text-link">前往排期方案 →</RouterLink>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useDefenseType, defenseLink } from '../utils/useDefenseType'
import RuleConfigForm from '../components/RuleConfigForm.vue'
import type { DefenseType, RuleConfig } from '../types/ruleConfig'
import { getDefaultRuleConfig } from '../utils/ruleConfigStorage'
import { createOperationLog } from '../api/operationLog'
import { getRuleConfig, saveRuleConfig } from '../api/ruleConfig'
import { useAdminGuard } from '../utils/adminGuard'

const activeType = useDefenseType()
const { canManage, requireAdmin } = useAdminGuard()
const loading = ref(true)
const saving = ref(false)
const loadError = ref('')
const configs = reactive<Record<DefenseType, RuleConfig>>({
  '预答辩': getDefaultRuleConfig('预答辩'),
  '正式答辩': getDefaultRuleConfig('正式答辩'),
  '中期答辩': getDefaultRuleConfig('中期答辩')
})

const activeConfig = computed({
  get: () => configs[activeType.value],
  set: (value: RuleConfig) => { configs[activeType.value] = value }
})

async function loadConfigs() {
  loading.value = true
  loadError.value = ''
  try {
    const config = await getRuleConfig(activeType.value)
    configs[activeType.value] = config
  } catch (cause) {
    loadError.value = cause instanceof Error ? cause.message : '要求读取失败，请重试。'
  } finally {
    loading.value = false
  }
}

async function handleSave(config: RuleConfig) {
  if (!requireAdmin() || saving.value || loading.value || loadError.value) return
  saving.value = true
  try {
    configs[config.defenseType] = await saveRuleConfig(config)
    try {
      await createOperationLog({
        type: '保存规则配置',
        module: '规则配置',
        description: `修改并保存了 [${config.defenseType}] 的规则配置`
      })
    } catch {
      ElMessage.warning('配置已保存，但操作日志写入失败')
    }
    ElMessage.success(`${config.defenseType}要求已保存`)
  } catch (cause) {
    ElMessage.error(cause instanceof Error ? cause.message : '配置保存失败，请稍后重试。')
  } finally {
    saving.value = false
  }
}

async function handleReset(type: string) {
  if (!requireAdmin() || saving.value || loading.value || loadError.value) return
  try {
    await ElMessageBox.confirm(`确定要恢复${type}默认要求吗？当前修改将丢失。`, '恢复默认要求', { type: 'warning' })
    saving.value = true
    const defenseType = type as DefenseType
    configs[defenseType] = await saveRuleConfig(getDefaultRuleConfig(defenseType))
    try {
      await createOperationLog({ type: '重置规则配置', module: '规则配置', description: `恢复了 [${type}] 的默认规则配置` })
    } catch {
      ElMessage.warning('默认要求已恢复，但操作日志写入失败')
    }
    ElMessage.success(`${type}默认要求已恢复`)
  } catch (cause) {
    if (cause instanceof Error) ElMessage.error(cause.message)
  } finally {
    saving.value = false
  }
}

watch(activeType, () => { void loadConfigs() })
onMounted(loadConfigs)
</script>
