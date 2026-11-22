/**
 * Resolves an internal site path against Astro's configured BASE_URL
 * (e.g. "/sapphire/" in production or "/" in local overrides).
 */
export function withBase(path: string, base: string = import.meta.env.BASE_URL): string {
  const cleanBase = base.endsWith('/') ? base.slice(0, -1) : base;
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  if (!cleanBase || cleanBase === '/') {
    return cleanPath;
  }
  return `${cleanBase}${cleanPath}`;
}

/**
 * Strips the configured BASE_URL prefix from a pathname for active-nav checks.
 */
export function stripBase(pathname: string, base: string = import.meta.env.BASE_URL): string {
  const cleanBase = base.endsWith('/') ? base.slice(0, -1) : base;
  if (
    cleanBase &&
    cleanBase !== '/' &&
    (pathname === cleanBase || pathname.startsWith(`${cleanBase}/`))
  ) {
    const rest = pathname.slice(cleanBase.length);
    return rest.startsWith('/') ? rest : `/${rest}`;
  }
  return pathname || '/';
}
