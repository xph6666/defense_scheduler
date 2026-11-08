<template>
  <el-dialog :model-value="modelValue" title="预答辩 ↔ 正式答辩 · 学生去向" width="min(980px, 95vw)" @update:model-value="emit('update:modelValue', $event)">
    <div v-loading="loading" style="min-height: 180px">
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <template v-if="mapping">
        <p class="text-sm text-gray-600 mb-4">预答辩 {{ mapping.preVersion ? `v${mapping.preVersion}` : '暂无来源版本' }} ↔ 正式答辩 {{ mapping.formalVersion ? `v${mapping.formalVersion}` : '尚未生成关联版本' }}。按学生唯一记录关联，调整分组后重新打开即可读取最新去向。</p>
        <div class="flex flex-wrap gap-2 mb-4">
          <el-tag v-for="(count, status) in mapping.summary" :key="status" :type="status === 'matched' ? 'success' : 'warning'">{{ labels[status] }} {{ count }}</el-tag>
        </div>
        <el-input v-model="search" clearable placeholder="搜索学号、姓名、预答辩组或正式答辩组" aria-label="搜索学生阶段去向" class="mb-3" />
        <el-table :data="rows" max-height="420" row-key="studentId" empty-text="没有符合条件的学生">
          <el-table-column prop="studentNo" label="学号" width="135" />
          <el-table-column prop="name" label="学生" width="100" />
          <el-table-column label="预答辩来源" min-width="180"><template #default="{ row }">{{ groupNames(row.preGroups) || '未找到来源' }}</template></el-table-column>
          <el-table-column label="正式答辩去向" min-width="180"><template #default="{ row }">{{ groupNames(row.formalGroups) || '尚未安排' }}</template></el-table-column>
          <el-table-column label="检查结果" width="130"><template #default="{ row }"><el-tag :type="row.status === 'matched' ? 'success' : 'warning'">{{ labels[row.status as keyof typeof labels] }}</el-tag></template></el-table-column>
        </el-table>
        <details v-if="mapping.links.length" class="mt-4">
          <summary class="cursor-pointer text-sm">查看小组间人数流向（支持拆分、合并）</summary>
          <el-table :data="mapping.links" max-height="220">
            <el-table-column prop="preGroup" label="预答辩组" /><el-table-column prop="formalGroup" label="正式答辩组" /><el-table-column prop="studentCount" label="学生数" />
          </el-table>
        </details>
      </template>
    </div>
    <template #footer><el-button @click="emit('update:modelValue', false)">关闭</el-button></template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { getStageMapping, type StageMapping } from '../api/schedule'
import type { DefenseType } from '../types/schedule'
const props = defineProps<{ modelValue: boolean; defenseType: DefenseType; versionId?: number }>()
const emit = defineEmits<{ (event: 'update:modelValue', value: boolean): void }>()
const mapping = ref<StageMapping | null>(null)
const search = ref('')
const error = ref('')
const loading = ref(false)
const labels = { matched: '已关联', pending_formal: '尚未进入正式', missing_pre: '缺少预答辩来源', duplicate: '重复分组' }
const groupNames = (groups: { name: string; campus: string }[]) => groups.map(g => `${g.campus} · ${g.name}`).join('、')
const rows = computed(() => (mapping.value?.rows || []).filter(row =>
  [row.studentNo, row.name, groupNames(row.preGroups), groupNames(row.formalGroups)].join(' ').includes(search.value.trim())))
let sequence = 0
watch(() => [props.modelValue, props.versionId, props.defenseType], async () => {
  const ticket = ++sequence
  mapping.value = null
  error.value = ''
  search.value = ''
  if (!props.modelValue || !props.versionId) return
  loading.value = true
  try {
    const result = await getStageMapping(props.defenseType, props.versionId)
    if (ticket === sequence) mapping.value = result
  } catch (e) {
    if (ticket === sequence) error.value = e instanceof Error ? e.message : '阶段去向读取失败'
  } finally { if (ticket === sequence) loading.value = false }
})
</script>
