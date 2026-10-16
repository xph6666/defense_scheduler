<template>
  <div class="rule-config-container">
    <div class="page-intro"><div><h1>这次答辩，怎样安排？</h1></div></div>
    <WorkflowSteps :current="2" />
    <el-alert v-if="loadError" :title="loadError" type="error" :closable="false" show-icon class="mb-4" />
    <el-button v-if="loadError" @click="loadConfigs">重新读取要求</el-button>
    <div v-loading="loading" class="workbench-panel">
      <el-tabs v-model="activeType" :before-leave="() => !saving">
        <el-tab-pane v-for="type in defenseTypes" :key="type" :label="type" :name="type">
          <RuleConfigForm v-if="activeType === type && !loading && !loadError" v-model="configs[type]" :readonly="!canManage" :saving="saving" @save="handleSave" @continue="saveAndContinue" @reset="handleReset" />
        </el-tab-pane>
      </el-tabs>
      <RouterLink v-if="!canManage" :to="workflowLink('/schedule-results')" class="text-link">下一步：查看答辩安排 →</RouterLink>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import WorkflowSteps from '../components/WorkflowSteps.vue'
import { useRouter } from 'vue-router'
import { defenseTypes, useDefenseType, workflowLink } from '../utils/useDefenseType'
import RuleConfigForm from '../components/RuleConfigForm.vue'
import type { DefenseType, RuleConfig } from '../types/ruleConfig'
import { getDefaultRuleConfig } from '../utils/ruleConfigStorage'
import { createOperationLog } from '../api/operationLog'
import { getRuleConfig, saveRuleConfig } from '../api/ruleConfig'
import { useAdminGuard } from '../utils/adminGuard'

const activeType = useDefenseType()
const router = useRouter()
const loading = ref(true)
const saving = ref(false)
const loadError = ref('')
const { canManage, requireAdmin } = useAdminGuard()

const configs = reactive<Record<DefenseType, RuleConfig>>({
  '预答辩': getDefaultRuleConfig('预答辩'),
  '正式答辩': getDefaultRuleConfig('正式答辩'),
  '中期答辩': getDefaultRuleConfig('中期答辩')
})

const loadConfigs = async () => {
  loading.value = true; loadError.value = ''
  try {
    const results = await Promise.all(defenseTypes.map(type => getRuleConfig(type)))
    defenseTypes.forEach((type, index) => { configs[type] = results[index] })
  } catch (e) { loadError.value = e instanceof Error ? e.message : '要求读取失败，请重试' }
  finally { loading.value = false }
}
const saveAndContinue = async (config: RuleConfig) => {
  if (await handleSave(config)) await router.push(workflowLink('/schedule-results'))
}

const handleSave = async (config: RuleConfig) => {
  if (!requireAdmin() || saving.value || loading.value || loadError.value) return false
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
    ElMessage.success(`${config.defenseType} 要求已保存`)
    return true
  } catch (e) {
    const message = e instanceof Error ? e.message : '配置保存失败，请稍后重试'
    ElMessage.error(message)
    return false
  } finally { saving.value = false }
}

const handleReset = async (type: string) => {
  if (!requireAdmin() || saving.value || loading.value || loadError.value) return
  try {
    await ElMessageBox.confirm(`确定要恢复 [${type}] 的默认规则吗？当前修改将丢失。`, '确认恢复')
    saving.value = true
    const defenseType = type as DefenseType
    const defaultConfig = getDefaultRuleConfig(defenseType)
    configs[defenseType] = await saveRuleConfig(defaultConfig)
    try {
      await createOperationLog({
        type: '重置规则配置',
        module: '规则配置',
        description: `恢复了 [${type}] 的默认规则配置`
      })
    } catch {
      ElMessage.warning('默认配置已恢复，但操作日志写入失败')
    }
    ElMessage.success(`${type} 已恢复默认配置`)
  } catch (e) {
    if (e instanceof Error) {
      ElMessage.error(e.message)
    }
  } finally { saving.value = false }
}

onMounted(loadConfigs)
</script>
