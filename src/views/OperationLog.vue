<template>
  <div class="operation-log-container">
    <PageSection 
      title="操作日志" 
      description="查看前端记录的排期生成、人工调整、冲突检测、导出和规则配置等关键操作历史。"
    >
      <el-card shadow="never" class="bg-white">
        <OperationLogTable />
      </el-card>
    </PageSection>
  </div>
</template>

<script setup lang="ts">
import PageSection from '../components/PageSection.vue'
import OperationLogTable from '../components/OperationLogTable.vue'
</script>
