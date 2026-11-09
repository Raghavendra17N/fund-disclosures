/**
 * Time budget (ms) for one Python adapter run.
 *
 * Order: the AMC's own `timeout_ms` in registry/amcs.json (slow multi-page APIs such as Bandhan),
 * then the PYTHON_REF_TIMEOUT_MS environment variable, then the 120 s default.
 */
export const DEFAULT_PYTHON_TIMEOUT_MS = 120_000;

function positiveNumber(v) {
  const n = Number(v);
  return Number.isFinite(n) && n > 0 ? n : null;
}

export function resolvePythonTimeoutMs(cfgTimeoutMs, env = process.env) {
  return positiveNumber(cfgTimeoutMs) ?? positiveNumber(env.PYTHON_REF_TIMEOUT_MS) ?? DEFAULT_PYTHON_TIMEOUT_MS;
}
