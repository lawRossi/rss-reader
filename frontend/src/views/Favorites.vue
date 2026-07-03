<template>
  <div class="space-y-4">
    <h2 class="text-xl font-bold text-[var(--color-text)]">⭐ 收藏文章</h2>
    <div class="space-y-3">
      <ArticleCard v-for="article in articleStore.articles" :key="article.id" :article="article" />
      <div v-if="!articleStore.articles.length && !articleStore.loading"
        class="text-center py-12 text-[var(--color-text-secondary)]">
        <p class="text-4xl mb-3">📌</p>
        <p>还没有收藏的文章</p>
        <p class="text-sm mt-1">在阅读文章时点击星标即可收藏</p>
      </div>
      <!-- Infinite scroll sentinel -->
      <div v-if="articleStore.articles.length > 0" ref="sentinelRef" class="flex justify-center py-6">
        <span v-if="loadingMore" class="text-sm text-[var(--color-text-secondary)]">加载中...</span>
        <span v-else-if="!hasMore" class="text-sm text-[var(--color-text-secondary)]">— 已加载全部文章 —</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useArticleStore } from '../stores/articleStore'
import { useInfiniteScroll } from '../composables/useInfiniteScroll'
import ArticleCard from '../components/ArticleCard.vue'

const articleStore = useArticleStore()

// Infinite scroll
const { sentinelRef, hasMore, loadingMore } = useInfiniteScroll(
  articleStore.loadMore,
  computed(() => articleStore.total),
  computed(() => articleStore.articles.length),
)

onMounted(() => {
  articleStore.loadArticles({ is_starred: true, page_size: 50 })
})
</script>
