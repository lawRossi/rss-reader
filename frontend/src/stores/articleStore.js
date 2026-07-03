import { defineStore } from 'pinia'
import { ref } from 'vue'
import { articlesApi } from '../api'

export const useArticleStore = defineStore('articles', () => {
  const articles = ref([])
  const currentArticle = ref(null)
  const total = ref(0)
  const loading = ref(false)
  const params = ref({
    page: 1,
    page_size: 20,
    sort: 'published_at',
    order: 'desc',
  })

  async function loadArticles(filters = {}) {
    const page = filters.page ?? 1
    // Only show full-page loading skeleton on first page load (not during pagination)
    if (page === 1) loading.value = true
    try {
      // Build request params: persistent pagination + current filters
      const mergedParams = {
        ...params.value,
        ...filters,
        page,
      }

      const res = await articlesApi.list(mergedParams)
      if (page === 1) {
        articles.value = res.data.items
      } else {
        articles.value = [...articles.value, ...res.data.items]
      }
      total.value = res.data.total

      // Only persist pagination & sort params — NOT temporary query filters
      // (e.g. is_starred, feed_id, tag_id, group_id are page-specific and must NOT leak)
      params.value.page = page
      if (filters.page_size !== undefined) params.value.page_size = filters.page_size
      if (filters.sort !== undefined) params.value.sort = filters.sort
      if (filters.order !== undefined) params.value.order = filters.order
    } catch (e) {
      console.error('Failed to load articles:', e)
    } finally {
      if (page === 1) loading.value = false
    }
  }

  async function loadMore() {
    if (articles.value.length >= total.value) return
    await loadArticles({ page: params.value.page + 1 })
  }

  async function getArticle(id) {
    const res = await articlesApi.get(id)
    currentArticle.value = res.data
    return res.data
  }

  async function updateArticle(id, data) {
    const res = await articlesApi.update(id, data)
    if (currentArticle.value?.id === id) {
      currentArticle.value = res.data
    }
    // Update in list
    const idx = articles.value.findIndex((a) => a.id === id)
    if (idx >= 0) {
      articles.value[idx] = { ...articles.value[idx], ...res.data }
    }
    return res.data
  }

  async function batchAction(data) {
    await articlesApi.batch(data)
    // Reload current page
    await loadArticles()
  }

  return {
    articles,
    currentArticle,
    total,
    loading,
    params,
    loadArticles,
    loadMore,
    getArticle,
    updateArticle,
    batchAction,
  }
})
