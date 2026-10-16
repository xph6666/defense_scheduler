<template>
  <el-container class="app-shell h-screen">
    <el-aside width="210px" class="app-sidebar">
      <AppSidebar />
    </el-aside>
    <el-container class="app-content">
      <el-header class="bg-white border-b shadow-sm p-0 h-14 flex items-center">
        <AppHeader />
      </el-header>
      <el-main class="app-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import AppSidebar from '../components/AppSidebar.vue'
import AppHeader from '../components/AppHeader.vue'
</script>
