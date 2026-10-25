<template>
  <el-container class="app-shell h-screen">
    <el-aside width="210px" class="app-sidebar">
      <AppSidebar />
    </el-aside>
    <el-container class="app-content">
      <el-header class="bg-white border-b shadow-sm p-0 h-14 flex items-center">
        <AppHeader />
      </el-header>
      <el-main ref="mainEl" class="app-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import AppSidebar from '../components/AppSidebar.vue'
import AppHeader from '../components/AppHeader.vue'

const route = useRoute()
const mainEl = ref<{ $el?: HTMLElement }>()

// 页面切换后回到顶部，避免沿用上一页的滚动位置
watch(() => route.fullPath, async () => {
  await nextTick()
  mainEl.value?.$el?.scrollTo({ top: 0 })
})
</script>
