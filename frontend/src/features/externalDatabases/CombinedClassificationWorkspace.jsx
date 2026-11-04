import { useState } from 'react'
import CatalogGpcActionPage from '../catalog/CatalogGpcActionPage'
import CbsClassificationPage from '../catalog/CbsClassificationPage'
import { canCurrentUserPerform, readStoredAuthContext } from '../../lib/authSession'

export default function CombinedClassificationWorkspace() {
  const [article, setArticle] = useState(null)
  const mayUpdateGpc = canCurrentUserPerform('gpc.update', readStoredAuthContext())

  return <section aria-label="GS1 en CBS classificeren" data-testid="combined-classification-workspace">
    <p>Selecteer één centraal Catalogusartikel. Bekijk daarna de GS1 GPC- en CBS ECOICOPv2-indeling
      voor datzelfde artikel, en bevestig iedere indeling afzonderlijk via de bestaande officiële route.</p>
    {!mayUpdateGpc ? <p role="status">Je kunt de GS1-indeling hier bekijken, maar je account heeft geen bevoegdheid om GS1 te wijzigen.</p> : null}
    <CatalogGpcActionPage embedded readOnly={!mayUpdateGpc} onArticleChange={setArticle} />
    {article ? <CbsClassificationPage key={article.id} embedded productId={article.id} /> : null}
  </section>
}
