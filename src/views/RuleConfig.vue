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
import { getRuleConfigFromStorage, saveRuleConfigToStorage, resetRuleConfig } from '../utils/ruleConfigStorage'
import { addOperationLog } from '../utils/operationLogStorage'

const activeType = ref<DefenseType>('预答辩')

const configs = reactive<Record<DefenseType, RuleConfig>>({
  '预答辩': getRuleConfigFromStorage('预答辩'),
  '正式答辩': getRuleConfigFromStorage('正式答辩'),
  '中期答辩': getRuleConfigFromStorage('中期答辩')
})

const handleSave = (config: RuleConfig) => {
  saveRuleConfigToStorage(config)
  addOperationLog({
    type: '保存规则配置',
    module: '规则配置',
    description: `修改并保存了 [${config.defenseType}] 的规则配置`
  })
  ElMessage.success(`${config.defenseType} 配置保存成功`)
}

const handleReset = (type: string) => {
  ElMessageBox.confirm(`确定要恢复 [${type}] 的默认规则吗？当前修改将丢失。`, '确认恢复').then(() => {
    const defenseType = type as DefenseType
    configs[defenseType] = resetRuleConfig(defenseType)
    addOperationLog({
      type: '重置规则配置',
      module: '规则配置',
      description: `恢复了 [${type}] 的默认规则配置`
    })
    ElMessage.success(`${type} 已恢复默认配置`)
  })
}

onMounted(() => {
  // 确保数据最新
  configs['预答辩'] = getRuleConfigFromStorage('预答辩')
  configs['正式答辩'] = getRuleConfigFromStorage('正式答辩')
  configs['中期答辩'] = getRuleConfigFromStorage('中期答辩')
})
</script>
