<template>
  <div class="space-y-4">
    <!-- Back button -->
    <button @click="$router.back()" class="text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-primary)]">
      ← 返回
    </button>

    <div v-if="loading" class="animate-pulse space-y-4">
      <div class="h-8 bg-gray-200 dark:bg-gray-700 rounded w-3/4"></div>
      <div class="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/2"></div>
      <div class="h-40 bg-gray-200 dark:bg-gray-700 rounded"></div>
    </div>

    <article v-else-if="article" class="bg-[var(--color-surface)] rounded-2xl p-6 border border-[var(--color-border)]">
      <!-- Header -->
      <h1 class="text-2xl font-bold text-[var(--color-text)] leading-snug">{{ article.title }}</h1>
      <div class="flex flex-wrap items-center gap-3 mt-3 text-sm text-[var(--color-text-secondary)]">
        <span v-if="article.feed_title">{{ article.feed_title }}</span>
        <span v-if="article.author">作者: {{ article.author }}</span>
        <span>{{ formatDate(article.published_at) }}</span>
      </div>

      <!-- Action bar -->
      <div class="flex flex-wrap items-center gap-2 mt-4 py-3 border-y border-[var(--color-border)]">
        <button @click="toggleRead"
          class="flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm transition-colors"
          :class="article.is_read ? 'bg-gray-100 dark:bg-gray-800 text-[var(--color-text-secondary)]' : 'bg-[var(--color-primary)]/10 text-[var(--color-primary)]'">
          {{ article.is_read ? '✅ 已读' : '◻️ 标记已读' }}
        </button>
        <button @click="toggleStar"
          class="flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm transition-colors"
          :class="article.is_starred ? 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-600' : 'bg-gray-100 dark:bg-gray-800 text-[var(--color-text-secondary)]'">
          {{ article.is_starred ? '⭐ 已收藏' : '☆ 收藏' }}
        </button>
        <button @click="openTagSelector"
          class="flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm bg-gray-100 dark:bg-gray-800 text-[var(--color-text-secondary)] hover:bg-gray-200 dark:hover:bg-gray-700">
          🏷️ 标签
        </button>
        <a :href="article.url" target="_blank"
          class="flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm bg-gray-100 dark:bg-gray-800 text-[var(--color-text-secondary)] hover:bg-gray-200 dark:hover:bg-gray-700">
          🔗 原文
        </a>
      </div>

      <!-- Tags display -->
      <div v-if="article.tags && article.tags.length" class="flex flex-wrap gap-2 mt-3">
        <span v-for="tag in article.tags" :key="tag.id"
          class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium"
          :style="{ backgroundColor: tag.color + '20', color: tag.color }">
          {{ tag.name }}
        </span>
      </div>

      <!-- Summary -->
      <div v-if="article.summary || summarizing" class="mt-4 p-4 bg-blue-50 dark:bg-blue-900/20 rounded-xl border border-blue-100 dark:border-blue-900/30">
        <div class="flex items-center justify-between mb-2">
          <span class="text-sm font-medium text-blue-600 dark:text-blue-400">📝 AI 摘要</span>
          <button @click="generateSummary" class="text-xs text-blue-500 hover:text-blue-600">重新生成</button>
        </div>
        <p class="text-sm text-[var(--color-text)] leading-relaxed">
          {{ article.summary }}<span v-if="summarizing && article.summary" class="inline-block w-0.5 h-4 bg-blue-500 ml-0.5 animate-pulse"></span>
        </p>
      </div>
      <button v-else @click="generateSummary" :disabled="summarizing"
        class="mt-4 w-full py-2 bg-gradient-to-r from-[var(--color-primary)] to-[var(--color-secondary)] text-white rounded-xl text-sm font-medium hover:opacity-90 disabled:opacity-50">
        {{ summarizing ? '📝 生成摘要中...' : '🤖 生成 AI 摘要' }}
      </button>

      <!-- Content -->
      <div class="mt-6">
        <div v-if="contentLoading" class="flex items-center justify-center py-8 text-sm text-[var(--color-text-secondary)]">
          <span class="inline-block w-4 h-4 border-2 border-[var(--color-primary)] border-t-transparent rounded-full animate-spin mr-2"></span>
          正在抓取原文内容...
        </div>
        <div v-else class="prose prose-sm dark:prose-invert max-w-none" v-html="article.content"></div>
      </div>
    </article>

    <!-- Tag selector modal -->
    <div v-if="showTagSelector" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" @click.self="showTagSelector = false">
      <div class="bg-[var(--color-surface)] rounded-2xl p-6 w-full max-w-sm">
        <h3 class="text-lg font-bold text-[var(--color-text)] mb-4">管理标签</h3>
        <div class="space-y-2 max-h-60 overflow-y-auto">
          <label v-for="tag in allTags" :key="tag.id"
            class="flex items-center gap-3 p-3 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer">
            <input type="checkbox" :value="tag.id" v-model="selectedTagIds"
              class="w-4 h-4 rounded border-gray-300 text-[var(--color-primary)] focus:ring-[var(--color-primary)]" />
            <span class="w-3 h-3 rounded-full" :style="{ backgroundColor: tag.color }"></span>
            <span class="text-sm text-[var(--color-text)]">{{ tag.name }}</span>
          </label>
        </div>
        <div class="flex gap-2 mt-4">
          <button @click="showTagSelector = false"
            class="flex-1 px-4 py-2 rounded-lg border border-[var(--color-border)] text-[var(--color-text)]">取消</button>
          <button @click="saveTags"
            class="flex-1 px-4 py-2 bg-[var(--color-primary)] text-white rounded-lg">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, inject } from 'vue'
import { useRoute } from 'vue-router'
import { useArticleStore } from '../stores/articleStore'
import { useTagStore } from '../stores/tagStore'
import { summaryApi, articlesApi } from '../api'

const route = useRoute()
const articleStore = useArticleStore()
const tagStore = useTagStore()
const showToast = inject('showToast')

const article = ref(null)
const loading = ref(true)
const summarizing = ref(false)
const contentLoading = ref(false)  // Track if we're fetching original content
const showTagSelector = ref(false)
const selectedTagIds = ref([])
const allTags = ref([])

onMounted(async () => {
  const data = await articleStore.getArticle(route.params.id)
  article.value = data
  await tagStore.loadTags()
  allTags.value = tagStore.tags
  selectedTagIds.value = (article.value.tags || []).map((t) => t.id)
  loading.value = false

  // Try to fetch full content from original URL if content is too short
  await tryFetchOriginalContent()
})

async function tryFetchOriginalContent() {
  if (!article.value) return

  // Only fetch if content is empty or very short (RSS summary noise)
  const content = article.value.content || ''
  if (content.length >= 500) return  // Already has substantial content

  contentLoading.value = true
  try {
    const res = await articlesApi.fetchContent(article.value.id)
    if (res.data.source === 'fetched') {
      article.value.content = res.data.content
      showToast('已加载原文内容', 'success')
    }
    // If source === 'existing', just keep current content silently
  } catch (e) {
    // Fetch failed silently — keep existing content
    console.debug('Original content fetch not available, using existing content')
  } finally {
    contentLoading.value = false
  }
}

function formatDate(dateStr) {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleString('zh-CN')
}

async function toggleRead() {
  await articleStore.updateArticle(article.value.id, { is_read: !article.value.is_read })
  article.value.is_read = !article.value.is_read
}

async function toggleStar() {
  await articleStore.updateArticle(article.value.id, { is_starred: !article.value.is_starred })
  article.value.is_starred = !article.value.is_starred
}

function openTagSelector() {
  selectedTagIds.value = (article.value.tags || []).map((t) => t.id)
  showTagSelector.value = true
}

async function saveTags() {
  try {
    const tags = await tagStore.setArticleTags(article.value.id, selectedTagIds.value)
    article.value.tags = tags
    showTagSelector.value = false
    showToast('标签已更新', 'success')
  } catch (e) {
    showToast('保存标签失败', 'error')
  }
}

async function generateSummary() {
  summarizing.value = true
  article.value.summary = ''  // Clear for streaming display
  let collected = []

  try {
    // force=true 绕过后端缓存，总是重新生成
    const response = await fetch(`/api/articles/${article.value.id}/summary?force=true`, { method: 'POST' })
    if (!response.ok) {
      // 非 2xx 响应（如网络层 429），直接抛出让 catch 处理
      const errData = await response.json().catch(() => ({}))
      throw new Error(errData.detail || `请求失败 (HTTP ${response.status})`)
    }
    const contentType = response.headers.get('content-type') || ''

    if (contentType.includes('text/event-stream')) {
      // SSE 流式响应
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let hasError = false

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              if (data.chunk) {
                collected.push(data.chunk)
                article.value.summary = collected.join('')
                // 主动让 Vue 刷新 DOM，避免在同一个 read() 批处理中批量更新
                await nextTick()
              } else if (data.summary) {
                article.value.summary = data.summary
                await nextTick()
              } else if (data.error) {
                hasError = true
                showToast(data.error, 'error')
              }
            } catch (e) {
              // Skip malformed JSON
            }
          }
        }
      }

      if (!hasError && collected.length > 0) {
        showToast('摘要生成完成', 'success')
      }
    } else {
      // JSON 响应（缓存命中情况，但 force=true 通常不会走这里）
      const data = await response.json()
      if (data.summary) {
        article.value.summary = data.summary
        showToast('摘要已加载', 'success')
      } else if (data.error) {
        showToast(data.error, 'error')
      }
    }
  } catch (e) {
    showToast('生成摘要失败，请检查 LLM 配置', 'error')
  } finally {
    summarizing.value = false
  }
}
</script>

<style>
.prose {
  color: var(--color-text);
  line-height: 1.8;
}
.prose img {
  max-width: 100%;
  border-radius: 8px;
}
.prose a {
  color: var(--color-primary);
  text-decoration: underline;
}
.prose blockquote {
  border-left: 3px solid var(--color-primary);
  padding-left: 1rem;
  margin: 1rem 0;
  opacity: 0.8;
}
.prose pre {
  background: #1e293b;
  color: #e2e8f0;
  padding: 1rem;
  border-radius: 8px;
  overflow-x: auto;
}
.prose code {
  font-size: 0.875em;
}
</style>
