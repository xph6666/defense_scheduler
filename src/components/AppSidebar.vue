<template>
  <div class="h-full flex flex-col">
    <div class="h-14 flex items-center justify-center border-b font-bold text-lg text-blue-600 tracking-wide">
      答辩安排助手
    </div>
    <el-menu
      :default-active="activeMenu"
      class="border-r-0 flex-1"
      @select="path => router.push(workflowLink(path))"
    >
      <el-menu-item index="/dashboard">
        <el-icon><DataBoard /></el-icon>
        <span>工作台 · 从这里开始</span>
      </el-menu-item>
      <el-menu-item v-if="canManage" index="/schedule-wizard">
        <el-icon><Guide /></el-icon>
        <span>分步安排向导</span>
      </el-menu-item>
      <div class="nav-section">完整管理</div>
      <el-menu-item index="/rule-config">
        <el-icon><Setting /></el-icon>
        <span>安排要求</span>
      </el-menu-item>
      <el-menu-item index="/schedule-results">
        <el-icon><Calendar /></el-icon>
        <span>答辩安排与导出</span>
      </el-menu-item>
      <div class="nav-section">资料管理</div>
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
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { DataBoard, Avatar, User, OfficeBuilding, Calendar, Setting, Document, Guide, CircleCheck } from '@element-plus/icons-vue'
import { enableDemoTools } from '../config/features'

import { workflowLink } from '../utils/useDefenseType'
import { useAdminGuard } from '../utils/adminGuard'
const { canManage } = useAdminGuard()
const router = useRouter()
const route = useRoute()
const activeMenu = computed(() => route.path)
</script>
