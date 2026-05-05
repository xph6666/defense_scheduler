<template>
  <div class="rule-config-container">
    <PageSection
      title="规则配置中心"
      description="用于配置不同答辩类型的基础人数规则、角色资格、时间限制及软约束权重。"
    >
      <el-tabs v-model="activeType" class="bg-white p-6 rounded-lg shadow-sm">
        <el-tab-pane label="预答辩" name="预答辩">
          <RuleConfigForm
            v-if="activeType === '预答辩'"
            v-model="configs.预答辩"
            @save="handleSave"
            @reset="handleReset"
          />
        </el-tab-pane>
        <el-tab-pane label="正式答辩" name="正式答辩">
          <RuleConfigForm
            v-if="activeType === '正式答辩'"
            v-model="configs.正式答辩"
            @save="handleSave"
            @reset="handleReset"
          />
        </el-tab-pane>
        <el-tab-pane label="中期答辩" name="中期答辩">
          <RuleConfigForm
            v-if="activeType === '中期答辩'"
            v-model="configs.中期答辩"
            @save="handleSave"
            @reset="handleReset"
          />
        </el-tab-pane>
      </el-tabs>
    </PageSection>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageSection from '../components/PageSection.vue'
import RuleConfigForm from '../components/RuleConfigForm.vue'
import type { DefenseType, RuleConfig } from '../types/ruleConfig'
import { getDefaultRuleConfig } from '../utils/ruleConfigStorage'
import { createOperationLog } from '../api/operationLog'
import { getRuleConfig, saveRuleConfig } from '../api/ruleConfig'

const activeType = ref<DefenseType>('预答辩')
const defenseTypes: DefenseType[] = ['预答辩', '正式答辩', '中期答辩']

const configs = reactive<Record<DefenseType, RuleConfig>>({
  '预答辩': getDefaultRuleConfig('预答辩'),
  '正式答辩': getDefaultRuleConfig('正式答辩'),
  '中期答辩': getDefaultRuleConfig('中期答辩')
})

const loadConfigs = async () => {
  const results = await Promise.all(defenseTypes.map(type => getRuleConfig(type)))
  defenseTypes.forEach((type, index) => {
    configs[type] = results[index]
  })
}

const handleSave = async (config: RuleConfig) => {
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
    ElMessage.success(`${config.defenseType} 配置保存成功`)
  } catch (e) {
    const message = e instanceof Error ? e.message : '配置保存失败，请稍后重试'
    ElMessage.error(message)
  }
}

const handleReset = async (type: string) => {
  try {
    await ElMessageBox.confirm(`确定要恢复 [${type}] 的默认规则吗？当前修改将丢失。`, '确认恢复')
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
  }
}

onMounted(() => {
  loadConfigs().catch(e => {
    const message = e instanceof Error ? e.message : '规则配置加载失败'
    ElMessage.error(message)
  })
})
</script>
