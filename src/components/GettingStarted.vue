<template>
  <el-button link @click="visible = true">使用帮助</el-button>
  <el-dialog v-model="visible" title="按三个页面完成安排" width="min(600px, 94vw)">
    <p class="workflow-note mb-4">先在左侧选择答辩类型，再依次查看概览、确认安排要求，并在排期方案页生成、核对和发布。</p>
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
  { title: '概览：看当前进度', text: '工作台展示三类答辩状态；进入某类概览可查看参排人数、分组数和系统推荐的下一步。公共资料由三类答辩共用。' },
  { title: '安排要求：设定本次条件', text: '确认日期、每组人数、专家人数及回避规则。高级资格和软目标收在“更多要求”中。' },
  { title: '排期方案：生成到导出', text: '生成草稿后在同一页查看分组、定位冲突和未安排学生、调整安排、校验并发布，再选择 Word、Excel 或 PDF 导出。历史版本仍可查看。' }
]
</script>
