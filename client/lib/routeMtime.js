import { execFileSync } from "node:child_process";
import { statSync } from "node:fs";
import path from "node:path";

/**
 * Last modification time for a route, resolved at build time.
 *
 * Using `new Date()` in the sitemap tells crawlers every page changed on every
 * deploy, which makes <lastmod> worthless as a signal. We read the last commit
 * that touched the files backing each route instead, and fall back to the file
 * mtime when git isn't available (e.g. a build from a source tarball).
 */

const cache = new Map();

function gitLastCommit(files) {
  try {
    const out = execFileSync(
      "git",
      ["log", "-1", "--format=%cI", "--", ...files],
      { cwd: process.cwd(), encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }
    ).trim();
    return out ? new Date(out) : null;
  } catch {
    return null;
  }
}

function fileMtime(files) {
  let newest = null;
  for (const f of files) {
    try {
      const { mtime } = statSync(path.join(process.cwd(), f));
      if (!newest || mtime > newest) newest = mtime;
    } catch {
      /* file may not exist — ignore */
    }
  }
  return newest;
}

/**
 * @param {string[]} files  repo-relative paths (relative to the client dir)
 * @returns {Date}
 */
export function lastModified(files) {
  const key = files.join("|");
  if (cache.has(key)) return cache.get(key);
  const when = gitLastCommit(files) ?? fileMtime(files) ?? new Date();
  cache.set(key, when);
  return when;
}
