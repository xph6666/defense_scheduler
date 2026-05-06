<template>
  <el-container class="h-screen bg-gray-50">
    <el-aside width="220px" class="bg-white border-r shadow-sm">
      <AppSidebar />
    </el-aside>
    <el-container>
      <el-header class="bg-white border-b shadow-sm p-0 h-14 flex items-center">
        <AppHeader />
      </el-header>
      <el-main class="p-6">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import AppSidebar from '../components/AppSidebar.vue'
import AppHeader from '../components/AppHeader.vue'
</script>
