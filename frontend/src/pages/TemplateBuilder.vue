<template>
  <div class="mx-auto max-w-5xl px-4 pb-10">
    <PageHeader
      title="Get a spreadsheet to fill in"
      subtitle="Download a ready-made workbook, fill it in, then import it back"
    >
      <template #action>
        <router-link to="/" class="text-sm text-gray-600 hover:text-gray-900 hover:underline"
          >Back to import</router-link
        >
      </template>
    </PageHeader>

    <!-- pick a doctype (always visible — builder reveals below) -->
    <div class="mb-6 rounded-xl border border-gray-200 bg-white p-5">
      <label class="mb-1.5 block text-sm font-medium text-gray-900">What do you want to import?</label>
      <Autocomplete
        :options="doctypeOptions"
        :modelValue="selectedDoctype ? { label: selectedDoctype, value: selectedDoctype } : null"
        placeholder="Search — e.g. Lead, Contact, Organization…"
        @change="(opt) => pickDoctype(opt ? opt.value : '')"
      />
      <div v-if="planResource.loading" class="mt-3 flex items-center gap-2 text-sm text-gray-700">
        <LoadingIndicator class="h-4 w-4" /> Getting things ready…
      </div>
      <p v-else-if="plan" class="mt-2 text-sm text-ink-gray-5">
        <template v-if="depCount"
          >{{ depCount }} related tab{{ depCount > 1 ? 's' : '' }} to fill in first — top to
          bottom.</template
        >
        <template v-else>A single sheet — no related tabs.</template>
      </p>
      <ErrorMessage class="mt-3" :message="errorMessage" />
    </div>

    <!-- Main builder (revealed once a doctype is chosen) -->
    <div v-if="plan" class="flex flex-col gap-6 lg:flex-row">
      <!-- LEFT -->
      <div class="min-w-0 flex-1">
        <!-- why banner (one line) -->
        <div
          v-if="depCount"
          class="mb-4 flex items-center gap-2 rounded-lg bg-blue-50 px-3 py-2 text-xs text-ink-gray-7"
        >
          <FeatherIcon name="info" class="h-3.5 w-3.5 shrink-0 text-blue-500" />
          <span>Linked records must exist first, so this is split into tabs — fill them top to bottom.</span>
        </div>

        <!-- view switch -->
        <div class="mb-4">
          <TabButtons v-model="view" :buttons="views" />
        </div>

        <!-- FILL ORDER view (timeline of tabs to fill, top to bottom) -->
        <div v-if="view === 'steps'" class="relative space-y-3">
          <div
            v-for="(dt, i) in orderedTabs"
            :key="dt"
            class="relative rounded-xl border bg-white"
            :class="dt === selectedDoctype ? 'border-blue-300' : 'border-gray-200'"
          >
            <!-- vertical connector to the next step -->
            <span
              v-if="i < orderedTabs.length - 1"
              class="absolute left-[31px] top-[42px] -bottom-3 w-px bg-gray-200"
            />
            <div class="flex items-start gap-3 px-4 py-3">
              <span
                class="relative z-10 mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-medium"
                :class="dt === selectedDoctype ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600'"
                >{{ i + 1 }}</span
              >
              <FeatherIcon
                :name="dt === selectedDoctype ? 'target' : 'list'"
                class="mt-0.5 h-5 w-5 shrink-0 text-gray-400"
              />
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-center gap-2">
                  <span class="text-sm font-semibold text-gray-900">{{ labelOf(dt) }}</span>
                  <Badge v-if="dt === selectedDoctype" theme="blue" label="Importing this" />
                  <Badge v-else-if="forcedSet.has(dt)" theme="orange" label="Required first" />
                  <Badge v-else theme="gray" label="Added by you" />
                </div>
                <p class="mt-0.5 text-sm text-gray-600">{{ explanation(dt) }}</p>
              </div>
              <div class="flex shrink-0 items-center gap-2">
                <Button
                  v-if="dt !== selectedDoctype && !forcedSet.has(dt)"
                  variant="ghost"
                  size="sm"
                  icon="x"
                  @click="toggleInclude(dt)"
                />
                <Button variant="subtle" size="sm" @click="toggleSection(dt)">
                  <template #prefix><FeatherIcon name="grid" class="h-3.5 w-3.5" /></template>
                  {{ columnCount(dt) }} columns
                  <template #suffix>
                    <FeatherIcon :name="isOpen(dt) ? 'chevron-up' : 'chevron-down'" class="h-3.5 w-3.5" />
                  </template>
                </Button>
              </div>
            </div>
            <div v-if="isOpen(dt)" class="border-t border-gray-100 p-6">
              <ColumnPicker :dt="dt" />
            </div>
          </div>

          <Button v-if="optionalAvailable" variant="ghost" @click="view = 'map'">
            <template #prefix><FeatherIcon name="plus" class="h-4 w-4" /></template>
            Add other related records
          </Button>
        </div>

        <!-- RELATIONSHIPS view (how records connect; add optional ones) -->
        <div v-else class="rounded-xl border border-gray-200 bg-white p-5">
          <p class="mb-4 text-sm text-gray-600">
            How these records connect. Add any optional related records you also want to import —
            required ones are already included.
          </p>

          <!-- root: the record being imported (Espresso Badge, same as Fill order) -->
          <div class="flex items-center gap-2 text-sm font-semibold text-gray-900">
            <FeatherIcon name="target" class="h-4 w-4 text-blue-600" /> {{ rootLabel }}
            <Badge theme="blue" label="Importing this" />
          </div>

          <!-- linked records, drawn as a connected tree -->
          <div class="mt-1">
            <div
              v-for="node in treeRows"
              :key="node.doctype"
              class="relative flex items-center gap-2 py-1.5 text-sm"
              :style="{ paddingLeft: (node.depth + 1) * 22 + 'px' }"
            >
              <!-- connector guides: a rail per depth level + an elbow into the node -->
              <span
                v-for="d in node.depth + 1"
                :key="d"
                class="absolute top-0 bottom-0 w-px bg-gray-200"
                :style="{ left: d * 22 - 11 + 'px' }"
              />
              <FeatherIcon
                name="corner-down-right"
                class="-ml-1 h-3.5 w-3.5 shrink-0 text-gray-300"
                :style="{ marginLeft: '-' + (node.depth * 22 + 4) + 'px' }"
              />
              <button
                v-if="node.hasChildren"
                class="text-gray-400 hover:text-gray-700"
                @click="toggleTreeExpand(node.doctype)"
              >
                <FeatherIcon
                  :name="treeExpanded[node.doctype] ? 'chevron-down' : 'chevron-right'"
                  class="h-3.5 w-3.5"
                />
              </button>
              <span class="text-xs text-gray-400">{{ node.via_label }}</span>
              <span
                :class="includedSet.has(node.doctype) ? 'font-medium text-gray-900' : 'text-gray-600'"
              >
                {{ labelOf(node.doctype) }}
              </span>
              <Badge v-if="forcedSet.has(node.doctype)" theme="orange" label="required" />
              <Button
                v-else
                size="sm"
                :variant="includedSet.has(node.doctype) ? 'subtle' : 'outline'"
                :theme="includedSet.has(node.doctype) ? 'green' : 'gray'"
                :label="includedSet.has(node.doctype) ? 'Included' : 'Add'"
                @click="toggleInclude(node.doctype)"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- RIGHT: workbook summary -->
      <div class="w-full shrink-0 lg:w-80">
        <div class="sticky top-24 rounded-xl border border-gray-200 bg-white p-5">
          <div class="mb-1 flex items-center gap-2 text-sm font-semibold text-gray-900">
            <FeatherIcon name="file-text" class="h-4 w-4 text-gray-400" /> Your workbook
          </div>
          <p class="mb-3 font-mono text-xs text-gray-500">{{ rootLabel }} import.xlsx</p>

          <div class="space-y-1">
            <div
              v-for="(dt, i) in orderedTabs"
              :key="dt"
              class="rounded-md px-2 py-1.5"
              :class="dt === selectedDoctype ? 'bg-blue-50' : ''"
            >
              <div class="flex items-center gap-2 text-sm">
                <span class="text-xs text-gray-400">{{ i + 1 }}</span>
                <FeatherIcon
                  :name="dt === selectedDoctype ? 'target' : 'list'"
                  class="h-3.5 w-3.5 shrink-0 text-gray-400"
                />
                <span class="flex-1 truncate text-gray-800">
                  {{ labelOf(dt) }}
                  <span v-if="dt === selectedDoctype" class="text-xs font-normal text-blue-600"
                    >· main record</span
                  >
                </span>
                <span class="text-xs text-gray-500">{{ columnCount(dt) }}</span>
              </div>
              <p v-if="relationOf(dt)" class="ml-[26px] mt-0.5 text-xs text-gray-400">
                ↳ {{ relationOf(dt) }}
              </p>
            </div>
          </div>

          <div class="mt-3 border-t border-gray-100 pt-3 text-xs text-gray-500">
            {{ orderedTabs.length }} tab{{ orderedTabs.length > 1 ? 's' : '' }} ·
            {{ requiredCount }} required<br />
            {{ totalColumns }} columns total
          </div>

          <!-- fill mode -->
          <div class="mt-4">
            <label class="mb-1 block text-xs font-medium text-gray-700">Fill each tab with</label>
            <FormControl type="select" :options="modeOptions" v-model="mode" />
            <div v-if="mode === 'filtered'" class="mt-2 space-y-2">
              <div
                v-for="(f, i) in filterRows"
                :key="i"
                class="space-y-1.5 rounded-lg border border-gray-200 p-2"
              >
                <div class="flex items-center gap-1">
                  <div class="flex-1">
                    <FormControl
                      type="select"
                      :options="rootFilterOptions"
                      :modelValue="f.field"
                      @update:modelValue="(v) => onFilterField(f, v)"
                    />
                  </div>
                  <Button variant="ghost" size="sm" icon="x" @click="filterRows.splice(i, 1)" />
                </div>
                <FormControl
                  v-if="f.field"
                  type="select"
                  :options="operatorOptions(f.field)"
                  v-model="f.operator"
                />
                <template v-if="f.field && needsValue(f.operator)">
                  <FormControl
                    v-if="fieldMeta(f.field).fieldtype === 'Select'"
                    type="select"
                    :options="selectValueOptions(f.field)"
                    v-model="f.value"
                  />
                  <FormControl
                    v-else-if="fieldMeta(f.field).fieldtype === 'Check'"
                    type="select"
                    :options="[{ label: 'Yes', value: 1 }, { label: 'No', value: 0 }]"
                    v-model="f.value"
                  />
                  <FormControl
                    v-else-if="['Date', 'Datetime'].includes(fieldMeta(f.field).fieldtype)"
                    type="date"
                    v-model="f.value"
                  />
                  <FormControl
                    v-else-if="['Int', 'Float', 'Currency', 'Percent'].includes(fieldMeta(f.field).fieldtype)"
                    type="number"
                    v-model="f.value"
                  />
                  <Autocomplete
                    v-else-if="fieldMeta(f.field).link_doctype"
                    :options="linkOptions[f.field] || []"
                    :modelValue="f.value ? { label: f.value, value: f.value } : null"
                    placeholder="Search…"
                    @change="(opt) => (f.value = opt ? opt.value : '')"
                    @update:query="(q) => fetchLinkOptions(f.field, q)"
                  />
                  <FormControl v-else type="text" placeholder="value" v-model="f.value" />
                </template>
              </div>
              <Button
                variant="ghost"
                size="sm"
                @click="filterRows.push({ field: '', operator: '', value: '' })"
              >
                <template #prefix><FeatherIcon name="plus" class="h-3 w-3" /></template>
                Add condition
              </Button>
            </div>
          </div>

          <Button
            class="mt-4 w-full"
            variant="solid"
            :loading="downloading"
            label="Download workbook"
            @click="download"
          >
            <template #prefix><FeatherIcon name="download" class="h-4 w-4" /></template>
          </Button>
          <p class="mt-2 text-xs text-gray-500">
            Fill it in, then come back to upload — we'll import every tab in the right order.
          </p>
          <ErrorMessage class="mt-2" :message="errorMessage" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, h, reactive, ref } from 'vue'
import {
  Autocomplete,
  Badge,
  Button,
  Checkbox,
  ErrorMessage,
  FeatherIcon,
  FormControl,
  LoadingIndicator,
  TabButtons,
  createResource,
} from 'frappe-ui'
import PageHeader from '../components/PageHeader.vue'

const errorMessage = ref('')

const selectedDoctype = ref('')
const mode = ref('examples')
const view = ref('steps')
const userChecked = reactive({})
const fieldsByDoctype = reactive({})
const chosenFields = reactive({})
const chosenChildFields = reactive({}) // {table_fieldname: {fieldname: bool}} line items on the root sheet
const openSections = reactive({})
const treeExpanded = reactive({})
const filterRows = ref([{ field: '', operator: '', value: '' }])

const TEXT_OPS = [
  { label: 'equals', value: 'equals' },
  { label: 'not equals', value: 'not equals' },
  { label: 'contains', value: 'contains' },
  { label: 'is set', value: 'is set' },
  { label: 'is not set', value: 'is not set' },
]
const NUM_OPS = [
  { label: '=', value: 'equals' },
  { label: '≠', value: 'not equals' },
  { label: '>', value: '>' },
  { label: '≥', value: '>=' },
  { label: '<', value: '<' },
  { label: '≤', value: '<=' },
]
function fieldMeta(fieldname) {
  return (((plan.value && plan.value.fields) || []).find((f) => f.fieldname === fieldname)) || {}
}
function operatorOptions(fieldname) {
  const ft = fieldMeta(fieldname).fieldtype
  if (['Int', 'Float', 'Currency', 'Percent', 'Date', 'Datetime'].includes(ft)) return NUM_OPS
  if (ft === 'Select')
    return [
      { label: 'equals', value: 'equals' },
      { label: 'not equals', value: 'not equals' },
      { label: 'is set', value: 'is set' },
      { label: 'is not set', value: 'is not set' },
    ]
  if (ft === 'Check') return [{ label: 'equals', value: 'equals' }]
  return TEXT_OPS
}
function needsValue(op) {
  return op && op !== 'is set' && op !== 'is not set'
}
function selectValueOptions(fieldname) {
  return [
    { label: 'Choose…', value: '' },
    ...((fieldMeta(fieldname).select_options || []).map((o) => ({ label: o, value: o }))),
  ]
}
const linkOptions = reactive({})
const linkOptionsResource = createResource({ url: 'smart_import.api.link_options' })
async function fetchLinkOptions(fieldname, q) {
  const target = fieldMeta(fieldname).link_doctype
  if (!target) return
  linkOptions[fieldname] = await linkOptionsResource.submit({ doctype: target, txt: q || '' })
}
function onFilterField(f, v) {
  f.field = v
  f.operator = (operatorOptions(v)[0] || {}).value || 'equals'
  f.value = ''
  if (fieldMeta(v).link_doctype) fetchLinkOptions(v, '')
}
const downloading = ref(false)

const views = [
  { value: 'steps', label: 'Fill order', icon: 'list' },
  { value: 'map', label: 'Relationships', icon: 'share-2' },
]

const modeOptions = [
  { label: 'A few example rows', value: 'examples' },
  { label: 'Empty (headings only)', value: 'blank' },
  { label: 'All existing records', value: 'records' },
  { label: 'Only certain records', value: 'filtered' },
]

const doctypesResource = createResource({ url: 'smart_import.api.importable_doctypes', auto: true })
const doctypeOptions = computed(() => doctypesResource.data || [])

const planResource = createResource({
  url: 'smart_import.api.template_plan',
  onSuccess(data) {
    for (const k of Object.keys(userChecked)) delete userChecked[k]
    for (const k of Object.keys(fieldsByDoctype)) delete fieldsByDoctype[k]
    for (const k of Object.keys(chosenFields)) delete chosenFields[k]
    for (const k of Object.keys(chosenChildFields)) delete chosenChildFields[k]
    for (const k of Object.keys(openSections)) delete openSections[k]
    for (const k of Object.keys(treeExpanded)) delete treeExpanded[k]
    filterRows.value = [{ field: '', operator: '', value: '' }]
    view.value = 'steps'
    setFields(data.doctype, data.fields)
    for (const ct of data.child_tables || []) chosenChildFields[ct.table_fieldname] = {}
  },
  onError: showError,
})
const plan = computed(() => planResource.data)
const rootLabel = computed(() => labelOf(selectedDoctype.value))

const fieldsResource = createResource({ url: 'smart_import.api.doctype_fields' })
async function ensureFields(dt) {
  if (fieldsByDoctype[dt]) return
  const data = await fieldsResource.submit({ doctype: dt })
  // doctype_fields returns { parent, children }; the picker uses the parent list
  setFields(dt, Array.isArray(data) ? data : data.parent || [])
}
function setFields(dt, fields) {
  fieldsByDoctype[dt] = fields
  const sel = {}
  for (const f of fields) sel[f.fieldname] = !!f.suggested
  chosenFields[dt] = sel
}

// ---- relationships ----
const allLinks = computed(() => (plan.value && plan.value.links) || [])
function childrenOf(dt) {
  return allLinks.value.filter((l) => l.from_doctype === dt)
}
function linkEdge(dt) {
  return allLinks.value.find((l) => l.doctype === dt)
}
function labelOf(dt) {
  return dt || ''
}

// short description of how a prerequisite tab connects to the record it feeds
function relationOf(dt) {
  if (dt === selectedDoctype.value) return ''
  const edge = linkEdge(dt)
  if (!edge) return ''
  const main = edge.from_doctype || selectedDoctype.value
  return edge.via_table
    ? `line items inside ${main}`
    : `linked from ${main} · ${edge.via_label}`
}

const resolution = computed(() => {
  const root = selectedDoctype.value
  const links = allLinks.value
  const included = new Set(root ? [root] : [])
  const forced = new Set()
  let changed = true
  while (changed) {
    changed = false
    // mandatory chain (required-first) + tabs the user opted into
    for (const l of links) {
      if (included.has(l.doctype)) continue
      const forcedHere = l.mandatory && included.has(l.from_doctype)
      if (forcedHere || userChecked[l.doctype]) {
        included.add(l.doctype)
        if (forcedHere) forced.add(l.doctype)
        changed = true
      }
    }
    // a tab opted in via a link column may not be a discovered edge — include it
    for (const dt of Object.keys(userChecked)) {
      if (userChecked[dt] === true && !included.has(dt)) {
        included.add(dt)
        changed = true
      }
    }
  }
  return { included, forced }
})
const includedSet = computed(() => resolution.value.included)
const forcedSet = computed(() => resolution.value.forced)

// dependency order: a doctype's link targets come before it; root ends last
const orderedTabs = computed(() => {
  const root = selectedDoctype.value
  if (!root) return []
  const inc = includedSet.value
  const placed = []
  const done = new Set()
  const visiting = new Set()
  const visit = (dt) => {
    if (done.has(dt) || visiting.has(dt)) return
    visiting.add(dt)
    for (const l of childrenOf(dt)) {
      if (inc.has(l.doctype)) visit(l.doctype)
    }
    visiting.delete(dt)
    done.add(dt)
    placed.push(dt)
  }
  for (const dt of inc) visit(dt)
  // ensure root is last
  return placed.filter((d) => d !== root).concat(root)
})

const depCount = computed(() => orderedTabs.value.length - 1)
const requiredCount = computed(() => orderedTabs.value.filter((d) => forcedSet.value.has(d)).length)
const optionalAvailable = computed(() =>
  allLinks.value.some((l) => !l.system && !includedSet.value.has(l.doctype))
)

// connection-map tree (all discovered links, expandable)
const treeRows = computed(() => {
  const root = selectedDoctype.value
  if (!root) return []
  const out = []
  const walk = (dt, depth) => {
    for (const l of childrenOf(dt)) {
      const hasChildren = childrenOf(l.doctype).length > 0
      out.push({ doctype: l.doctype, via_label: l.via_label, depth, hasChildren })
      if (hasChildren && treeExpanded[l.doctype]) walk(l.doctype, depth + 1)
    }
  }
  walk(root, 0)
  return out
})

function explanation(dt) {
  if (dt === selectedDoctype.value) {
    return 'The records you came to import. Everything above is set up first so these match up cleanly.'
  }
  const edge = linkEdge(dt)
  if (!edge) return 'A related list included in your workbook.'
  return `Each ${edge.from_doctype} links to a ${edge.via_label}, so your ${dt} records have to exist before the import can match them up.`
}

// ---- columns ----
function linkColumns(dt) {
  const l = linkEdge(dt)
  return l && l.columns ? l.columns : 0
}
function columnCount(dt) {
  let base
  if (fieldsByDoctype[dt]) {
    base = (fieldsByDoctype[dt] || []).filter((f) => isChosen(dt, f)).length
  } else if (dt === selectedDoctype.value && plan.value) {
    base = plan.value.fields.filter((f) => f.suggested).length
  } else {
    base = linkColumns(dt)
  }
  if (dt === selectedDoctype.value) base += childSelectedCount()
  return base
}

// ---- line-item (child table) columns on the root sheet ----
const rootChildTables = computed(() => (plan.value && plan.value.child_tables) || [])
function isChildChosen(tf, fieldname) {
  return !!(chosenChildFields[tf] && chosenChildFields[tf][fieldname])
}
function setChildField(tf, fieldname, checked) {
  if (!chosenChildFields[tf]) chosenChildFields[tf] = {}
  chosenChildFields[tf][fieldname] = checked
}
function setAllChild(tf, fields, all) {
  if (!chosenChildFields[tf]) chosenChildFields[tf] = {}
  for (const f of fields || []) chosenChildFields[tf][f.fieldname] = all
}
function childSelectedCount() {
  let n = 0
  for (const tf in chosenChildFields) {
    for (const f in chosenChildFields[tf]) if (chosenChildFields[tf][f]) n++
  }
  return n
}

// a small feather glyph + plain word for a field's type, shown in the picker
function typeIcon(ft) {
  if (['Int', 'Float', 'Currency', 'Percent'].includes(ft)) return 'hash'
  if (['Date', 'Datetime', 'Time'].includes(ft)) return 'calendar'
  if (ft === 'Select') return 'chevron-down'
  if (ft === 'Check') return 'check-square'
  if (['Link', 'Dynamic Link'].includes(ft)) return 'link'
  return 'type'
}
function typeLabel(ft) {
  if (['Int', 'Float', 'Currency', 'Percent'].includes(ft)) return 'number'
  if (['Date', 'Datetime', 'Time'].includes(ft)) return 'date'
  if (ft === 'Select') return 'choice'
  if (ft === 'Check') return 'yes/no'
  if (['Link', 'Dynamic Link'].includes(ft)) return 'link'
  return 'text'
}
const totalColumns = computed(() =>
  orderedTabs.value.reduce((sum, dt) => sum + columnCount(dt), 0)
)

function isOpen(dt) {
  return !!openSections[dt]
}
function toggleSection(dt) {
  const next = !openSections[dt]
  openSections[dt] = next
  if (next) ensureFields(dt)
}
function isChosen(dt, f) {
  const m = chosenFields[dt] || {}
  return f.reqd || !!m[f.fieldname]
}
function setField(dt, fieldname, checked) {
  if (!chosenFields[dt]) chosenFields[dt] = {}
  chosenFields[dt][fieldname] = checked
}
function setAll(dt, all) {
  const fields = fieldsByDoctype[dt] || []
  const m = chosenFields[dt] || (chosenFields[dt] = {})
  for (const f of fields) m[f.fieldname] = all || !!f.reqd
}

function toggleInclude(dt) {
  if (forcedSet.value.has(dt)) return
  userChecked[dt] = !includedSet.value.has(dt)
}
function toggleTreeExpand(dt) {
  treeExpanded[dt] = !treeExpanded[dt]
}

// reusable column-picker (functional component using the helpers above)
const ColumnPicker = (props) => {
  const dt = props.dt
  if (!fieldsByDoctype[dt]) {
    return h('div', { class: 'flex items-center gap-2 text-sm text-gray-600' }, [
      h(LoadingIndicator, { class: 'h-4 w-4' }),
      ' Loading…',
    ])
  }
  // subtle, hover-revealed control to add a tab for a linked column
  const tabControl = (f) => {
    const target = f.link_doctype
    if (!target || target === selectedDoctype.value) return null
    const included = includedSet.value.has(target)
    const forced = forcedSet.value.has(target)
    if (included) {
      return h(
        'span',
        {
          class:
            'shrink-0 text-xs ' +
            (forced ? 'text-ink-gray-4' : 'cursor-pointer text-ink-green-3 hover:underline'),
          title: forced ? 'Always included as a tab' : 'Remove this tab',
          onClick: forced
            ? undefined
            : (e) => {
                e.preventDefault()
                e.stopPropagation()
                toggleInclude(target)
              },
        },
        '✓ tab'
      )
    }
    return h(
      'button',
      {
        class:
          'shrink-0 text-xs text-ink-gray-5 opacity-0 transition hover:text-ink-gray-8 hover:underline group-hover:opacity-100',
        title: `Add a tab to create new ${target} records`,
        onClick: (e) => {
          e.preventDefault()
          e.stopPropagation()
          toggleInclude(target)
        },
      },
      '+ tab'
    )
  }
  const rows = (fieldsByDoctype[dt] || []).map((f) =>
    h('div', { key: f.fieldname, class: 'group flex min-w-0 items-center justify-between gap-2 py-1 text-sm' }, [
      h('label', { class: 'flex min-w-0 items-center gap-2.5' }, [
        h(Checkbox, {
          modelValue: isChosen(dt, f),
          disabled: f.reqd,
          'onUpdate:modelValue': (v) => setField(dt, f.fieldname, v),
        }),
        h(FeatherIcon, {
          name: typeIcon(f.fieldtype),
          class: 'h-3.5 w-3.5 shrink-0 text-ink-gray-4',
          title: typeLabel(f.fieldtype),
        }),
        h('span', { class: 'min-w-0 truncate text-ink-gray-7' }, [
          f.label,
          f.reqd ? h('span', { class: 'text-ink-amber-3' }, ' *') : null,
          f.link_doctype ? h('span', { class: 'text-ink-gray-4' }, ` · ${f.link_doctype}`) : null,
        ]),
      ]),
      tabControl(f),
    ])
  )
  // line-item (child table) sections — root sheet only
  const childSections =
    dt === selectedDoctype.value
      ? rootChildTables.value.map((ct) =>
          h('div', { key: ct.table_fieldname, class: 'mt-5 border-t border-gray-100 pt-4' }, [
            h('div', { class: 'mb-1 flex items-center justify-between gap-3' }, [
              h('div', { class: 'flex min-w-0 items-center gap-2' }, [
                h(FeatherIcon, { name: 'list', class: 'h-3.5 w-3.5 shrink-0 text-blue-500' }),
                h('span', { class: 'truncate text-sm font-medium text-ink-gray-8' }, `Line items · ${ct.label}`),
                h(
                  'span',
                  { class: 'shrink-0 rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-medium text-blue-600' },
                  'child table'
                ),
              ]),
              h('div', { class: 'flex shrink-0 gap-1' }, [
                h(Button, {
                  variant: 'ghost',
                  size: 'sm',
                  label: 'Select all',
                  onClick: () => setAllChild(ct.table_fieldname, ct.fields, true),
                }),
                h(Button, {
                  variant: 'ghost',
                  size: 'sm',
                  label: 'Clear',
                  onClick: () => setAllChild(ct.table_fieldname, ct.fields, false),
                }),
              ]),
            ]),
            h(
              'p',
              { class: 'mb-2 text-xs text-ink-gray-5' },
              `Each row adds one ${ct.label} line; repeat the main columns per line. Required (*) fields are added automatically.`
            ),
            h(
              'div',
              { class: 'grid grid-cols-2 gap-x-10 gap-y-1.5' },
              (ct.fields || []).map((f) =>
                h(
                  'div',
                  {
                    key: f.fieldname,
                    class:
                      'group flex min-w-0 items-center justify-between gap-2 py-1 text-sm',
                  },
                  [
                    h('label', { class: 'flex min-w-0 items-center gap-2.5' }, [
                      h(Checkbox, {
                        modelValue: isChildChosen(ct.table_fieldname, f.fieldname),
                        'onUpdate:modelValue': (v) =>
                          setChildField(ct.table_fieldname, f.fieldname, v),
                      }),
                      h(FeatherIcon, {
                        name: typeIcon(f.fieldtype),
                        class: 'h-3.5 w-3.5 shrink-0 text-ink-gray-4',
                        title: typeLabel(f.fieldtype),
                      }),
                      h('span', { class: 'min-w-0 truncate text-ink-gray-7' }, [
                        f.label,
                        f.reqd ? h('span', { class: 'text-ink-amber-3' }, ' *') : null,
                        f.link_doctype
                          ? h('span', { class: 'text-ink-gray-4' }, ` · ${f.link_doctype}`)
                          : null,
                      ]),
                    ]),
                    tabControl(f),
                  ]
                )
              )
            ),
          ])
        )
      : []

  return h('div', [
    // header: actions on their own line, separated from the descriptive note
    h('div', { class: 'mb-1 flex items-center justify-between gap-3' }, [
      h('span', { class: 'text-sm font-medium text-ink-gray-8' }, 'Columns'),
      h('div', { class: 'flex shrink-0 gap-1' }, [
        h(Button, { variant: 'ghost', size: 'sm', label: 'Select all', onClick: () => setAll(dt, true) }),
        h(Button, { variant: 'ghost', size: 'sm', label: 'Clear', onClick: () => setAll(dt, false) }),
      ]),
    ]),
    h(
      'p',
      { class: 'mb-4 text-xs text-ink-gray-5' },
      'Required (*) columns are always included. Hover a linked column and click “+ tab” to also create new records of that type.'
    ),
    h('div', { class: 'grid max-h-96 grid-cols-2 gap-x-10 gap-y-1.5 overflow-auto pr-1' }, rows),
    ...childSections,
  ])
}

const rootFilterOptions = computed(() => [
  { label: 'Choose a field…', value: '' },
  ...(((plan.value && plan.value.fields) || []).map((f) => ({ label: f.label, value: f.fieldname }))),
])

function pickDoctype(dt) {
  selectedDoctype.value = dt
  errorMessage.value = ''
  if (dt) planResource.submit({ doctype: dt })
}
function changeDoctype() {
  selectedDoctype.value = ''
  planResource.reset()
  errorMessage.value = ''
}

const downloadResource = createResource({
  url: 'smart_import.api.download_template',
  onSuccess(data) {
    triggerDownload(data.filename, data.content_b64)
    downloading.value = false
  },
  onError(err) {
    downloading.value = false
    showError(err)
  },
})

function download() {
  errorMessage.value = ''
  downloading.value = true
  const fieldsMap = {}
  for (const dt of orderedTabs.value) {
    if (chosenFields[dt]) {
      fieldsMap[dt] = Object.keys(chosenFields[dt]).filter((k) => chosenFields[dt][k])
    }
  }
  const include = orderedTabs.value.filter((dt) => dt !== selectedDoctype.value)
  const childMap = {}
  for (const tf in chosenChildFields) {
    const chosen = Object.keys(chosenChildFields[tf]).filter((k) => chosenChildFields[tf][k])
    if (chosen.length) childMap[tf] = chosen
  }
  const filters = []
  if (mode.value === 'filtered') {
    for (const f of filterRows.value) {
      if (!f.field || !f.operator) continue
      const noValue = f.operator === 'is set' || f.operator === 'is not set'
      if (!noValue && (f.value === '' || f.value == null)) continue
      filters.push({ field: f.field, operator: f.operator, value: noValue ? null : f.value })
    }
  }
  downloadResource.submit({
    doctype: selectedDoctype.value,
    fields_map: JSON.stringify(fieldsMap),
    include: JSON.stringify(include),
    mode: mode.value,
    filters: JSON.stringify(filters),
    child_map: JSON.stringify(childMap),
  })
}

function triggerDownload(filename, b64) {
  const bin = atob(b64)
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
  const blob = new Blob([bytes], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

function showError(error) {
  errorMessage.value =
    (error && error.messages && error.messages.join(', ')) ||
    (error && error.message) ||
    'Could not build the template.'
}
</script>
