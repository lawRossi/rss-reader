import { ref, onMounted, watch } from 'vue'

/**
 * Theme composable — dark/light mode switching with persistence.
 *
 * Features:
 * - Auto-detects system preference via `prefers-color-scheme`
 * - Persists choice to localStorage
 * - Toggles `.dark` class on `<html>`
 */
export function useTheme() {
  const isDark = ref(false)

  function applyTheme(dark) {
    isDark.value = dark
    document.documentElement.classList.toggle('dark', dark)
    localStorage.setItem('theme', dark ? 'dark' : 'light')
  }

  function toggleTheme() {
    applyTheme(!isDark.value)
  }

  function setTheme(dark) {
    applyTheme(dark)
  }

  onMounted(() => {
    const savedTheme = localStorage.getItem('theme')
    if (savedTheme === 'dark') {
      applyTheme(true)
    } else if (savedTheme === 'light') {
      applyTheme(false)
    } else {
      // Follow system preference
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
      applyTheme(prefersDark)
    }
  })

  return {
    isDark,
    toggleTheme,
    setTheme,
  }
}
