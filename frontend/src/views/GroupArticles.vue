<template>
  <div class="space-y-4">
    <h2 class="text-xl font-bold text-[var(--color-text)]">{{ group?.name || '分组' }}</h2>
    <div class="space-y-3">
      <ArticleCard v-for="article in articleStore.articles" :key="article.id" :article="article" />
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
import { useRoute } from 'vue-router'
import { useArticleStore } from '../stores/articleStore'
import { useFeedStore } from '../stores/feedStore'
import { useInfiniteScroll } from '../composables/useInfiniteScroll'
import ArticleCard from '../components/ArticleCard.vue'

const route = useRoute()
const articleStore = useArticleStore()
const feedStore = useFeedStore()

const group = computed(() => feedStore.groups.find((g) => g.id === Number(route.params.id)))

// Infinite scroll
const { sentinelRef, hasMore, loadingMore } = useInfiniteScroll(
  articleStore.loadMore,
  computed(() => articleStore.total),
  computed(() => articleStore.articles.length),
)

onMounted(async () => {
  await Promise.all([
    articleStore.loadArticles({ group_id: route.params.id, page_size: 50 }),
    feedStore.loadFeeds(),
  ])
})
</script>
