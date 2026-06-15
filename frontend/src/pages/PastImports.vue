<template>
  <div class="mx-auto max-w-5xl px-4 pb-10">
    <PageHeader title="Past imports" subtitle="A history of the files you've brought in">
      <template #action>
        <router-link to="/" class="text-sm text-gray-600 hover:text-gray-900 hover:underline"
          >New import</router-link
        >
      </template>
    </PageHeader>

    <!-- Loading -->
    <div
      v-if="sessionsResource.loading"
      class="flex items-center gap-2 rounded-xl border border-gray-200 bg-white px-4 py-6 text-sm text-gray-700"
    >
      <LoadingIndicator class="h-4 w-4" /> Loading your past imports...
    </div>

    <!-- Empty -->
    <div
      v-else-if="!sessions.length"
      class="flex flex-col items-center rounded-xl border border-gray-200 bg-white py-12 text-center"
    >
      <FeatherIcon name="inbox" class="mb-3 h-8 w-8 text-gray-400" />
      <p class="text-base font-medium text-gray-900">No imports yet</p>
      <p class="mt-1 text-sm text-gray-600">
        When you import a file, it'll show up here.
      </p>
      <router-link
        to="/"
        class="mt-4 rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800"
        >Start an import</router-link
      >
    </div>

    <!-- List -->
    <div v-else class="space-y-3">
      <div v-for="s in sessions" :key="s.name" class="rounded-lg border border-gray-200 bg-white">
        <button
          class="flex w-full flex-wrap items-center gap-3 px-4 py-4 text-left"
          @click="openSession(s)"
        >
          <div
            class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full"
            :class="statusStyle(s.status).bg"
          >
            <FeatherIcon :name="statusStyle(s.status).icon" class="h-4 w-4" :class="statusStyle(s.status).text" />
          </div>
          <div class="min-w-0 flex-1">
            <p class="text-sm font-medium text-gray-900">
              {{ statusLabel(s.status) }}
              <span class="font-normal text-gray-500">· {{ formatDate(s.modified) }}</span>
            </p>
            <p class="mt-0.5 text-xs text-gray-600">
              {{ s.imported_count || 0 }} imported · {{ s.skipped_count || 0 }} skipped ·
              {{ s.failed_count || 0 }} failed
              <span v-if="s.owner_name" class="text-gray-400">· by {{ s.owner_name }}</span>
            </p>
          </div>
          <span class="shrink-0 rounded-full px-2 py-0.5 text-xs font-medium" :class="statusStyle(s.status).badge">
            {{ s.status }}
          </span>
          <span
            v-if="isResumable(s.status)"
            class="flex shrink-0 items-center gap-1 text-xs font-medium text-gray-600"
          >
            Continue <FeatherIcon name="arrow-right" class="h-4 w-4" />
          </span>
          <FeatherIcon
            v-else
            :name="expanded[s.name] ? 'chevron-up' : 'chevron-down'"
            class="h-4 w-4 shrink-0 text-gray-400"
          />
        </button>

        <div v-if="expanded[s.name]" class="border-t border-gray-100 px-4 py-3">
          <div v-if="!detail[s.name]" class="flex items-center gap-2 text-sm text-gray-600">
            <LoadingIndicator class="h-4 w-4" /> Loading…
          </div>
          <template v-else>
            <template v-if="(detail[s.name].created || []).length">
              <p class="mb-2 text-xs font-medium text-gray-700">
                Records created
                <span class="font-normal text-gray-500">· {{ detail[s.name].created_count }}</span>
              </p>
              <div class="mb-3 divide-y divide-gray-100 overflow-hidden rounded-lg border border-gray-200">
                <a
                  v-for="(rec, i) in detail[s.name].created"
                  :key="i"
                  :href="rec.route"
                  target="_blank"
                  class="flex items-center justify-between gap-2 px-3 py-1.5 text-xs hover:bg-gray-50"
                >
                  <span class="truncate text-gray-700"
                    ><span class="text-gray-400">{{ rec.doctype }}</span> · {{ rec.name }}</span
                  >
                  <FeatherIcon name="external-link" class="h-3.5 w-3.5 shrink-0 text-gray-400" />
                </a>
              </div>
            </template>
            <template v-if="(detail[s.name].log || []).length">
              <p class="mb-2 text-xs font-medium text-gray-700">Issues</p>
              <div class="space-y-1 rounded-lg border border-gray-200 p-3">
                <p v-for="(entry, i) in detail[s.name].log" :key="i" class="text-xs text-gray-700">
                  <span v-if="entry.row" class="text-gray-500">{{ entry.sheet }} · row {{ entry.row }}:</span>
                  {{ entry.message }}
                </p>
              </div>
            </template>
            <p
              v-if="!(detail[s.name].created || []).length && !(detail[s.name].log || []).length"
              class="text-sm text-gray-500"
            >
              Nothing was imported in this run.
            </p>
          </template>
        </div>
      </div>
    </div>

    <ErrorMessage class="mt-3" :message="errorMessage" />
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ErrorMessage, FeatherIcon, LoadingIndicator, createResource } from 'frappe-ui'
import PageHeader from '../components/PageHeader.vue'

const router = useRouter()
const errorMessage = ref('')

// A finished run (Completed) just expands to show its records; anything else
// (Reviewing, Ready to import, Partial, Failed) reopens in the wizard so the
// user can carry on from where they left off.
function isResumable(status) {
  return status !== 'Completed'
}

function openSession(s) {
  if (isResumable(s.status)) {
    router.push({ path: '/', query: { session: s.name } })
  } else {
    toggleDetail(s.name)
  }
}

const expanded = reactive({})
const detail = reactive({})
const detailResource = createResource({ url: 'smart_import.api.status' })
async function toggleDetail(name) {
  expanded[name] = !expanded[name]
  if (expanded[name] && !detail[name]) {
    try {
      detail[name] = await detailResource.submit({ session: name })
    } catch (e) {
      expanded[name] = false
      errorMessage.value = 'Could not load this import.'
    }
  }
}

const sessionsResource = createResource({
  url: 'smart_import.api.list_sessions',
  auto: true,
  onError(error) {
    errorMessage.value =
      (error && error.messages && error.messages.join(', ')) ||
      (error && error.message) ||
      'Could not load your past imports.'
  },
})

const sessions = computed(() => sessionsResource.data || [])

function statusLabel(status) {
  const map = {
    Completed: 'Import completed',
    Partial: 'Import completed with hiccups',
    Failed: 'Import failed',
    Importing: 'Import in progress',
    Validated: 'Ready to import',
    Profiled: 'Reviewing file',
  }
  return map[status] || status
}

function statusStyle(status) {
  if (status === 'Completed')
    return { bg: 'bg-green-100', text: 'text-green-700', icon: 'check', badge: 'bg-green-100 text-green-700' }
  if (status === 'Failed')
    return { bg: 'bg-red-100', text: 'text-red-700', icon: 'x', badge: 'bg-red-100 text-red-700' }
  if (status === 'Partial')
    return { bg: 'bg-amber-100', text: 'text-amber-700', icon: 'alert-triangle', badge: 'bg-amber-100 text-amber-700' }
  if (status === 'Importing')
    return { bg: 'bg-blue-100', text: 'text-blue-700', icon: 'loader', badge: 'bg-blue-100 text-blue-700' }
  return { bg: 'bg-gray-100', text: 'text-gray-600', icon: 'file-text', badge: 'bg-gray-100 text-gray-600' }
}

function formatDate(value) {
  if (!value) return ''
  const d = new Date(value.replace(' ', 'T'))
  if (isNaN(d.getTime())) return value
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}
</script>
