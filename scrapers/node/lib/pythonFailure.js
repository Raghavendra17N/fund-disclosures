/**
 * Summarise a failed Python adapter run for the ingestion log / manifest notes.
 *
 * A Python traceback ends with the exception line, so keep the TAIL of stderr (not the head,
 * which is only the first frames) and collapse whitespace so it stays on one log line.
 */
export const PYTHON_FAILURE_MAX_CHARS = 1200;

export function summarizePythonFailure(result, maxChars = PYTHON_FAILURE_MAX_CHARS) {
  const raw = String(result?.stderr || result?.stdout || result?.error || "").trim();
  const flat = raw.replace(/\s*\n\s*/g, " | ").replace(/[ \t]+/g, " ");
  const tail = flat.length > maxChars ? `…${flat.slice(-maxChars)}` : flat;
  return `python_exit_${result?.status ?? "x"}: ${tail}`;
}
