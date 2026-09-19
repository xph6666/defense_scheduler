<template>
  <el-button link @click="visible = true">使用帮助</el-button>
  <el-dialog v-model="visible" title="第一次使用？照着这 4 步做" width="min(600px, 94vw)">
    <p class="workflow-note mb-4">推荐从工作台点击“开始一次答辩安排”，先选类型，再按下面四个环节逐步完成。熟练后可直接使用左侧完整管理功能。</p>
    <ol class="help-steps">
      <li v-for="(item, index) in items" :key="item.title">
        <span class="step-number">{{ index + 1 }}</span>
        <div><strong>{{ item.title }}</strong><p>{{ item.text }}</p></div>
      </li>
    </ol>
    <div class="workflow-note">草稿可以反复调整；发布后会锁定内容。需要更改已发布安排时，生成新草稿即可，历史版本仍保留。</div>
    <template #footer><el-button type="primary" @click="visible = false">明白了</el-button></template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
const visible = ref(false)
const items = [
  { title: '准备好三份资料', text: '在工作台导入学生名单、教师名单和教室资料。已有资料可直接查看、补充，不用重新导入。' },
  { title: '确认日期和人数', text: '选择答辩类型，确认日期范围、每组学生和专家人数。职称要求、人数上下限等设置可展开查看。' },
  { title: '生成草稿，处理问题', text: '系统先生成草稿。有问题时根据提示补充资料，或点击具体分组的“调整”；换组使用“移动学生”。' },
  { title: '确认发布，导出文件', text: '核对无误后发布，再导出 Word 或 Excel。未发布也能导出草稿，文件会标注草稿状态。' }
]
</script>
