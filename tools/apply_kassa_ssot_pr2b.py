import re, os, io, sys
p = 'frontend/src/features/receipts/KassaPage.jsx'
s = open(p, 'r', encoding='utf-8').read()
# import replace
s = s.replace("import useDismissOnComponentClick from '../../lib/useDismissOnComponentClick.js'\n",
              "import useDismissOnComponentClick from '../../lib/useDismissOnComponentClick.js'\nimport { mapReceiptsForKassaInbox, buildKassaInboxSummary } from './services/KassaInboxLogic.js'\n")
# remove normalizeInboxStatus function
s = re.sub(r"\nfunction normalizeInboxStatus\([\s\S]*?\n}\n", "\n", s)
# replace inboxItems mapping
s = re.sub(r"const inboxItems = useMemo\(\(\) => \{[\s\S]*?\}\, \[receipts, deletedReceiptIds\]\)",
           "const inboxItems = useMemo(() => {\n    return mapReceiptsForKassaInbox(\n      receipts.filter((item) => !deletedReceiptIds.includes(String(item?.receipt_table_id || '')))\n    ).sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))\n  }, [receipts, deletedReceiptIds])", s)
# replace summary
s = s.replace("const inboxSummary = useMemo(() => ({}), [inboxItems])",
              "const inboxSummary = useMemo(() => buildKassaInboxSummary(inboxItems), [inboxItems])")
open(p, 'w', encoding='utf-8').write(s)
# delete workflow and self
try:
 os.remove('.github/workflows/apply-kassa-ssot-pr2b.yml')
 os.remove('tools/apply_kassa_ssot_pr2b.py')
except Exception:
 pass
print('patched')
