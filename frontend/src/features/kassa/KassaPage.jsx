import { useLayoutEffect } from 'react'
import ReceiptsKassaPage from '../receipts/KassaPage.jsx'
import KassaParseQualityDiagnostics, { installKassaReceiptDiagnosticsFetchProbe } from './KassaParseQualityDiagnostics.jsx'

export default function KassaPage() {
  useLayoutEffect(() => installKassaReceiptDiagnosticsFetchProbe(), [])

  return (
    <>
      <ReceiptsKassaPage />
      <KassaParseQualityDiagnostics />
    </>
  )
}
