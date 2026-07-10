<template>
  <div class="voice-dropdown-wrapper" ref="wrapperRef" style="position:relative">
    <!-- Trigger -->
    <button
      class="voice-dropdown-trigger"
      :class="{ 'opacity-50': disabled }"
      :disabled="disabled"
      @click="toggle"
      @keydown.down.prevent="openAndFocus"
      @keydown.enter.prevent="toggle"
      @keydown.space.prevent="toggle"
      type="button"
    >
      <span class="truncate">{{ displayText }}</span>
    </button>

    <!-- Panel -->
    <Teleport to="body">
      <div
        v-if="open"
        class="voice-dropdown-panel"
        :style="panelStyle"
        ref="panelRef"
        @keydown.escape="close"
      >
        <!-- Null option -->
        <button
          v-if="showNullOption"
          class="voice-option"
          :class="{ selected: modelValue === null }"
          @click="select(null)"
          type="button"
        >
          {{ nullLabel }}
        </button>

        <!-- Grouped options -->
        <template v-for="group in groupedOptions" :key="group.label">
          <div class="voice-option-group-label">{{ group.label }}</div>
          <button
            v-for="opt in group.options"
            :key="opt.value"
            class="voice-option"
            :class="{
              selected: modelValue === opt.value,
              highlighted: highlightIndex === getOptionIndex(opt.value),
            }"
            @click="select(opt.value)"
            @mouseenter="highlightIndex = getOptionIndex(opt.value)"
            type="button"
          >
            {{ opt.label }}
          </button>
        </template>

        <!-- Ungrouped options -->
        <button
          v-for="(opt, i) in ungroupedOptions"
          :key="opt.value"
          class="voice-option"
          :class="{
            selected: modelValue === opt.value,
            highlighted: highlightIndex === i,
          }"
          @click="select(opt.value)"
          @mouseenter="highlightIndex = i"
          type="button"
        >
          {{ opt.label }}
        </button>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'

const props = defineProps({
  modelValue: { type: String, default: null },
  options: { type: Array, default: () => [] },
  groups: { type: Array, default: null }, // [{label, options: [{value, label}]}]
  showNullOption: { type: Boolean, default: true },
  nullLabel: { type: String, default: '🌐 默认音色' },
  disabled: { type: Boolean, default: false },
  placeholder: { type: String, default: '请选择音色' },
})

const emit = defineEmits(['update:modelValue'])

const open = ref(false)
const wrapperRef = ref(null)
const panelRef = ref(null)
const highlightIndex = ref(-1)

// Normalize options: groups or flat list
const groupedOptions = computed(() => {
  if (props.groups) return props.groups
  return []
})

const ungroupedOptions = computed(() => {
  if (props.groups) return []
  return props.options.map(o => ({
    value: o.short_name,
    label: o.short_label || o.display_name,
  }))
})

const allOptions = computed(() => {
  const list = []
  if (props.showNullOption) list.push({ value: null, label: props.nullLabel })
  for (const g of groupedOptions.value) {
    for (const o of g.options) {
      list.push({ value: o.value, label: o.label })
    }
  }
  for (const o of ungroupedOptions.value) {
    list.push({ value: o.value, label: o.label })
  }
  return list
})

const displayText = computed(() => {
  if (props.modelValue === null || props.modelValue === undefined) {
    return props.nullLabel
  }
  const found = allOptions.value.find(o => o.value === props.modelValue)
  return found ? found.label : props.modelValue
})

const panelStyle = ref({})

function getOptionIndex(value) {
  return allOptions.value.findIndex(o => o.value === value)
}

function toggle() {
  if (props.disabled) return
  if (open.value) close()
  else openAndFocus()
}

function openAndFocus() {
  if (props.disabled) return
  open.value = true
  nextTick(() => {
    // Position panel below trigger
    if (wrapperRef.value) {
      const rect = wrapperRef.value.getBoundingClientRect()
      panelStyle.value = {
        position: 'fixed',
        top: rect.bottom + 2 + 'px',
        left: rect.left + 'px',
        width: Math.max(rect.width, 200) + 'px',
      }
    }
    // Highlight current value
    highlightIndex.value = getOptionIndex(props.modelValue)
    if (panelRef.value) panelRef.value.focus()
  })
}

function close() {
  open.value = false
  highlightIndex.value = -1
}

function select(value) {
  emit('update:modelValue', value)
  close()
}

function onClickOutside(e) {
  if (!open.value) return
  if (wrapperRef.value && !wrapperRef.value.contains(e.target)) {
    // Check if click is on the panel
    if (panelRef.value && panelRef.value.contains(e.target)) return
    close()
  }
}

onMounted(() => {
  document.addEventListener('mousedown', onClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('mousedown', onClickOutside)
})
</script>
