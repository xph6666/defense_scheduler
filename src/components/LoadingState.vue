<template>
  <div class="flex flex-col items-center justify-center py-10" v-loading="true">
    <div class="mt-12 text-sm text-gray-500">{{ text }}</div>
  </div>
</template>

<script setup lang="ts">
interface Props {
  text?: string
}

withDefaults(defineProps<Props>(), {
  text: '加载中，请稍候……'
})
</script>
