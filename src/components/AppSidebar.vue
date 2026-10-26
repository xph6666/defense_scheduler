<template>
  <div class="h-full flex flex-col">
    <div class="h-14 flex items-center justify-center border-b font-bold text-lg text-blue-600 tracking-wide">
      答辩安排助手
    </div>
    <!-- [TASK-P02 修改] 选择答辩类型，并由路由查询参数保持各模块上下文。 -->
    <div class="px-4 py-3 border-b">
      <div class="text-xs text-gray-500 mb-2">当前答辩类型</div>
      <el-select v-model="selectedType" size="small" class="w-full" aria-label="当前答辩类型" @change="handleTypeChange">
        <el-option v-for="type in defenseTypes" :key="type" :label="type" :value="type" />
      </el-select>
    </div>
    <el-menu
      :default-active="activeMenu"
      class="border-r-0 flex-1"
      @select="handleSelect"
    >
      <el-menu-item index="/dashboard">
        <el-icon><DataBoard /></el-icon>
        <span>工作台</span>
      </el-menu-item>
      <el-menu-item index="/rule-config">
        <el-icon><Setting /></el-icon>
        <span>安排要求</span>
      </el-menu-item>
      <el-menu-item index="/schedule-results">
        <el-icon><Calendar /></el-icon>
        <span>分组与发布</span>
      </el-menu-item>
      <el-menu-item v-if="canManage" index="/schedule-wizard">
        <el-icon><Guide /></el-icon>
        <span>生成向导</span>
      </el-menu-item>
      <div class="nav-section">基础数据</div>
      <el-menu-item index="/teachers">
        <el-icon><Avatar /></el-icon>
        <span>教师/专家管理</span>
      </el-menu-item>
      <el-menu-item index="/students">
        <el-icon><User /></el-icon>
        <span>学生管理</span>
      </el-menu-item>
      <el-menu-item index="/classrooms">
        <el-icon><OfficeBuilding /></el-icon>
        <span>教室管理</span>
      </el-menu-item>
      <div class="nav-section">其他工具</div>
      <el-menu-item index="/operation-log">
        <el-icon><Document /></el-icon>
        <span>操作日志</span>
      </el-menu-item>
      <el-menu-item v-if="enableDemoTools" index="/demo-guide">
        <el-icon><Guide /></el-icon>
        <span>演示指南</span>
      </el-menu-item>
      <el-menu-item v-if="enableDemoTools" index="/acceptance-test">
        <el-icon><CircleCheck /></el-icon>
        <span>验收测试</span>
      </el-menu-item>
    </el-menu>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { DataBoard, Avatar, User, OfficeBuilding, Calendar, Setting, Document, Guide, CircleCheck } from '@element-plus/icons-vue'
import { enableDemoTools } from '../config/features'

import { defenseTypes, useDefenseType, workflowLink } from '../utils/useDefenseType'
import type { DefenseType } from '../types/schedule'
import { useAdminGuard } from '../utils/adminGuard'
const { canManage } = useAdminGuard()
const router = useRouter()
const route = useRoute()
const defenseType = useDefenseType()
const selectedType = ref<DefenseType>(defenseType.value)
const activeMenu = computed(() => route.path)

watch(defenseType, value => { selectedType.value = value })

const handleSelect = (path: string) => {
  if (route.path === path) return
  void router.push(workflowLink(path))
}

// 类型切换走路由，让当前页面（如向导）的未保存内容确认生效；被取消时恢复下拉显示
const handleTypeChange = async (value: DefenseType) => {
  if (value === defenseType.value) return
  const failure = await router.push({ path: route.path, query: { ...route.query, type: value } })
  if (failure) selectedType.value = defenseType.value
}
</script>
