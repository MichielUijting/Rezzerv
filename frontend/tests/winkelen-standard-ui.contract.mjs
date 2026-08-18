import { readFileSync } from 'node:fs'

const shopping = readFileSync(new URL('../src/features/shopping/ShoppingPage.jsx', import.meta.url), 'utf8')
const dataTable = readFileSync(new URL('../src/ui/DataTable.jsx', import.meta.url), 'utf8')
const resizable = readFileSync(new URL('../src/ui/resizableTable.jsx', import.meta.url), 'utf8')

function includes(source, needle, label) {
  if (!source.includes(needle)) throw new Error(`${label}: ontbreekt: ${needle}`)
}

function excludes(source, needle, label) {
  if (source.includes(needle)) throw new Error(`${label}: verboden aanwezig: ${needle}`)
}

includes(shopping, "import DataTable from '../../ui/DataTable.jsx'", 'Winkelen gebruikt niet de standaard DataTable')
includes(shopping, "import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'", 'Winkelen gebruikt niet de standaard app-feedback')
includes(shopping, '<DataTable', 'Winkelen rendert geen DataTable')
includes(shopping, 'Artikel toevoegen', 'Label Artikel toevoegen ontbreekt')
includes(shopping, "testId: 'shopping-delete-confirmation'", 'Standaard verwijderbevestiging ontbreekt')
includes(shopping, "testId: 'shopping-complete-confirmation'", 'Standaard afrondbevestiging ontbreekt')
excludes(shopping, 'window.confirm', 'Native browser-confirm is niet toegestaan')
excludes(shopping, '<Table ', 'Winkelen bouwt nog een eigen low-level tabel')
excludes(shopping, '<tr className="rz-input">', 'Winkelen gebruikt nog een niet-standaard titelrij')
excludes(shopping, 'FILTER_CONTROL_STYLE', 'Winkelen definieert nog een lokale filterstyle')
excludes(shopping, 'minHeight: 38', 'Winkelen forceert nog een niet-standaard filterhoogte')
excludes(shopping, 'style={FILTER_CONTROL_STYLE}', 'Winkelen past nog een lokale filterstyle toe')

includes(dataTable, 'className="rz-table-header"', 'DataTable standaard titelrij ontbreekt')
includes(dataTable, "typeof column.renderFilter === 'function'", 'DataTable ondersteunt geen standaard custom filtercontrol')
includes(dataTable, "typeof column.filterPredicate === 'function'", 'DataTable ondersteunt geen exacte filtersemantiek')
includes(resizable, 'role="separator"', 'DataTable kolomresize-handle ontbreekt')
includes(resizable, 'aria-sort=', 'Standaard sorteerheader exposeert aria-sort niet')

console.log('WINKELEN_STANDARD_UI_CONTRACT_GREEN')
