import fs from 'node:fs'
import assert from 'node:assert/strict'

const articlePage = fs.readFileSync('frontend/src/features/articles/ArticlePage.jsx', 'utf8')
const receiptFeedbackTest = fs.readFileSync('frontend/tests/e2e/uitpakken-feedback.frontend-regression.spec.js', 'utf8')
const articleFeedbackTest = fs.readFileSync('frontend/tests/e2e/article-detail.frontend-regression.spec.js', 'utf8')

function pass(name) {
  console.log(`PASS ${name}`)
}

assert.match(
  articlePage,
  /useAppFeedback\(\)/,
  'ArticlePage moet de centrale AppFeedbackProvider gebruiken voor API-foutfeedback',
)
pass('article_page_uses_app_feedback_provider')

assert.doesNotMatch(
  articlePage,
  /rz-article-detail-alert/,
  'API-loadfouten op ArticlePage mogen niet als losse inline rz-article-detail-alert worden gerenderd',
)
pass('article_api_errors_have_no_inline_alert')

assert.match(
  articlePage,
  /article-inventory-load-error/,
  'De inventory-preview fout moet via een expliciete standaard feedback-key worden aangeboden',
)
assert.match(
  articlePage,
  /Live artikelvoorraad kon niet worden geladen[\s\S]{0,1200}showFeedback\(\{[\s\S]{0,500}variant:\s*'error'/,
  'Een inventory-preview API-fout moet via showFeedback als error worden getoond',
)
pass('inventory_preview_failure_uses_standard_feedback')

assert.match(receiptFeedbackTest, /app-feedback-error/)
assert.match(receiptFeedbackTest, /Interne serverfout in de API/)
assert.match(receiptFeedbackTest, /rz-inline-feedback/)
pass('receipt_list_api_failure_has_browser_authority')

assert.match(articleFeedbackTest, /app-feedback-error/)
assert.match(articleFeedbackTest, /Live artikelhistorie kon niet worden geladen/)
assert.match(articleFeedbackTest, /rz-article-detail-alert/)
pass('article_history_api_failure_has_browser_authority')

console.log('F5_14_STANDARD_API_ERROR_FEEDBACK_GREEN')
