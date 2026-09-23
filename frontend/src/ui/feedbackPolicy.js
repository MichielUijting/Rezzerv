export const MAX_TRANSIENT_FEEDBACK_MS = 3000

export function isTransientFeedback(feedback) {
  if (!feedback) return false
  if (feedback.variant === 'progress' || feedback.dismissMode === 'blocked') return false
  if (feedback.onPrimaryAction || feedback.onSecondaryAction) return false
  if (Array.isArray(feedback.inputFields) && feedback.inputFields.length > 0) return false
  if (feedback.showTechnicalToggle) return false
  return true
}

export function transientFeedbackDuration(feedback) {
  if (!isTransientFeedback(feedback)) return 0
  const requested = Number(feedback?.autoDismissMs)
  if (!Number.isFinite(requested) || requested <= 0) return MAX_TRANSIENT_FEEDBACK_MS
  return Math.min(MAX_TRANSIENT_FEEDBACK_MS, Math.max(250, requested))
}
