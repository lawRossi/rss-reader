<template>
  <div class="space-y-4">
    <h2 class="text-xl font-bold text-[var(--color-text)]">{{ group?.name || '分组' }}</h2>
    <div class="space-y-3">
      <ArticleCard v-for="article in articleStore.articles" :key="article.id" :article="article" />
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useArticleStore } from '../stores/articleStore'
import { useFeedStore } from '../stores/feedStore'
import ArticleCard from '../components/ArticleCard.vue'

const route = useRoute()
const articleStore = useArticleStore()
const feedStore = useFeedStore()

const group = computed(() => feedStore.groups.find((g) => g.id === Number(route.params.id)))

onMounted(async () => {
  await Promise.all([
    articleStore.loadArticles({ group_id: route.params.id, page_size: 50 }),
    feedStore.loadFeeds(),
  ])
})
</script>
