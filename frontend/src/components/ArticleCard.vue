<template>
  <router-link
    :to="`/article/${article.id}`"
    class="block bg-[var(--color-surface)] rounded-xl p-4 border border-[var(--color-border)] hover:shadow-md transition-shadow"
  >
    <div class="flex items-start justify-between gap-3">
      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-2 text-xs text-[var(--color-text-secondary)] mb-1">
          <span v-if="article.feed_title" class="truncate">{{ article.feed_title }}</span>
          <span>·</span>
          <span>{{ formatDate(article.published_at || article.fetched_at) }}</span>
        </div>
        <h3 class="font-semibold text-[var(--color-text)] line-clamp-2" :class="{ 'opacity-60': article.is_read }">
          {{ article.title }}
        </h3>
        <p v-if="article.summary" class="text-sm text-[var(--color-text-secondary)] mt-1 line-clamp-2">
          {{ article.summary }}
        </p>
        <div class="flex items-center gap-2 mt-2">
          <span v-if="!article.is_read" class="w-2 h-2 rounded-full bg-[var(--color-primary)]"></span>
          <span v-if="article.is_starred" class="text-sm">⭐</span>
          <span v-for="tag in article.tags" :key="tag.id"
            class="inline-block px-2 py-0.5 rounded-full text-xs"
            :style="{ backgroundColor: tag.color + '20', color: tag.color }"
          >
            {{ tag.name }}
          </span>
        </div>
      </div>
    </div>
  </router-link>
</template>

<script setup>
defineProps({
  article: { type: Object, required: true },
})

function formatDate(dateStr) {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  const now = new Date()
  const diff = now - date
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
  if (diff < 604800000) return `${Math.floor(diff / 86400000)}天前`
  return date.toLocaleDateString('zh-CN')
}
</script>
