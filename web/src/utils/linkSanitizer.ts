const TRAILING_POSITION_RE = /:(\d+)(?::(\d+))?$/;
const LOCAL_PATH_PREFIXES = ["/Users/", "/home/", "/opt/", "/var/", "/tmp/"];

function stripTrailingPosition(pathname: string): string {
  return pathname.replace(TRAILING_POSITION_RE, "");
}

function toFileHrefFromAbsolutePath(pathname: string): string {
  const normalized = stripTrailingPosition(pathname);
  return `file://${encodeURI(normalized)}`;
}

export function sanitizeMarkdownHref(rawHref?: string): string | undefined {
  if (!rawHref) return rawHref;

  const href = rawHref.trim();
  if (!href) return href;

  // Keep web/email/anchor links untouched.
  if (/^(https?:|mailto:|tel:|#)/i.test(href)) return href;

  // Normalize file:// links that accidentally include trailing :line[:column].
  if (href.startsWith("file://")) {
    const pathPart = href.slice("file://".length);
    return toFileHrefFromAbsolutePath(decodeURI(pathPart));
  }

  // Treat Unix absolute paths as local file links.
  if (href.startsWith("/")) {
    return toFileHrefFromAbsolutePath(decodeURI(href));
  }

  return href;
}

export interface LocalFileTarget {
  path: string;
  line?: number;
}

function parsePathAndLine(pathText: string): LocalFileTarget {
  const decoded = decodeURI(pathText);
  const m = decoded.match(/^(.*):(\d+)(?::\d+)?$/);
  if (!m) return { path: decoded };
  return { path: m[1], line: Number(m[2]) };
}

function isLikelyLocalAbsolutePath(pathname: string): boolean {
  return LOCAL_PATH_PREFIXES.some((p) => pathname.startsWith(p));
}

export function parseLocalFileTarget(rawHref?: string): LocalFileTarget | null {
  if (!rawHref) return null;
  const href = rawHref.trim();
  if (!href) return null;

  if (href.startsWith("file://")) {
    return parsePathAndLine(href.slice("file://".length));
  }

  if (href.startsWith("/")) {
    if (!isLikelyLocalAbsolutePath(href)) return null;
    return parsePathAndLine(href);
  }

  if (/^https?:\/\//i.test(href)) {
    try {
      const u = new URL(href);
      if (isLikelyLocalAbsolutePath(u.pathname)) {
        return parsePathAndLine(u.pathname);
      }
    } catch {
      return null;
    }
  }

  return null;
}
