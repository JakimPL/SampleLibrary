const WWW_PREFIX = "www.";

/** The site a page address leads to, as a person names it: its host without a leading `www.`. */
export function linkHost(url: string): string {
    const { hostname } = new URL(url);
    return hostname.startsWith(WWW_PREFIX) ? hostname.slice(WWW_PREFIX.length) : hostname;
}
