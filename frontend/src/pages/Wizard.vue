<template>
  <div class="mx-auto max-w-5xl px-4 py-8">
    <!-- Header -->
    <div class="mb-6 flex items-center justify-between">
      <div class="flex items-center gap-3">
        <img :src="logoUrl" alt="" class="h-9 w-9 rounded-lg" />
        <div>
          <h1 class="text-lg font-semibold text-gray-900">Smart Import</h1>
          <p class="text-sm text-gray-600">Bring your spreadsheet data in, without the headache</p>
        </div>
      </div>
      <router-link
        to="/past"
        class="text-sm text-gray-600 hover:text-gray-900 hover:underline"
        >Past imports</router-link
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
      <p class="mt-4 text-center text-sm text-gray-600">
        Don't have a file yet?
        <router-link to="/template" class="font-medium text-gray-900 hover:underline"
          >Download a template</router-link
        >
        for any doctype.
      </p>
    </div>

    <!-- ============ STEP 2: Review ============ -->
    <div v-else-if="step === 2" class="rounded-xl border border-gray-200 bg-white p-6">
      <h2 class="text-base font-semibold text-gray-900">Here's what we found in your file</h2>
      <p class="mb-4 mt-0.5 text-sm text-gray-600">
        Check our guesses below. You can change what each sheet should become, or skip a sheet.
      </p>

      <div class="space-y-3">
        <div
          v-for="entity in plan.entities"
          :key="entity.id"
          class="rounded-lg border border-gray-200"
        >
          <div class="flex flex-wrap items-center gap-3 px-4 py-3">
            <FeatherIcon name="file-text" class="h-5 w-5 shrink-0 text-gray-400" />
            <div class="min-w-0 flex-1">
              <p class="text-sm font-medium text-gray-900">
                {{ entity.rows }} rows from sheet "{{ entity.sheet }}"
              </p>
              <p class="text-xs text-gray-600" v-if="!childInfo(entity)">
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
            <div class="w-56 shrink-0">
              <Autocomplete
                :options="doctypeOptions"
                :modelValue="doctypeModel(entity.doctype)"
                placeholder="Search a doctype…"
                @change="(opt) => changeDoctype(entity.id, opt ? opt.value : '')"
              />
            </div>
          </div>

          <!-- grouped mapping: main record + each child table, shown plainly -->
          <div v-if="childInfo(entity)" class="space-y-3 border-t border-gray-100 px-4 py-3">
            <!-- Main record (parent) -->
            <div class="overflow-hidden rounded-lg border border-gray-200 bg-white">
              <div class="flex items-center gap-1.5 border-b border-gray-100 bg-gray-50 px-3 py-2">
                <FeatherIcon name="file-text" class="h-3.5 w-3.5 text-gray-500" />
                <span class="text-xs font-semibold uppercase tracking-wide text-gray-600">
                  Main record · {{ entity.doctype }}
                </span>
              </div>
              <div class="px-3 py-2">
                <p class="text-sm text-gray-700">
                  <span class="font-medium">{{ mappingGroups(entity).parent.length }}</span>
                  column{{ mappingGroups(entity).parent.length === 1 ? '' : 's' }} go into the
                  {{ entity.doctype }} record.
                  <button
                    class="ml-1 text-gray-500 underline hover:text-gray-900"
                    @click="toggleCols(entity.id)"
                  >
                    {{ openCols[entity.id] ? 'hide' : 'see / change' }}
                  </button>
                </p>
                <div class="mt-2 border-t border-gray-100 pt-2">
                  <div class="flex items-center gap-2">
                    <span class="shrink-0 text-xs text-gray-600">Make one {{ entity.doctype }} per</span>
                    <div class="w-48 shrink-0">
                      <FormControl
                        type="select"
                        :options="groupKeyOptions(entity)"
                        :modelValue="entity.group_key || ''"
                        @update:modelValue="(v) => changeGroupKey(entity.id, v)"
                      />
                    </div>
                  </div>
                  <p class="mt-1 text-xs text-gray-500">
                    Rows that share this value are combined into one record.
                  </p>
                </div>
              </div>
            </div>

            <!-- Child tables (line items) -->
            <div
              v-for="ct in mappingGroups(entity).children"
              :key="ct.table_fieldname"
              class="overflow-hidden rounded-lg border border-indigo-200 bg-indigo-50/30"
            >
              <div class="flex items-center gap-1.5 border-b border-indigo-100 bg-indigo-50 px-3 py-2">
                <FeatherIcon name="list" class="h-3.5 w-3.5 text-indigo-500" />
                <span class="text-xs font-semibold uppercase tracking-wide text-indigo-700">
                  Line items · {{ ct.label }}
                </span>
                <span class="rounded bg-indigo-100 px-1.5 py-0.5 text-[10px] font-medium text-indigo-600">
                  child table
                </span>
              </div>
              <div class="space-y-1 px-3 py-2">
                <p class="text-xs text-gray-500">
                  Each row in your sheet adds one {{ ct.label }} line to its {{ entity.doctype }}.
                </p>
                <div
                  v-for="m in ct.fields"
                  :key="m.column"
                  class="flex items-center gap-2 text-sm"
                >
                  <span class="w-44 shrink-0 truncate text-gray-800">{{ m.column }}</span>
                  <FeatherIcon name="arrow-right" class="h-3 w-3 shrink-0 text-gray-400" />
                  <span class="truncate text-gray-700">{{ m.label }}</span>
                </div>
              </div>
            </div>

            <p v-if="entity.unmapped.length" class="text-xs text-gray-500">
              Ignored: {{ entity.unmapped.join(', ') }}
            </p>

            <!-- inline editor (toggled by "see / change" above) to move columns
                 between the main record and child tables -->
            <div
              v-if="openCols[entity.id]"
              class="space-y-1.5 rounded-lg border border-gray-200 bg-white p-3"
            >
              <p class="text-xs text-gray-500">
                For each column, choose where it goes and which field it fills.
              </p>
              <div
                v-for="cell in entity.cells"
                :key="cell.column"
                class="flex flex-wrap items-center gap-2"
              >
                <div class="w-36 shrink-0 truncate text-sm text-gray-800">{{ cell.column }}</div>
                <FeatherIcon name="arrow-right" class="h-3.5 w-3.5 shrink-0 text-gray-400" />
                <div class="w-48 shrink-0">
                  <FormControl
                    type="select"
                    :options="targetOptions(entity)"
                    :modelValue="cellTarget(entity, cell)"
                    @update:modelValue="(v) => changeTarget(entity, cell, v)"
                  />
                </div>
                <div v-if="cellTarget(entity, cell) !== 'skip'" class="w-52 shrink-0">
                  <FormControl
                    type="select"
                    :options="fieldOptionsFor(entity, cellTarget(entity, cell))"
                    :modelValue="cell.field || ''"
                    @update:modelValue="(v) => changeField(entity, cell, v)"
                  />
                </div>
              </div>
            </div>
          </div>

          <!-- data preview -->
          <div v-if="previewBySheet[entity.sheet]" class="border-t border-gray-100 px-4 py-3">
            <button
              class="mb-2 flex items-center gap-1.5 text-xs font-medium text-gray-600 hover:text-gray-900"
              @click="togglePreview(entity.sheet)"
            >
              <FeatherIcon
                :name="openPreviews[entity.sheet] ? 'chevron-down' : 'chevron-right'"
                class="h-3.5 w-3.5"
              />
              {{ openPreviews[entity.sheet] ? 'Hide' : 'Preview' }} data
            </button>
            <div
              v-if="openPreviews[entity.sheet]"
              class="max-h-72 overflow-auto rounded-lg border border-gray-200"
            >
              <table class="min-w-full border-collapse text-left text-xs">
                <thead class="sticky top-0 bg-gray-50 text-gray-600">
                  <tr>
                    <th
                      v-for="h in previewBySheet[entity.sheet].headers"
                      :key="h"
                      class="whitespace-nowrap border-b border-gray-200 px-3 py-2 font-medium"
                    >
                      {{ h }}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(row, ri) in previewBySheet[entity.sheet].rows"
                    :key="ri"
                    class="border-t border-gray-100"
                  >
                    <td
                      v-for="(c, ci) in row"
                      :key="ci"
                      class="whitespace-nowrap px-3 py-1.5 text-gray-700"
                    >
                      {{ formatCell(c) }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p class="mt-1.5 text-xs text-gray-500">
              Showing first {{ previewBySheet[entity.sheet].rows.length }} of
              {{ previewBySheet[entity.sheet].total_rows }} rows.
            </p>
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
              <div class="min-w-0 flex-1">
                <p class="text-sm text-gray-900">{{ issue.message }}</p>
                <p class="mt-0.5 text-xs text-gray-600">
                  Choose what each value should do. Our suggestion is pre-selected.
                </p>
                <div class="mt-2 space-y-1.5">
                  <div
                    v-for="val in issue.values"
                    :key="val.value"
                    class="flex flex-wrap items-center gap-2"
                  >
                    <div class="w-44 shrink-0 truncate text-sm text-gray-800">
                      <span class="font-medium">{{ val.value === '' ? '(blank)' : val.value }}</span>
                      <span class="text-gray-500">
                        · {{ val.count }} row{{ val.count > 1 ? 's' : '' }}</span
                      >
                    </div>
                    <FeatherIcon name="arrow-right" class="h-3.5 w-3.5 shrink-0 text-gray-400" />
                    <div class="w-44 shrink-0">
                      <FormControl
                        type="select"
                        :options="issue.choices"
                        :modelValue="choiceFor(issue, val)"
                        @update:modelValue="(v) => onChoice(issue, val, v)"
                      />
                    </div>
                    <div v-if="isManual(issue, val)" class="w-44 shrink-0">
                      <FormControl
                        type="text"
                        placeholder="Type a value"
                        :modelValue="manualText[mkey(issue, val)] || ''"
                        @update:modelValue="(v) => onManual(issue, val, v)"
                      />
                    </div>
                  </div>
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

        <!-- records created (clickable into the app) -->
        <div v-if="createdRecords.length" class="mt-5">
          <p class="mb-2 text-sm font-medium text-gray-900">
            Records created
            <span class="font-normal text-gray-500">· {{ liveStatus.created_count || createdRecords.length }}</span>
          </p>
          <div class="max-h-64 divide-y divide-gray-100 overflow-y-auto rounded-lg border border-gray-200">
            <a
              v-for="(rec, i) in createdRecords"
              :key="i"
              :href="rec.route"
              target="_blank"
              class="flex items-center justify-between gap-2 px-3 py-1.5 text-xs hover:bg-gray-50"
            >
              <span class="truncate text-gray-700">
                <span class="text-gray-400">{{ rec.doctype }}</span> · {{ rec.name }}
              </span>
              <FeatherIcon name="external-link" class="h-3.5 w-3.5 shrink-0 text-gray-400" />
            </a>
          </div>
          <p
            v-if="liveStatus.created_count > createdRecords.length"
            class="mt-1 text-xs text-gray-500"
          >
            Showing first {{ createdRecords.length }} of {{ liveStatus.created_count }}.
          </p>
        </div>

        <div v-if="visibleLog.length" class="mt-5">
          <p class="mb-2 text-sm font-medium text-gray-900">Issues</p>
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
  Autocomplete,
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
const manualText = reactive({})
const manualOn = reactive({})
const openPreviews = reactive({})
// child-table mapping state (Review step)
const fieldCache = reactive({}) // doctype -> { parent: [...], children: [...] }
const pendingTarget = reactive({}) // cell key -> target awaiting a field pick
const openCols = reactive({}) // entity id -> column editor expanded?
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
    previewResource.submit({ session: session.value })
    loadFieldsForPlan()
  },
  onError: showError,
})

const previewResource = createResource({
  url: 'smart_import.api.preview',
  onSuccess(data) {
    for (const s of data.sheets || []) openPreviews[s.name] = true
  },
})

const setDoctypeResource = createResource({
  url: 'smart_import.api.set_entity_doctype',
  onSuccess(data) {
    plan.value = data
    errorMessage.value = ''
    loadFieldsForPlan()
  },
  onError: showError,
})

const setColMapResource = createResource({
  url: 'smart_import.api.set_column_mapping',
  onSuccess(data) {
    plan.value = data
    errorMessage.value = ''
  },
  onError: showError,
})

const setGroupKeyResource = createResource({
  url: 'smart_import.api.set_group_key',
  onSuccess(data) {
    plan.value = data
    errorMessage.value = ''
  },
  onError: showError,
})

// fields (parent + child tables) for the per-column picker, fetched once per doctype
const fieldsResource = createResource({ url: 'smart_import.api.doctype_fields' })
function ensureFields(dt) {
  if (!dt || fieldCache[dt]) return
  fieldCache[dt] = { parent: [], children: [] } // reserve so we fetch only once
  fieldsResource
    .submit({ doctype: dt })
    .then((data) => {
      fieldCache[dt] = data
    })
    .catch(() => {
      delete fieldCache[dt]
    })
}
function loadFieldsForPlan() {
  for (const e of plan.value.entities || []) ensureFields(e.doctype)
}

const validateResource = createResource({
  url: 'smart_import.api.validate',
  onSuccess(data) {
    issues.value = data
    errorMessage.value = ''
    clearDecisions()
    for (const issue of data.issues || []) {
      if (issue.values && issue.values.length) {
        const m = {}
        for (const v of issue.values) m[v.value] = v.suggestion
        decisions[issue.id] = m
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

function prepareAndOpen(openFileSelector) {
  errorMessage.value = ''
  // Open the file dialog synchronously, while we still have the user's click
  // "gesture" — browsers block the file picker if it opens after an `await`.
  openFileSelector()
  // Create the session in parallel; it's a fast local insert and finishes long
  // before the user has picked a file, so the upload has a docname to attach to.
  if (!session.value) {
    newSessionResource
      .submit()
      .then((name) => {
        session.value = name
      })
      .catch(showError)
  }
}

function onUploadSuccess() {
  profileResource.submit({ session: session.value })
}

function onUploadFailure(error) {
  showError(error)
}

// ---------- step 2 ----------
// every importable doctype (any app), so any sheet can map to any doctype
const doctypesResource = createResource({
  url: 'smart_import.api.importable_doctypes',
  auto: true,
})
const doctypeOptions = computed(() => [
  { label: "Don't import this sheet", value: '' },
  ...(doctypesResource.data || []),
])
function doctypeModel(dt) {
  return { label: dt || "Don't import this sheet", value: dt || '' }
}

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

// ---------- step 2: child-table (line item) mapping ----------
// show the line-item controls only when the chosen doctype actually has child tables
function childInfo(entity) {
  const f = entity.doctype ? fieldCache[entity.doctype] : null
  return f && f.children && f.children.length ? f : null
}

function toggleCols(entityId) {
  openCols[entityId] = !openCols[entityId]
}

function groupKeyOptions(entity) {
  return (entity.cells || []).map((c) => ({ label: c.column, value: c.column }))
}

function changeGroupKey(entityId, column) {
  setGroupKeyResource.submit({ session: session.value, entity_id: entityId, column: column || '' })
}

function targetOptions(entity) {
  const f = fieldCache[entity.doctype] || { children: [] }
  return [
    { label: `${entity.doctype} (main record)`, value: 'parent' },
    ...(f.children || []).map((c) => ({ label: `Line item · ${c.label}`, value: 'child:' + c.table_fieldname })),
    { label: "Don't import", value: 'skip' },
  ]
}

// the available fields for a given target ('parent' or 'child:<table_fieldname>')
function fieldListFor(entity, target) {
  const f = fieldCache[entity.doctype] || { parent: [], children: [] }
  if (target === 'parent') return f.parent || []
  if (target && target.startsWith('child:')) {
    const tf = target.slice(6)
    const c = (f.children || []).find((x) => x.table_fieldname === tf)
    return c ? c.fields : []
  }
  return []
}

function fieldOptionsFor(entity, target) {
  return [
    { label: 'Choose a field…', value: '' },
    ...fieldListFor(entity, target).map((o) => ({
      label: o.reqd ? `${o.label} (required)` : o.label,
      value: o.fieldname,
    })),
  ]
}

// human label for a mapped field, looked up from the cached field options
function fieldLabelFor(entity, target, fieldname) {
  const f = fieldListFor(entity, target).find((o) => o.fieldname === fieldname)
  return f ? f.label : fieldname
}

function childTableLabel(entity, tf) {
  const ct = (entity.child_tables || []).find((x) => x.table_fieldname === tf)
  if (ct) return ct.label
  const f = fieldCache[entity.doctype]
  const cc = f && (f.children || []).find((x) => x.table_fieldname === tf)
  return cc ? cc.label : tf
}

// split an entity's mapped columns into the main record and each child table,
// for the grouped Review display
function mappingGroups(entity) {
  const parent = []
  const childrenMap = {}
  for (const c of entity.cells || []) {
    if (!c.field) continue
    if (c.target === 'child' && c.table_fieldname) {
      const tf = c.table_fieldname
      if (!childrenMap[tf]) {
        childrenMap[tf] = { table_fieldname: tf, label: childTableLabel(entity, tf), fields: [] }
      }
      childrenMap[tf].fields.push({
        column: c.column,
        label: fieldLabelFor(entity, 'child:' + tf, c.field),
      })
    } else {
      parent.push({ column: c.column, label: fieldLabelFor(entity, 'parent', c.field) })
    }
  }
  return { parent, children: Object.values(childrenMap) }
}

function ckey(entity, cell) {
  return entity.id + '::' + cell.column
}

function cellTarget(entity, cell) {
  const k = ckey(entity, cell)
  if (pendingTarget[k] !== undefined) return pendingTarget[k]
  if (cell.target === 'child' && cell.table_fieldname) return 'child:' + cell.table_fieldname
  return cell.field ? 'parent' : 'skip'
}

function commitMapping(entity, cell, target, fieldname) {
  let table_fieldname = null
  let fname = fieldname || ''
  if (target === 'skip') fname = ''
  else if (target.startsWith('child:')) table_fieldname = target.slice(6)
  setColMapResource
    .submit({
      session: session.value,
      entity_id: entity.id,
      column: cell.column,
      fieldname: fname,
      table_fieldname,
    })
    .finally(() => {
      delete pendingTarget[ckey(entity, cell)]
    })
}

function changeTarget(entity, cell, v) {
  const k = ckey(entity, cell)
  if (v === 'skip') {
    delete pendingTarget[k]
    commitMapping(entity, cell, 'skip', '')
    return
  }
  // keep the current field if it's valid under the new target; otherwise wait for a pick
  if (fieldListFor(entity, v).some((o) => o.fieldname === cell.field)) {
    delete pendingTarget[k]
    commitMapping(entity, cell, v, cell.field)
  } else {
    pendingTarget[k] = v
  }
}

function changeField(entity, cell, fieldname) {
  commitMapping(entity, cell, cellTarget(entity, cell), fieldname)
}

// preview
const previewBySheet = computed(() => {
  const out = {}
  for (const s of previewResource.data?.sheets || []) out[s.name] = s
  return out
})

function togglePreview(name) {
  openPreviews[name] = !openPreviews[name]
}

function formatCell(c) {
  return c === null || c === undefined ? '' : String(c)
}

// ---------- step 3 ----------
const actionIssues = computed(() =>
  (issues.value.issues || []).filter((i) => i.severity === 'action')
)
const infoIssues = computed(() => (issues.value.issues || []).filter((i) => i.severity === 'info'))

// per-value resolution picker
function mkey(issue, val) {
  return issue.id + '::' + val.value
}

function choiceFor(issue, val) {
  if (manualOn[mkey(issue, val)]) return '__manual__'
  const d = decisions[issue.id]
  return d ? d[val.value] : val.suggestion
}

function onChoice(issue, val, v) {
  const k = mkey(issue, val)
  if (!decisions[issue.id]) decisions[issue.id] = {}
  if (v === '__manual__') {
    manualOn[k] = true
    decisions[issue.id][val.value] = manualText[k] || ''
  } else {
    manualOn[k] = false
    decisions[issue.id][val.value] = v
  }
}

function isManual(issue, val) {
  return !!manualOn[mkey(issue, val)]
}

function onManual(issue, val, text) {
  const k = mkey(issue, val)
  manualText[k] = text
  if (!decisions[issue.id]) decisions[issue.id] = {}
  decisions[issue.id][val.value] = text
}

function clearDecisions() {
  for (const k of Object.keys(decisions)) delete decisions[k]
  for (const k of Object.keys(manualOn)) delete manualOn[k]
  for (const k of Object.keys(manualText)) delete manualText[k]
}

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
const createdRecords = computed(() => liveStatus.value.created || [])

function openApp() {
  window.location.href = liveStatus.value.app_home || '/app'
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
  clearDecisions()
  Object.keys(openPreviews).forEach((k) => delete openPreviews[k])
  Object.keys(openCols).forEach((k) => delete openCols[k])
  Object.keys(pendingTarget).forEach((k) => delete pendingTarget[k])
  liveStatus.value = { status: '', progress: {}, imported: 0, failed: 0, skipped: 0, log: [] }
  errorMessage.value = ''
}

onBeforeUnmount(stopPolling)
</script>
