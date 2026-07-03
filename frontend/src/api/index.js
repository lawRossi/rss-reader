import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const message = error.response?.data?.detail || error.message || 'Request failed'
    console.error('API Error:', message)
    return Promise.reject(error)
  }
)

// ─── Settings ───
export const settingsApi = {
  getAll: () => api.get('/settings'),
  update: (settings) => api.put('/settings', { settings }),
  getTtsEngines: () => api.get('/settings/tts-engines'),
}

// ─── Daily Briefings ───
export const briefingsApi = {
  list: () => api.get('/daily-briefings'),
  get: (id) => api.get(`/daily-briefings/${id}`),
  generate: (data) => api.post('/daily-briefings/generate', data),
  delete: (id) => api.delete(`/daily-briefings/${id}`),
  getAudio: (id) => `/api/daily-briefings/${id}/audio`,
  export: (id, format) => api.get(`/daily-briefings/${id}/export`, { params: { format } }),
  getTtsBackends: () => api.get('/daily-briefings/tts-backends'),
}

// ─── Scheduled Tasks ───
export const scheduledTasksApi = {
  list: () => api.get('/scheduled-tasks'),
  get: (id) => api.get(`/scheduled-tasks/${id}`),
  create: (data) => api.post('/scheduled-tasks', data),
  update: (id, data) => api.put(`/scheduled-tasks/${id}`, data),
  delete: (id) => api.delete(`/scheduled-tasks/${id}`),
  toggle: (id) => api.post(`/scheduled-tasks/${id}/toggle`),
  executeNow: (id) => api.post(`/scheduled-tasks/${id}/execute-now`),
}

// ─── Groups ───
export const groupsApi = {
  list: () => api.get('/groups'),
  create: (data) => api.post('/groups', data),
  update: (id, data) => api.put(`/groups/${id}`, data),
  delete: (id) => api.delete(`/groups/${id}`),
}

// ─── Feeds ───
export const feedsApi = {
  list: () => api.get('/feeds'),
  get: (id) => api.get(`/feeds/${id}`),
  create: (data) => api.post('/feeds', data),
  update: (id, data) => api.put(`/feeds/${id}`, data),
  delete: (id) => api.delete(`/feeds/${id}`),
  fetch: (id) => api.post(`/feeds/${id}/fetch`),
  importOpml: (formData) =>
    api.post('/feeds/import-opml', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
}

// ─── Articles ───
export const articlesApi = {
  list: (params) => api.get('/articles', { params }),
  get: (id) => api.get(`/articles/${id}`),
  update: (id, data) => api.patch(`/articles/${id}`, data),
  batch: (data) => api.post('/articles/batch', data),
  export: (params) => api.get('/articles/export', { params }),
  fetchContent: (id) => api.post(`/articles/${id}/fetch-content`),
}

// ─── Tags ───
export const tagsApi = {
  list: () => api.get('/tags'),
  create: (data) => api.post('/tags', data),
  update: (id, data) => api.put(`/tags/${id}`, data),
  delete: (id) => api.delete(`/tags/${id}`),
  setArticleTags: (articleId, tagIds) =>
    api.post(`/tags/articles/${articleId}/tags`, { tag_ids: tagIds }),
}

// ─── Stats ───
export const statsApi = {
  get: () => api.get('/stats'),
}

// ─── Summary ───
export const summaryApi = {
  get: (articleId) => api.get(`/articles/${articleId}/summary`),
  generate: (articleId) => api.post(`/articles/${articleId}/summary`),
}

export default api
