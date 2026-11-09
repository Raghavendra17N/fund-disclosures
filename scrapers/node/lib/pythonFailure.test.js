import test from "node:test";
import assert from "node:assert/strict";
import { summarizePythonFailure } from "./pythonFailure.js";

const TRACE = [
  "Traceback (most recent call last):",
  '  File "/runner/fetch_bajaj.py", line 251, in <module>',
  "    main()",
  '  File "/runner/fetch_bajaj.py", line 190, in main',
  "    items = fetch_media_search(query)",
  "requests.exceptions.ConnectionError: HTTPSConnectionPool(host='x', port=443): Max retries exceeded",
].join("\n");

test("keeps the exception line at the end of a traceback (the old 240-char head lost it)", () => {
  const out = summarizePythonFailure({ status: 1, stderr: TRACE });
  assert.ok(out.startsWith("python_exit_1: "));
  assert.ok(out.includes("requests.exceptions.ConnectionError"));
  assert.ok(!out.includes("\n"));
});

test("long output is cut from the head, never the tail", () => {
  const stderr = `${"frame ".repeat(1000)}\nValueError: the real reason`;
  const out = summarizePythonFailure({ status: 1, stderr }, 200);
  assert.ok(out.endsWith("ValueError: the real reason"));
  assert.ok(out.length < 260);
});

test("falls back to stdout, error, then an unknown status", () => {
  assert.match(summarizePythonFailure({ status: 2, stdout: "boom" }), /^python_exit_2: boom$/);
  assert.match(summarizePythonFailure({ error: "ENOENT" }), /^python_exit_x: ENOENT$/);
  assert.equal(summarizePythonFailure({}), "python_exit_x: ");
});
