import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: () => import('../views/Home.vue'),
    meta: { title: '首页', icon: 'home' },
  },
  {
    path: '/source',
    name: 'SourceManage',
    component: () => import('../views/SourceManage.vue'),
    meta: { title: '订阅源', icon: 'rss' },
  },
  {
    path: '/source/:id',
    name: 'FeedDetail',
    component: () => import('../views/FeedDetail.vue'),
  },
  {
    path: '/group/:id',
    name: 'GroupArticles',
    component: () => import('../views/GroupArticles.vue'),
  },
  {
    path: '/article/:id',
    name: 'ArticleDetail',
    component: () => import('../views/ArticleDetail.vue'),
  },
  {
    path: '/tags',
    name: 'Tags',
    component: () => import('../views/Tags.vue'),
    meta: { title: '标签', icon: 'tag' },
  },
  {
    path: '/tag/:id',
    name: 'TagArticles',
    component: () => import('../views/TagArticles.vue'),
  },
  {
    path: '/favorites',
    name: 'Favorites',
    component: () => import('../views/Favorites.vue'),
    meta: { title: '收藏', icon: 'star' },
  },
  {
    path: '/daily',
    name: 'DailyBriefings',
    component: () => import('../views/DailyBriefings.vue'),
    meta: { title: '日报', icon: 'podcast' },
  },
  {
    path: '/daily/:id',
    name: 'DailyBriefingDetail',
    component: () => import('../views/DailyBriefingDetail.vue'),
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('../views/Settings.vue'),
    meta: { title: '设置', icon: 'settings' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
