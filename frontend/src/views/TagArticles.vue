<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <h2 class="text-xl font-bold text-[var(--color-text)]">
        标签: <span class="text-[var(--color-primary)]">{{ tag?.name }}</span>
      </h2>
      <button @click="$router.back()" class="text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-primary)]">← 返回</button>
    </div>
    <div class="space-y-3">
      <ArticleCard v-for="article in articleStore.articles" :key="article.id" :article="article" />
      <p v-if="!articleStore.articles.length" class="text-center py-12 text-[var(--color-text-secondary)]">该标签下暂无文章</p>
      <!-- Infinite scroll sentinel -->
      <div v-if="articleStore.articles.length > 0" ref="sentinelRef" class="flex justify-center py-6">
        <span v-if="loadingMore" class="text-sm text-[var(--color-text-secondary)]">加载中...</span>
        <span v-else-if="!hasMore" class="text-sm text-[var(--color-text-secondary)]">— 已加载全部文章 —</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useArticleStore } from '../stores/articleStore'
import { useTagStore } from '../stores/tagStore'
import { useInfiniteScroll } from '../composables/useInfiniteScroll'
import ArticleCard from '../components/ArticleCard.vue'

const route = useRoute()
const articleStore = useArticleStore()
const tagStore = useTagStore()

const tag = computed(() => tagStore.tags.find((t) => t.id === Number(route.params.id)))

// Infinite scroll
const { sentinelRef, hasMore, loadingMore } = useInfiniteScroll(
  articleStore.loadMore,
  computed(() => articleStore.total),
  computed(() => articleStore.articles.length),
)

onMounted(async () => {
  await Promise.all([
    articleStore.loadArticles({ tag_id: route.params.id, page_size: 50 }),
    tagStore.loadTags(),
  ])
})
</script>
