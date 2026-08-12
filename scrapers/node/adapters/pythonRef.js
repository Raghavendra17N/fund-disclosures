/**
 * Bridge to scrapers/python/*.py (AMC-direct only).
 * Runs the script with --dry-run when possible to list URLs; otherwise runs a
 * real fetch into a staging tree and reads manifest.json.
 */
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync, mkdirSync, readdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "../../..");
const scriptsDir = join(root, "scrapers/python");
const stagingRoot = join(root, "data/staging/python");

function pythonBin() {
  const venv = join(root, ".venv/bin/python3");
  if (existsSync(venv)) return venv;
  return "python3";
}

function runPython(script, args) {
  const scriptPath = join(scriptsDir, script);
  if (!existsSync(scriptPath)) {
    return { ok: false, error: `missing ${script}`, stdout: "", stderr: "" };
  }
  const proc = spawnSync(pythonBin(), [scriptPath, ...args], {
    cwd: root,
    encoding: "utf8",
    timeout: 300_000,
    env: { ...process.env, PYTHONUNBUFFERED: "1" },
  });
  return {
    ok: proc.status === 0,
    status: proc.status,
    stdout: proc.stdout || "",
    stderr: proc.stderr || "",
    error: proc.error ? String(proc.error.message || proc.error) : undefined,
  };
}

function readManifest(slug, period) {
  const man = join(stagingRoot, "amcs", slug, period, "manifest.json");
  if (!existsSync(man)) return [];
  try {
    const data = JSON.parse(readFileSync(man, "utf8"));
    return Array.isArray(data) ? data : [];
  } catch {
    return [];
  }
}

/**
 * @param {object} cfg
 * @param {string} cfg.script e.g. fetch_bandhan.py
 * @param {string} cfg.slug folder slug under amcs/ in the python toolkit
 * @param {string[]} [cfg.extraArgs]
 */
export function createPythonRefAdapter(cfg) {
  return {
    id: "python_ref",
    script: cfg.script,
    slug: cfg.slug,
    async listFiles(ctx) {
      if (ctx.type !== "monthly" && ctx.type !== "fortnightly") {
        return { files: [], notes: `python_ref unsupported type ${ctx.type}` };
      }
      mkdirSync(stagingRoot, { recursive: true });

      const extra = [...(cfg.extraArgs || [])];
      // LIC consolidated fortnightly id; POSTs use numeric month from YYYY-MM
      if (ctx.type === "fortnightly" && cfg.script === "fetch_lic.py") {
        if (!extra.some((a) => String(a).startsWith("--consolidated-id"))) {
          extra.push("--scope", "consolidated", "--consolidated-id", "638");
        }
      }
      if (ctx.type === "fortnightly") {
        extra.push("--fortnightly");
      }

      const baseArgs = ["--months", ctx.period, "--root", stagingRoot, ...extra];

      // Hosts with broken TLS need python to materialize files (Node fetch fails).
      const forceRealFetch = ["fetch_unifi.py"].includes(cfg.script);

      // Prefer dry-run if the script supports it (unless we must stage files)
      let result = forceRealFetch
        ? runPython(cfg.script, baseArgs)
        : runPython(cfg.script, ["--dry-run", ...baseArgs]);

      const dropUnknown = (args, flag) => {
        const i = args.indexOf(flag);
        if (i >= 0) args = args.filter((_, idx) => idx !== i);
        return args;
      };

      // Some scripts don't support --dry-run and/or --fortnightly yet
      if (
        !result.ok &&
        /unrecognized arguments:\s*--dry-run|no such option.*dry-run/i.test(
          `${result.stderr}\n${result.stdout}`,
        )
      ) {
        result = runPython(cfg.script, baseArgs);
      }
      if (
        !result.ok &&
        /unrecognized arguments:\s*--fortnightly|no such option.*fortnightly/i.test(
          `${result.stderr}\n${result.stdout}`,
        )
      ) {
        const withoutFn = dropUnknown([...baseArgs], "--fortnightly");
        result = runPython(cfg.script, ["--dry-run", ...withoutFn]);
        if (
          !result.ok &&
          /unrecognized arguments:\s*--dry-run|no such option.*dry-run/i.test(
            `${result.stderr}\n${result.stdout}`,
          )
        ) {
          result = runPython(cfg.script, withoutFn);
        } else if (!result.ok) {
          result = runPython(cfg.script, withoutFn);
        }
      }

      if (!result.ok) {
        return {
          files: [],
          notes: `python_exit_${result.status ?? "x"}: ${(result.stderr || result.stdout || result.error || "").slice(0, 240)}`,
        };
      }

      const rows = readManifest(cfg.slug, ctx.period);
      const stageDir = join(stagingRoot, "amcs", cfg.slug, ctx.period);
      const files = [];
      const seen = new Set();
      for (const row of rows) {
        const url = row.download_url || row.url;
        if (!url || seen.has(url)) continue;
        if (row.error) continue;
        seen.add(url);
        const filename =
          row.saved_as || decodeURIComponent(url.split("/").pop());
        const localPath = join(stageDir, filename);
        files.push({
          url,
          filename,
          ...(existsSync(localPath) ? { localPath } : {}),
        });
      }

      // Fallback: files already written on disk (non-dry-run scripts)
      if (!files.length) {
        if (existsSync(stageDir)) {
          for (const name of readdirSync(stageDir)) {
            if (name === "manifest.json") continue;
            if (!/\.(xlsx?|xlsb|csv|zip)$/i.test(name)) continue;
            files.push({
              url: `file://${join(stageDir, name)}`,
              filename: name,
              localPath: join(stageDir, name),
            });
          }
        }
      }

      // Scripts receive --fortnightly and already scope results; keep all returned files.
      let out = files;
      return {
        files: out,
        notes: out.length
          ? `python ${cfg.script} (${ctx.type})`
          : `python ok but empty (${cfg.script}, ${ctx.type})`,
      };
    },
  };
}
