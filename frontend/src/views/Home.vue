<template>
  <div class="space-y-6">
    <!-- Welcome section -->
    <div class="bg-[var(--color-primary)]/80 dark:bg-[var(--color-surface)] rounded-2xl p-6 text-gray-900 dark:text-white">
      <h2 class="text-2xl font-bold">欢迎回来 👋</h2>
      <p class="mt-2 opacity-90">今天的阅读摘要</p>
      <div class="grid grid-cols-3 gap-4 mt-6">
        <div class="bg-white/20 rounded-xl p-4 text-center backdrop-blur-sm">
          <div class="text-2xl font-bold">{{ todayCount }}</div>
          <div class="text-xs mt-1 opacity-80">今日新增</div>
        </div>
        <router-link to="/favorites" class="bg-white/20 rounded-xl p-4 text-center backdrop-blur-sm block hover:bg-white/30 transition-colors">
          <div class="text-2xl font-bold">{{ starredCount }}</div>
          <div class="text-xs mt-1 opacity-80">收藏文章</div>
        </router-link>
        <router-link to="/source" class="bg-white/20 rounded-xl p-4 text-center backdrop-blur-sm block hover:bg-white/30 transition-colors">
          <div class="text-2xl font-bold">{{ feedCount }}</div>
          <div class="text-xs mt-1 opacity-80">订阅源</div>
        </router-link>
      </div>
    </div>

    <!-- Recent articles -->
    <div>
      <div class="flex items-center justify-between mb-4">
        <h3 class="text-lg font-bold text-[var(--color-text)]">最近更新</h3>
      </div>
      <div v-if="loading || pageLoading" class="space-y-3">
        <div v-for="i in 5" :key="i" class="animate-pulse bg-[var(--color-surface)] rounded-xl p-4 border border-[var(--color-border)]">
          <div class="h-4 bg-gray-200 dark:bg-gray-700 rounded w-3/4"></div>
          <div class="h-3 bg-gray-200 dark:bg-gray-700 rounded w-1/2 mt-2"></div>
        </div>
      </div>
      <div v-else class="space-y-3">
        <ArticleCard
          v-for="article in articles"
          :key="article.id"
          :article="article"
        />
        <div v-if="articles.length === 0" class="text-center py-12 text-[var(--color-text-secondary)]">
          <p class="text-4xl mb-3">📭</p>
          <p>还没有文章，快去添加订阅源吧！</p>
          <router-link to="/source" class="inline-block mt-3 px-4 py-2 bg-[var(--color-primary)] text-white rounded-lg text-sm hover:bg-[var(--color-primary-dark)]">
            添加订阅源
          </router-link>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useArticleStore } from '../stores/articleStore'
import { useFeedStore } from '../stores/feedStore'
import { statsApi } from '../api'
import ArticleCard from '../components/ArticleCard.vue'

const articleStore = useArticleStore()
const feedStore = useFeedStore()

const articles = computed(() => articleStore.articles)
const loading = computed(() => articleStore.loading)
const feedCount = computed(() => feedStore.feeds.length)

// Local loading guard to prevent flash of stale data from other pages
const pageLoading = ref(true)

// Stats from backend API for accurate counts
const todayCount = ref(0)
const starredCount = ref(0)

async function loadStats() {
  try {
    const res = await statsApi.get()
    todayCount.value = res.data.today_count
    starredCount.value = res.data.starred_count
  } catch (e) {
    console.error('Failed to load stats:', e)
  }
}

onMounted(async () => {
  await Promise.all([
    articleStore.loadArticles({ page_size: 20 }),
    feedStore.loadFeeds(),
    loadStats(),
  ])
  pageLoading.value = false
})
</script>
