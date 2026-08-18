import { readFileSync } from 'node:fs'

const shopping = readFileSync(new URL('../src/features/shopping/ShoppingPage.jsx', import.meta.url), 'utf8')
const dataTable = readFileSync(new URL('../src/ui/DataTable.jsx', import.meta.url), 'utf8')
const table = readFileSync(new URL('../src/ui/Table.jsx', import.meta.url), 'utf8')
const resizable = readFileSync(new URL('../src/ui/resizableTable.jsx', import.meta.url), 'utf8')
const tableCss = readFileSync(new URL('../src/ui/components/table.css', import.meta.url), 'utf8')

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
includes(shopping, 'Selecteer alle zichtbare rijen', 'Bulkselectie voor Winkelen ontbreekt')
includes(shopping, "testId: 'shopping-delete-confirmation'", 'Standaard verwijderbevestiging ontbreekt')
includes(shopping, "testId: 'shopping-complete-confirmation'", 'Standaard afrondbevestiging ontbreekt')
excludes(shopping, 'window.confirm', 'Native browser-confirm is niet toegestaan')
excludes(shopping, '<Table ', 'Winkelen bouwt nog een eigen low-level tabel')
excludes(shopping, '<tr className="rz-input">', 'Winkelen gebruikt nog een niet-standaard titelrij')
excludes(shopping, 'FILTER_CONTROL_STYLE', 'Winkelen definieert nog een lokale filterstyle')
excludes(shopping, 'minHeight: 38', 'Winkelen forceert nog een niet-standaard filterhoogte')
excludes(shopping, 'style={FILTER_CONTROL_STYLE}', 'Winkelen past nog een lokale filterstyle toe')

includes(dataTable, 'className="rz-table-header"', 'DataTable standaard titelrij ontbreekt')
includes(dataTable, "column.key === 'select'", 'DataTable herkent de standaard selectie-kolom niet')
includes(dataTable, "placement: 'header'", 'Bulkselectie wordt niet in de titelrij geprojecteerd')
includes(dataTable, 'isSelectionHeaderColumn(column) ? null', 'Bulkselectie staat nog in de filterrij')
includes(dataTable, "typeof column.renderFilter === 'function'", 'DataTable ondersteunt geen standaard custom filtercontrol')
includes(dataTable, "typeof column.filterPredicate === 'function'", 'DataTable ondersteunt geen exacte filtersemantiek')
includes(dataTable, 'resizableColumns', 'DataTable activeert het standaard resizecontract niet')
includes(dataTable, 'onColumnResize={handleColumnResize}', 'DataTable synchroniseert zichtbare resize niet terug naar React-state')
includes(table, 'const nearLeftEdge', 'Tabelgrens is niet aan de linkerzijde van de volgende kolom pakbaar')
includes(table, 'const nearRightEdge', 'Tabelgrens is niet aan de rechterzijde van de huidige kolom pakbaar')
includes(table, 'onColumnResize?.(activeResize.columnIndex, nextWidth)', 'Tabelresizer rapporteert de werkelijke breedte niet terug')
includes(resizable, 'setColumnWidth', 'React-kolombreedte kan niet vanuit het standaard resizecontract worden bijgewerkt')
includes(resizable, 'role="separator"', 'DataTable kolomresize-indicator ontbreekt')
includes(resizable, "pointerEvents: 'none'", 'Losse resize-indicator onderschept nog muisevents in plaats van het standaard Table-contract')
includes(resizable, 'aria-sort=', 'Standaard sorteerheader exposeert aria-sort niet')
includes(tableCss, '.rz-table--resizable-columns', 'Standaard resize-CSS ontbreekt')

console.log('WINKELEN_STANDARD_UI_CONTRACT_GREEN')
