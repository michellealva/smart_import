<template>
  <!-- Shared header chrome for every screen, so the logo/title sit in the exact
       same place and nothing jumps when navigating between pages. -->
  <div
    class="sticky top-0 z-10 -mx-4 mb-6 flex items-center justify-between border-b border-gray-200 bg-gray-50/90 px-4 py-5 backdrop-blur-sm"
  >
    <div class="flex items-center gap-3">
      <img :src="logoUrl" alt="" class="h-9 w-9 rounded-lg" />
      <div>
        <h1 class="text-lg font-semibold text-gray-900">{{ title }}</h1>
        <p class="text-sm text-gray-600">{{ subtitle }}</p>
      </div>
    </div>
    <slot name="action" />
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
})
const logoUrl = '/assets/smart_import/logo.svg'
</script>
