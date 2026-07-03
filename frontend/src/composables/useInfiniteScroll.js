import { ref, computed, watch, onUnmounted } from 'vue'

/**
 * Infinite scroll composable using IntersectionObserver.
 *
 * Watches the sentinel element reactively — handles cases where the element
 * is rendered asynchronously (e.g. after data loads).
 *
 * @param {Function} loadMoreFn - async function to load more items
 * @param {import('vue').Ref<number>} totalRef - ref with total item count
 * @param {import('vue').Ref<number>} loadedCountRef - ref with currently loaded item count
 * @param {Object} options - IntersectionObserver options
 * @returns {{ sentinelRef: import('vue').Ref<HTMLElement|null>, hasMore: import('vue').ComputedRef<boolean>, loadingMore: import('vue').Ref<boolean> }}
 */
export function useInfiniteScroll(loadMoreFn, totalRef, loadedCountRef, options = {}) {
  const sentinelRef = ref(null)
  const loadingMore = ref(false)
  let observer = null

  const hasMore = computed(() => {
    return loadedCountRef.value < totalRef.value
  })

  async function onIntersect() {
    if (loadingMore.value || !hasMore.value) return
    loadingMore.value = true
    try {
      await loadMoreFn()
    } finally {
      loadingMore.value = false
    }
  }

  // Set up observer when sentinel element appears (may be delayed if data loads async)
  const stopWatch = watch(sentinelRef, (el) => {
    // Clean up previous observer
    if (observer) {
      observer.disconnect()
      observer = null
    }

    if (!el) return

    observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          onIntersect()
        }
      },
      {
        root: null,
        rootMargin: '200px',
        threshold: 0,
        ...options,
      }
    )

    observer.observe(el)
  })

  onUnmounted(() => {
    stopWatch()
    if (observer) {
      observer.disconnect()
      observer = null
    }
  })

  return { sentinelRef, hasMore, loadingMore }
}
