export const DEFAULT_LAYER1_FIXTURE = {
  articleId: null,
  batchId: null,
  completeLineId: null,
  incompleteLineId: null,
  historyId: null,
  analysisId: null,
}

export function getLayer1Fixture() {
  try {
    const raw = window.localStorage.getItem('rezzerv_layer1_fixture')
    if (!raw) return { ...DEFAULT_LAYER1_FIXTURE }
    const parsed = JSON.parse(raw)
    return {
      ...DEFAULT_LAYER1_FIXTURE,
      ...(parsed && typeof parsed === 'object' ? parsed : {}),
    }
  } catch {
    return { ...DEFAULT_LAYER1_FIXTURE }
  }
}
