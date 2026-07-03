<template>
  <div class="min-h-screen bg-[var(--color-bg)]">
    <!-- Mobile Header -->
    <header class="md:hidden fixed top-0 left-0 right-0 z-50 bg-[var(--color-surface)] border-b border-[var(--color-border)] px-4 h-14 flex items-center justify-between">
      <h1 class="text-lg font-bold text-[var(--color-primary)]">RSS Reader</h1>
      <button @click="toggleTheme" class="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800">
        <span v-if="isDark" class="text-xl">☀️</span>
        <span v-else class="text-xl">🌙</span>
      </button>
    </header>

    <!-- Desktop Sidebar -->
    <aside class="hidden md:flex fixed left-0 top-0 bottom-0 w-64 bg-[var(--color-surface)] border-r border-[var(--color-border)] flex-col z-50">
      <div class="p-6 border-b border-[var(--color-border)]">
        <h1 class="text-2xl font-bold text-[var(--color-primary)]">RSS Reader</h1>
        <p class="text-sm text-[var(--color-text-secondary)] mt-1">信息聚合中心</p>
      </div>
      <nav class="flex-1 p-4 space-y-1 overflow-y-auto">
        <router-link
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-colors"
          :class="route.path === item.path || (item.path !== '/' && route.path.startsWith(item.path))
            ? 'bg-[var(--color-primary)]/10 text-[var(--color-primary)]'
            : 'text-[var(--color-text-secondary)] hover:bg-gray-100 dark:hover:bg-gray-800'"
        >
          <span class="text-lg">{{ item.icon }}</span>
          <span>{{ item.title }}</span>
        </router-link>
      </nav>
      <div class="p-4 border-t border-[var(--color-border)]">
        <button @click="toggleTheme" class="flex items-center gap-3 px-4 py-3 rounded-lg text-sm text-[var(--color-text-secondary)] hover:bg-gray-100 dark:hover:bg-gray-800 w-full">
          <span class="text-lg">{{ isDark ? '☀️' : '🌙' }}</span>
          <span>{{ isDark ? '亮色模式' : '暗色模式' }}</span>
        </button>
      </div>
    </aside>

    <!-- Main Content -->
    <main class="md:ml-64 pt-14 md:pt-0 min-h-screen">
      <div class="max-w-4xl mx-auto p-4 md:p-8">
        <router-view v-slot="{ Component }">
          <transition name="page" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </div>
    </main>

    <!-- Mobile Bottom Navigation -->
    <nav class="md:hidden fixed bottom-0 left-0 right-0 z-50 bg-[var(--color-surface)] border-t border-[var(--color-border)] safe-area-bottom">
      <div class="flex justify-around items-center h-16">
        <router-link
          v-for="item in mobileNavItems"
          :key="item.path"
          :to="item.path"
          class="flex flex-col items-center gap-1 px-3 py-2 rounded-lg text-xs transition-colors"
          :class="route.path === item.path
            ? 'text-[var(--color-primary)]'
            : 'text-[var(--color-text-secondary)]'"
        >
          <span class="text-xl">{{ item.icon }}</span>
          <span>{{ item.title }}</span>
        </router-link>
      </div>
    </nav>

    <!-- Toast notifications -->
    <div class="fixed top-4 right-4 z-[100] space-y-2">
      <div
        v-for="toast in toasts"
        :key="toast.id"
        class="px-4 py-3 rounded-lg shadow-lg text-sm font-medium transition-all"
        :class="toast.type === 'success' ? 'bg-[var(--color-primary)] text-white' : toast.type === 'error' ? 'bg-red-500 text-white' : 'bg-[var(--color-surface)] text-[var(--color-text)] border border-[var(--color-border)]'"
      >
        {{ toast.message }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { useRoute } from 'vue-router'
import { provide } from 'vue'
import { useTheme } from './composables/useTheme'
import { useToast } from './composables/useToast'

const route = useRoute()

// Theme management (extracted composable)
const { isDark, toggleTheme } = useTheme()

// Toast system (extracted composable)
const { toasts, showToast } = useToast()
provide('showToast', showToast)

const navItems = [
  { path: '/', title: '首页', icon: '🏠' },
  { path: '/source', title: '订阅源', icon: '📡' },
  { path: '/daily', title: '日报', icon: '🎙️' },
  { path: '/favorites', title: '收藏', icon: '⭐' },
  { path: '/tags', title: '标签', icon: '🏷️' },
  { path: '/settings', title: '设置', icon: '⚙️' },
]

const mobileNavItems = [
  { path: '/', title: '首页', icon: '🏠' },
  { path: '/source', title: '订阅', icon: '📡' },
  { path: '/daily', title: '日报', icon: '🎙️' },
  { path: '/favorites', title: '收藏', icon: '⭐' },
  { path: '/settings', title: '设置', icon: '⚙️' },
]
</script>

<style>
.safe-area-bottom {
  padding-bottom: env(safe-area-inset-bottom, 0px);
}
</style>
