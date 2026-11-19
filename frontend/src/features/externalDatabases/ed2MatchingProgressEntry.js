/** Matchen resumes the existing Superuser job after viewport remounts. */
export function matchingEntryAction(job, forceNewCheck = false) {
  if (forceNewCheck) return 'start'
  if (job?.ok === false && job?.state === 'not_started') return 'start'
  if (job?.ok === true && ['running', 'completed', 'error'].includes(job.state)) return 'resume'
  return 'invalid'
}
