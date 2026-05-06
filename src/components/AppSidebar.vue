<template>
  <div class="h-full flex flex-col">
    <div class="h-14 flex items-center justify-center border-b font-bold text-lg text-blue-600 tracking-wide">
      答辩排组排期系统
    </div>
    <el-menu
      :default-active="activeMenu"
      class="border-r-0 flex-1"
      router
    >
      <el-menu-item index="/dashboard">
        <el-icon><DataBoard /></el-icon>
        <span>首页</span>
      </el-menu-item>
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
      <el-menu-item index="/schedule-results">
        <el-icon><Calendar /></el-icon>
        <span>排期结果</span>
      </el-menu-item>
    </el-menu>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { DataBoard, Avatar, User, OfficeBuilding, Calendar } from '@element-plus/icons-vue'

const route = useRoute()
const activeMenu = computed(() => route.path)
</script>
