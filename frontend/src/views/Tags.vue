<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <h2 class="text-xl font-bold text-[var(--color-text)]">标签管理</h2>
      <button @click="showCreate = true"
        class="px-4 py-2 bg-[var(--color-primary)] text-white rounded-lg text-sm">+ 新建标签</button>
    </div>

    <div class="grid grid-cols-2 md:grid-cols-3 gap-3">
      <router-link v-for="tag in tagStore.tags" :key="tag.id"
        :to="`/tag/${tag.id}`"
        class="bg-[var(--color-surface)] rounded-xl p-4 border border-[var(--color-border)] hover:shadow-md transition-shadow">
        <div class="flex items-center gap-3">
          <span class="w-4 h-4 rounded-full" :style="{ backgroundColor: tag.color }"></span>
          <span class="font-medium text-[var(--color-text)]">{{ tag.name }}</span>
        </div>
        <p class="text-sm text-[var(--color-text-secondary)] mt-2">{{ tag.article_count }} 篇文章</p>
      </router-link>
    </div>

    <!-- Create tag modal -->
    <div v-if="showCreate" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" @click.self="showCreate = false">
      <div class="bg-[var(--color-surface)] rounded-2xl p-6 w-full max-w-sm">
        <h3 class="text-lg font-bold text-[var(--color-text)] mb-4">新建标签</h3>
        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-[var(--color-text)] mb-1">名称</label>
            <input v-model="newTagName" placeholder="标签名称"
              class="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]" />
          </div>
          <div>
            <label class="block text-sm font-medium text-[var(--color-text)] mb-1">颜色</label>
            <input v-model="newTagColor" type="color"
              class="w-full h-10 rounded-lg border border-[var(--color-border)] cursor-pointer" />
          </div>
          <div class="flex gap-2 pt-2">
            <button @click="showCreate = false"
              class="flex-1 px-4 py-2 rounded-lg border border-[var(--color-border)] text-[var(--color-text)]">取消</button>
            <button @click="createTag" :disabled="!newTagName"
              class="flex-1 px-4 py-2 bg-[var(--color-primary)] text-white rounded-lg disabled:opacity-50">创建</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, inject } from 'vue'
import { useTagStore } from '../stores/tagStore'

const tagStore = useTagStore()
const showToast = inject('showToast')
const showCreate = ref(false)
const newTagName = ref('')
const newTagColor = ref('#3B82F6')

onMounted(() => tagStore.loadTags())

async function createTag() {
  try {
    await tagStore.createTag({ name: newTagName.value, color: newTagColor.value })
    showCreate.value = false
    newTagName.value = ''
    showToast('标签创建成功！', 'success')
  } catch (e) {
    showToast(e.response?.data?.detail || '创建失败', 'error')
  }
}
</script>
