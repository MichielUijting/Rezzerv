export const FEATURE_GERECHTEN = 'feature.gerechten'

// Only an explicit boolean from the backend enables a registered entry point.
export function isFeatureEnabled(features, key) {
  return Object.hasOwn(features || {}, key) && features[key] === true
}
