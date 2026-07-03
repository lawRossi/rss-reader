<template>
  <div class="space-y-4">
    <div v-if="feed" class="flex items-center justify-between">
      <div>
        <h2 class="text-xl font-bold text-[var(--color-text)]">{{ feed.title }}</h2>
        <p class="text-sm text-[var(--color-text-secondary)] mt-1">{{ feed.site_url }}</p>
      </div>
      <button @click="fetchFeed" :disabled="fetching"
        class="px-4 py-2 bg-[var(--color-primary)] text-white rounded-lg text-sm hover:bg-[var(--color-primary-dark)] disabled:opacity-50">
        {{ fetching ? '抓取中...' : '刷新' }}
      </button>
    </div>

    <div class="space-y-3">
      <ArticleCard v-for="article in articles" :key="article.id" :article="article" />
      <!-- Infinite scroll sentinel -->
      <div v-if="articles.length > 0" ref="sentinelRef" class="flex justify-center py-6">
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
import { useFeedStore } from '../stores/feedStore'
import { feedsApi } from '../api'
import { useInfiniteScroll } from '../composables/useInfiniteScroll'
import ArticleCard from '../components/ArticleCard.vue'

const route = useRoute()
const articleStore = useArticleStore()
const feedStore = useFeedStore()

const feed = ref(null)
const fetching = ref(false)

const articles = computed(() => articleStore.articles)

// Infinite scroll
const { sentinelRef, hasMore, loadingMore } = useInfiniteScroll(
  articleStore.loadMore,
  computed(() => articleStore.total),
  computed(() => articleStore.articles.length),
)

onMounted(async () => {
  const feedId = route.params.id
  const res = await feedsApi.get(feedId)
  feed.value = res.data
  await articleStore.loadArticles({ feed_id: feedId, page_size: 50 })
})

async function fetchFeed() {
  fetching.value = true
  try {
    await feedsApi.fetch(feed.value.id)
    await articleStore.loadArticles({ feed_id: feed.value.id, page_size: 50 })
  } finally {
    fetching.value = false
  }
}
</script>
