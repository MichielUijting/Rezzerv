$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$SourcePath = Join-Path $RepoRoot 'frontend\src\features\stores\StoreBatchDetailPage.jsx'
$CheckerPath = Join-Path $RepoRoot 'tools\check_unpacking_readiness_article_model.py'
$TempWorkflowPath = Join-Path $RepoRoot '.github\workflows\_temp-apply-unpacking-readiness-fix.yml'

if (-not (Test-Path $SourcePath)) { throw "Bronbestand ontbreekt: $SourcePath" }
if (-not (Test-Path $CheckerPath)) { throw "Contractchecker ontbreekt: $CheckerPath" }

$branch = (git branch --show-current).Trim()
if ($branch -ne 'fix/unpacking-readiness-article-model') {
    throw "STOP: verkeerde branch '$branch'. Verwacht fix/unpacking-readiness-article-model."
}

if (git status --porcelain) {
    git status --short
    throw 'STOP: werkmap is niet schoon.'
}

$text = [System.IO.File]::ReadAllText($SourcePath, [System.Text.Encoding]::UTF8)
$original = $text

function Replace-ExactOnce([string]$Old, [string]$New, [string]$Label) {
    $count = ([regex]::Matches($script:text, [regex]::Escape($Old))).Count
    if ($count -ne 1) { throw "$Label: verwacht 1 match, gevonden $count" }
    $script:text = $script:text.Replace($Old, $New)
}

Replace-ExactOnce @'
  const effectiveLocationId = String(draft?.locationId || '')

  const hasValidArticle
'@ @'
  const effectiveLocationId = String(draft?.locationId || '')
  const effectiveQuantity = Number(line?.quantity_raw ?? 0)

  const hasValidArticle
'@ 'effective quantity'

Replace-ExactOnce @'
  const hasValidLocation = Boolean(effectiveLocationId) && validLocationIds.has(effectiveLocationId)
  const isProcessable = hasProcessSource
    && hasArticleGroup
    && hasValidLocation
'@ @'
  const hasValidQuantity = Number.isFinite(effectiveQuantity) && effectiveQuantity > 0
  const hasValidLocation = Boolean(effectiveLocationId) && validLocationIds.has(effectiveLocationId)
  const isProcessable = hasProcessSource
    && hasValidQuantity
    && hasValidLocation
'@ 'readiness gate'

Replace-ExactOnce "    effectiveLocationId,`n    hasValidArticle," "    effectiveLocationId,`n    effectiveQuantity,`n    hasValidArticle," 'return effective quantity'
Replace-ExactOnce "    hasProcessSource,`n    hasArticleGroup,`n    hasValidLocation," "    hasProcessSource,`n    hasArticleGroup,`n    hasValidQuantity,`n    hasValidLocation," 'return quantity readiness'

Replace-ExactOnce @'
        const hasGlobalProduct = Boolean(String(line.matched_global_product_id || '').trim())
        const hasRawArticleName = Boolean(String(line.article_name_raw || '').trim())
        const hasArticleGroup = Boolean(String(draft.articleGroupId || '').trim())
        const hasValidLocation = validLocationIds.has(String(draft.locationId || ''))
        return !hasArticle
          && !hasGlobalProduct
          && hasRawArticleName
          && hasArticleGroup
          && hasValidLocation
'@ @'
        const hasRawArticleName = Boolean(String(line.article_name_raw || '').trim())
        const quantity = Number(line.quantity_raw ?? 0)
        const hasValidQuantity = Number.isFinite(quantity) && quantity > 0
        const hasValidLocation = validLocationIds.has(String(draft.locationId || ''))
        return !hasArticle
          && hasRawArticleName
          && hasValidQuantity
          && hasValidLocation
'@ 'hidden household article creation'

$stateOld = "        hasProcessSource,`n        hasArticleGroup,`n        hasValidLocation,"
$stateNew = "        hasProcessSource,`n        hasArticleGroup,`n        hasValidQuantity,`n        hasValidLocation,"
$stateCount = ([regex]::Matches($text, [regex]::Escape($stateOld))).Count
if ($stateCount -ne 2) { throw "line state occurrences: verwacht 2, gevonden $stateCount" }
$text = $text.Replace($stateOld, $stateNew)

Replace-ExactOnce @'
        } else if (!hasValidLocation) {
          statusKey = 'action_needed'
          statusLabel = 'Actie nodig'
          statusReason = 'Locatie ontbreekt.'
        } else if (!hasArticleGroup) {
          statusKey = 'action_needed'
          statusLabel = 'Actie nodig'
          statusReason = 'Artikelgroep ontbreekt.'
        } else {
'@ @'
        } else if (!hasValidQuantity) {
          statusKey = 'action_needed'
          statusLabel = 'Actie nodig'
          statusReason = 'Aantal ontbreekt of is niet geldig.'
        } else if (!hasValidLocation) {
          statusKey = 'action_needed'
          statusLabel = 'Actie nodig'
          statusReason = 'Locatie ontbreekt.'
        } else {
'@ 'status reasons'

Replace-ExactOnce '>Mijn artikel</ResizableHeaderCell>' '>Artikelgroep</ResizableHeaderCell>' 'table heading'

$oldFilter = '<th><select className="rz-input rz-inline-input" value={mappingFilter} onChange={(event) => setMappingFilter(event.target.value)} aria-label="Filter op Mijn artikel">{MAPPING_FILTERS.map((filter) => <option key={filter.key} value={filter.key}>{filter.label}</option>)}</select></th>'
Replace-ExactOnce $oldFilter '<th />' 'obsolete Mijn artikel filter'

$oldSelector = @'
                      <td onClick={(event) => event.stopPropagation()} onDoubleClick={(event) => event.stopPropagation()}>
                        <StoreArticleSelector
                          lineId={line.id}
                          lineName={line.article_name_raw}
                          selectedArticleId={entry.draft.articleId || ''}
                          articleOptions={articleOptions}
                          disabled={busyLineId === line.id || isProcessingBatch}
                          onChange={(nextArticleId) => persistLineDraft(line, { articleId: nextArticleId ?? '' })}
                          onClearArticle={() => persistLineDraft(line, { articleId: '' })}
                          onCreateArticle={(articleName) => handleCreateArticleFromLine(line.id, articleName)}
                          canCreateArticle={Boolean(household?.permissions?.['article.create'])}
                        />
                      </td>
'@
$newSelector = @'
                      <td onClick={(event) => event.stopPropagation()} onDoubleClick={(event) => event.stopPropagation()}>
                        <select
                          className="rz-input rz-inline-input"
                          value={entry.draft.articleGroupId || ''}
                          disabled={busyLineId === line.id || isProcessingBatch || isViewer}
                          aria-label={`Artikelgroep voor ${line.article_name_raw}`}
                          data-testid={`receipt-line-article-group-select-${line.id}`}
                          onChange={(event) => {
                            const nextValue = event.target.value
                            if (nextValue === '__add_article_group__') {
                              openCreateArticleGroup(line.id)
                              return
                            }
                            persistLineDraft(line, { articleGroupId: nextValue })
                          }}
                        >
                          <option value="">Niet ingedeeld</option>
                          {articleGroupOptions.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}
                          {canCreateArticleGroup ? <option value="__add_article_group__">Artikelgroep toevoegen...</option> : null}
                        </select>
                      </td>
'@
Replace-ExactOnce $oldSelector $newSelector 'table Artikelgroep selector'

$detailPattern = '(?s)\r?\n\s*<div className="rz-receipt-line-detail__wide"><dt>Mijn artikel</dt><dd data-testid=\{`receipt-line-article-select-\$\{line\.id\}`\}><StoreArticleSelector.*?</dd></div>'
$detailMatches = [regex]::Matches($text, $detailPattern)
if ($detailMatches.Count -ne 1) { throw "detail Mijn artikel removal: verwacht 1 match, gevonden $($detailMatches.Count)" }
$text = [regex]::Replace($text, $detailPattern, '', 1)

$text = $text.Replace('<option value="">Kies artikelgroep</option>', '<option value="">Niet ingedeeld</option>')
$text = $text.Replace("'Kies eerst Mijn artikel.'", "'Deze cataloguskoppeling is pas beschikbaar nadat het voorraadartikel technisch bestaat.'")
$text = $text.Replace("'Mijn artikel was al aan dit universele artikel gekoppeld.'", "'Het voorraadartikel was al aan dit universele artikel gekoppeld.'")
$text = $text.Replace("'Mijn artikel is aan het universele artikel gekoppeld.'", "'Het voorraadartikel is aan het universele artikel gekoppeld.'")
$text = $text.Replace("'Koppelen aan Mijn artikel'", "'Koppelen'")
$text = $text.Replace('<span>Kies eerst Mijn artikel.</span>', '<span>Het technische voorraadartikel bestaat nog niet.</span>')

Replace-ExactOnce '{processConfirm.readyCount} geselecteerde regel(s) zijn klaar voor verwerking en {processConfirm.incompleteCount} regel(s) missen nog artikel/product, locatie of artikelgroep.' '{processConfirm.readyCount} geselecteerde regel(s) zijn klaar voor verwerking en {processConfirm.incompleteCount} regel(s) missen nog bonartikel, geldig aantal of locatie.' 'process warning'

if ($text -eq $original) { throw 'STOP: er zijn geen bronwijzigingen aangebracht.' }
[System.IO.File]::WriteAllText($SourcePath, $text, [System.Text.UTF8Encoding]::new($false))

python $CheckerPath
if ($LASTEXITCODE -ne 0) { throw 'Contractchecker is rood.' }

if (Test-Path $TempWorkflowPath) {
    Remove-Item $TempWorkflowPath -Force
}

git diff --check
if ($LASTEXITCODE -ne 0) { throw 'git diff --check is rood.' }

Write-Host 'UNPACKING READINESS PATCH GREEN' -ForegroundColor Green
Write-Host 'De broncode is lokaal aangepast en gevalideerd. Commit/push wordt bewust apart uitgevoerd.' -ForegroundColor Green
