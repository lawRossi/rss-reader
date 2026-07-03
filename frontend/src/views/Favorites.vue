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
    </div>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useArticleStore } from '../stores/articleStore'
import ArticleCard from '../components/ArticleCard.vue'

const articleStore = useArticleStore()

onMounted(() => {
  articleStore.loadArticles({ is_starred: true, page_size: 50 })
})
</script>
