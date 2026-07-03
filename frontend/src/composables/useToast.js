import { ref } from 'vue'

/**
 * Toast notification composable.
 *
 * Provides a reactive toast list and a showToast function.
 * Meant to be used at the App level and provided to children.
 */
export function useToast() {
  const toasts = ref([])
  let toastId = 0

  function showToast(message, type = 'info') {
    const id = ++toastId
    toasts.value.push({ id, message, type })
    setTimeout(() => {
      toasts.value = toasts.value.filter((t) => t.id !== id)
    }, 3000)
  }

  return {
    toasts,
    showToast,
  }
}
