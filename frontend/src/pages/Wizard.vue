<template>
  <div class="mx-auto max-w-3xl px-4 py-8">
    <!-- Header -->
    <div class="mb-6 flex items-center justify-between">
      <div class="flex items-center gap-3">
        <img :src="logoUrl" alt="" class="h-9 w-9 rounded-lg" />
        <div>
          <h1 class="text-lg font-semibold text-gray-900">Smart Import</h1>
          <p class="text-sm text-gray-600">Bring your spreadsheet data in, without the headache</p>
        </div>
      </div>
      <a
        href="/app/smart-import-session"
        class="text-sm text-gray-600 hover:text-gray-900 hover:underline"
        >Past imports</a
      >
    </div>

    <!-- Step indicator -->
    <div class="mb-6 flex items-center gap-2 text-sm">
      <template v-for="(label, i) in stepLabels" :key="i">
        <div class="flex items-center gap-1.5">
          <div
            class="flex h-5 w-5 items-center justify-center rounded-full text-xs"
            :class="
              step > i + 1
                ? 'bg-green-100 text-green-700'
                : step === i + 1
                  ? 'bg-gray-900 text-white'
                  : 'border border-gray-300 text-gray-500'
            "
          >
            <FeatherIcon v-if="step > i + 1" name="check" class="h-3 w-3" />
            <span v-else>{{ i + 1 }}</span>
          </div>
          <span :class="step === i + 1 ? 'font-medium text-gray-900' : 'text-gray-500'">{{
            label
          }}</span>
        </div>
        <div v-if="i < stepLabels.length - 1" class="h-px w-6 bg-gray-300" />
      </template>
    </div>

    <!-- ============ STEP 1: Upload ============ -->
    <div v-if="step === 1" class="rounded-xl border border-gray-200 bg-white p-8">
      <FileUploader
        :fileTypes="['.xlsx', '.csv', '.xls']"
        :uploadArgs="uploadArgs"
        @success="onUploadSuccess"
        @failure="onUploadFailure"
      >
        <template #default="{ openFileSelector, uploading, progress }">
          <div
            class="flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-gray-300 px-6 py-14 text-center hover:border-gray-400"
            @click="prepareAndOpen(openFileSelector)"
          >
            <FeatherIcon name="upload-cloud" class="mb-3 h-8 w-8 text-gray-400" />
            <p v-if="uploading" class="text-base font-medium text-gray-900">
              Uploading... {{ progress }}%
            </p>
            <template v-else>
              <p class="text-base font-medium text-gray-900">
                Click to choose your Excel or CSV file
              </p>
              <p class="mt-1 text-sm text-gray-600">
                Files with multiple sheets work too — we'll figure out what's inside.
              </p>
            </template>
          </div>
        </template>
      </FileUploader>
      <p v-if="profileResource.loading" class="mt-4 flex items-center gap-2 text-sm text-gray-700">
        <LoadingIndicator class="h-4 w-4" /> Reading your file and figuring out what's inside...
      </p>
      <ErrorMessage class="mt-3" :message="errorMessage" />
    </div>

    <!-- ============ STEP 2: Review ============ -->
    <div v-else-if="step === 2" class="rounded-xl border border-gray-200 bg-white p-6">
      <h2 class="text-base font-semibold text-gray-900">Here's what we found in your file</h2>
      <p class="mb-4 mt-0.5 text-sm text-gray-600">
        Check our guesses below. You can change what each sheet should become, or skip a sheet.
      </p>

      <div class="space-y-2">
        <div
          v-for="entity in plan.entities"
          :key="entity.id"
          class="flex flex-wrap items-center gap-3 rounded-lg border border-gray-200 px-4 py-3"
        >
          <FeatherIcon name="file-text" class="h-5 w-5 shrink-0 text-gray-400" />
          <div class="min-w-0 flex-1">
            <p class="text-sm font-medium text-gray-900">
              {{ entity.rows }} rows from sheet "{{ entity.sheet }}"
            </p>
            <p class="text-xs text-gray-600">
              <template v-if="entity.doctype">
                {{ entity.mapped }} columns recognized<template v-if="entity.unmapped.length"
                  >, {{ entity.unmapped.length }} will be ignored ({{
                    entity.unmapped.slice(0, 3).join(', ')
                  }}<template v-if="entity.unmapped.length > 3">, ...</template>)</template
                >
                <template v-if="entity.links.length">
                  · connects to {{ entity.links.join(', ') }}</template
                >
              </template>
              <template v-else>This sheet will be skipped</template>
            </p>
          </div>
          <div class="w-52 shrink-0">
            <FormControl
              type="select"
              :options="doctypeOptions"
              :modelValue="entity.doctype"
              @update:modelValue="(v) => changeDoctype(entity.id, v)"
            />
          </div>
        </div>
      </div>

      <p
        v-if="importOrderText"
        class="mt-4 flex items-center gap-2 rounded-lg bg-gray-50 px-3 py-2 text-xs text-gray-600"
      >
        <FeatherIcon name="git-merge" class="h-3.5 w-3.5" />
        We'll import in this order so everything connects properly: {{ importOrderText }}
      </p>

      <div class="mt-5 flex justify-between">
        <Button label="Start over" @click="reset" />
        <Button
          variant="solid"
          :loading="validateResource.loading || setDoctypeResource.loading"
          label="Continue"
          @click="validateResource.submit({ session })"
        />
      </div>
      <ErrorMessage class="mt-3" :message="errorMessage" />
    </div>

    <!-- ============ STEP 3: Fix issues ============ -->
    <div v-else-if="step === 3" class="rounded-xl border border-gray-200 bg-white p-6">
      <template v-if="actionIssues.length || infoIssues.length">
        <h2 class="text-base font-semibold text-gray-900">A few things to sort out first</h2>
        <p class="mb-4 mt-0.5 text-sm text-gray-600">
          We checked everything — here's what needs a decision from you. Our suggestion is already
          selected.
        </p>

        <div class="space-y-3">
          <div
            v-for="issue in actionIssues"
            :key="issue.id"
            class="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3"
          >
            <div class="flex items-start gap-2">
              <FeatherIcon name="alert-triangle" class="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
              <div class="flex-1">
                <p class="text-sm text-gray-900">{{ issue.message }}</p>
                <p v-if="issue.values && issue.values.length" class="mt-0.5 text-xs text-gray-600">
                  For example: {{ issue.values.join(', ')
                  }}<template v-if="issue.count > issue.values.length">, ...</template>
                </p>
                <div class="mt-2 w-64">
                  <FormControl
                    type="select"
                    :options="issue.options"
                    v-model="decisions[issue.id]"
                  />
                </div>
              </div>
            </div>
          </div>

          <div
            v-for="issue in infoIssues"
            :key="issue.id"
            class="flex items-start gap-2 rounded-lg border border-gray-200 bg-gray-50 px-4 py-3"
          >
            <FeatherIcon name="info" class="mt-0.5 h-4 w-4 shrink-0 text-gray-500" />
            <p class="text-sm text-gray-700">{{ issue.message }}</p>
          </div>
        </div>
      </template>
      <template v-else>
        <div class="flex flex-col items-center py-8 text-center">
          <div class="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-green-100">
            <FeatherIcon name="check" class="h-6 w-6 text-green-700" />
          </div>
          <h2 class="text-base font-semibold text-gray-900">Everything looks good</h2>
          <p class="mt-1 text-sm text-gray-600">No problems found. You're ready to import.</p>
        </div>
      </template>

      <div class="mt-5 flex justify-between">
        <Button label="Back" @click="step = 2" />
        <Button
          variant="solid"
          :loading="startResource.loading"
          :label="actionIssues.length ? 'Apply my choices and import' : 'Start import'"
          @click="startImport"
        />
      </div>
      <ErrorMessage class="mt-3" :message="errorMessage" />
    </div>

    <!-- ============ STEP 4: Import ============ -->
    <div v-else-if="step === 4" class="rounded-xl border border-gray-200 bg-white p-6">
      <template v-if="!isFinished">
        <h2 class="text-base font-semibold text-gray-900">Importing your data...</h2>
        <p class="mt-0.5 text-sm text-gray-600">
          You can keep this page open — it updates by itself.
        </p>
        <div class="mt-5">
          <div class="h-2 w-full overflow-hidden rounded-full bg-gray-100">
            <div
              class="h-2 rounded-full bg-gray-900 transition-all duration-500"
              :style="{ width: progressPercent + '%' }"
            />
          </div>
          <p class="mt-2 text-sm text-gray-600">
            {{ liveStatus.progress?.done || 0 }} of {{ liveStatus.progress?.total || '...' }} rows
            <template v-if="liveStatus.progress?.sheet">
              · working on "{{ liveStatus.progress.sheet }}"</template
            >
          </p>
        </div>
      </template>

      <template v-else>
        <div class="flex items-center gap-3">
          <div
            class="flex h-10 w-10 items-center justify-center rounded-full"
            :class="liveStatus.failed ? 'bg-amber-100' : 'bg-green-100'"
          >
            <FeatherIcon
              :name="liveStatus.failed ? 'alert-triangle' : 'check'"
              class="h-5 w-5"
              :class="liveStatus.failed ? 'text-amber-700' : 'text-green-700'"
            />
          </div>
          <div>
            <h2 class="text-base font-semibold text-gray-900">{{ finishedTitle }}</h2>
            <p class="text-sm text-gray-600">{{ finishedSubtitle }}</p>
          </div>
        </div>

        <div class="mt-5 grid grid-cols-3 gap-3">
          <div class="rounded-lg bg-gray-50 p-4">
            <p class="text-xs text-gray-600">Imported</p>
            <p class="text-xl font-semibold text-gray-900">{{ liveStatus.imported }}</p>
          </div>
          <div class="rounded-lg bg-gray-50 p-4">
            <p class="text-xs text-gray-600">Skipped</p>
            <p class="text-xl font-semibold text-gray-900">{{ liveStatus.skipped }}</p>
          </div>
          <div class="rounded-lg bg-gray-50 p-4">
            <p class="text-xs text-gray-600">Failed</p>
            <p class="text-xl font-semibold text-gray-900">{{ liveStatus.failed }}</p>
          </div>
        </div>

        <div v-if="visibleLog.length" class="mt-5">
          <p class="mb-2 text-sm font-medium text-gray-900">Details</p>
          <div class="max-h-64 space-y-1 overflow-y-auto rounded-lg border border-gray-200 p-3">
            <p v-for="(entry, i) in visibleLog" :key="i" class="text-xs text-gray-700">
              <span v-if="entry.row" class="text-gray-500"
                >{{ entry.sheet }} · row {{ entry.row }}:</span
              >
              {{ entry.message }}
            </p>
          </div>
        </div>

        <div class="mt-5 flex justify-between">
          <Button label="Import another file" @click="reset" />
          <Button variant="solid" label="Open your app" @click="openApp" />
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import {
  Button,
  ErrorMessage,
  FeatherIcon,
  FileUploader,
  FormControl,
  LoadingIndicator,
  createResource,
} from 'frappe-ui'

const stepLabels = ['Upload', 'Review', 'Fix issues', 'Import']
const logoUrl = '/assets/smart_import/logo.svg'

const step = ref(1)
const session = ref(null)
const plan = ref({ entities: [], available_doctypes: [], order: [] })
const issues = ref({ issues: [], entities: [] })
const decisions = reactive({})
const liveStatus = ref({ status: '', progress: {}, imported: 0, failed: 0, skipped: 0, log: [] })
const errorMessage = ref('')
let pollTimer = null

// ---------- resources ----------
const newSessionResource = createResource({ url: 'smart_import.api.new_session' })

const profileResource = createResource({
  url: 'smart_import.api.profile',
  onSuccess(data) {
    plan.value = data
    errorMessage.value = ''
    step.value = 2
  },
  onError: showError,
})

const setDoctypeResource = createResource({
  url: 'smart_import.api.set_entity_doctype',
  onSuccess(data) {
    plan.value = data
    errorMessage.value = ''
  },
  onError: showError,
})

const validateResource = createResource({
  url: 'smart_import.api.validate',
  onSuccess(data) {
    issues.value = data
    errorMessage.value = ''
    for (const issue of data.issues || []) {
      if (issue.options && issue.options.length) {
        decisions[issue.id] = issue.default || issue.options[0].value
      }
    }
    step.value = 3
  },
  onError: showError,
})

const startResource = createResource({
  url: 'smart_import.api.start_import',
  onSuccess() {
    errorMessage.value = ''
    step.value = 4
    startPolling()
  },
  onError: showError,
})

const statusResource = createResource({
  url: 'smart_import.api.status',
  onSuccess(data) {
    liveStatus.value = data
    if (['Completed', 'Partial', 'Failed'].includes(data.status)) {
      stopPolling()
    }
  },
})

// ---------- step 1 ----------
const uploadArgs = computed(() => ({
  doctype: 'Smart Import Session',
  docname: session.value,
  fieldname: 'source_file',
  private: true,
}))

async function prepareAndOpen(openFileSelector) {
  errorMessage.value = ''
  if (!session.value) {
    session.value = await newSessionResource.submit()
  }
  openFileSelector()
}

function onUploadSuccess() {
  profileResource.submit({ session: session.value })
}

function onUploadFailure(error) {
  showError(error)
}

// ---------- step 2 ----------
const doctypeOptions = computed(() => [
  { label: "Don't import this sheet", value: '' },
  ...(plan.value.available_doctypes || []),
])

const importOrderText = computed(() => {
  const names = (plan.value.order || [])
    .map((id) => {
      const e = (plan.value.entities || []).find((x) => x.id === id)
      return e && e.doctype ? e.sheet : null
    })
    .filter(Boolean)
  return names.length > 1 ? names.join(' → ') : ''
})

function changeDoctype(entityId, doctype) {
  setDoctypeResource.submit({
    session: session.value,
    entity_id: entityId,
    doctype: doctype || '',
  })
}

// ---------- step 3 ----------
const actionIssues = computed(() =>
  (issues.value.issues || []).filter((i) => i.severity === 'action')
)
const infoIssues = computed(() => (issues.value.issues || []).filter((i) => i.severity === 'info'))

function startImport() {
  startResource.submit({
    session: session.value,
    decisions: JSON.stringify({ ...decisions }),
  })
}

// ---------- step 4 ----------
function startPolling() {
  stopPolling()
  pollTimer = setInterval(() => {
    statusResource.submit({ session: session.value })
  }, 1500)
  statusResource.submit({ session: session.value })
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

const isFinished = computed(() =>
  ['Completed', 'Partial', 'Failed'].includes(liveStatus.value.status)
)

const progressPercent = computed(() => {
  const p = liveStatus.value.progress || {}
  if (!p.total) return 5
  return Math.min(100, Math.round((p.done / p.total) * 100))
})

const finishedTitle = computed(() => {
  if (liveStatus.value.status === 'Completed') return 'All done!'
  if (liveStatus.value.status === 'Partial') return 'Done, with a few hiccups'
  return "The import couldn't finish"
})

const finishedSubtitle = computed(() => {
  const s = liveStatus.value
  if (s.status === 'Completed') return `${s.imported} records were imported successfully.`
  if (s.status === 'Partial')
    return `${s.imported} records imported. ${s.failed} couldn't be — details below.`
  return 'Details below. You can fix the file and try again.'
})

const visibleLog = computed(() => (liveStatus.value.log || []).slice(0, 50))

function openApp() {
  window.location.href = '/crm'
}

// ---------- shared ----------
function showError(error) {
  errorMessage.value =
    (error && error.messages && error.messages.join(', ')) ||
    (error && error.message) ||
    'Something went wrong. Please try again.'
}

function reset() {
  stopPolling()
  step.value = 1
  session.value = null
  plan.value = { entities: [], available_doctypes: [], order: [] }
  issues.value = { issues: [], entities: [] }
  Object.keys(decisions).forEach((k) => delete decisions[k])
  liveStatus.value = { status: '', progress: {}, imported: 0, failed: 0, skipped: 0, log: [] }
  errorMessage.value = ''
}

onBeforeUnmount(stopPolling)
</script>
