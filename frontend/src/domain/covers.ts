/**
 * Cover identity: where the image comes from, and what stands in when there
 * is none.
 *
 * The panel always asks its OWN api, never the address the database stored.
 * The source's image hosts answer 403 to a request that does not carry their
 * own Referer, so a hotlinked cover renders broken — the API serves the bytes
 * it cached instead.
 */

/** The panel's own cover route. 404 there is ordinary: a manga can be listed
 *  long before `cache-covers` reaches it, which is why callers need a
 *  fallback rather than a guarantee. */
export function coverUrl(mangaId: number): string {
  return `/api/covers/${mangaId}`;
}

/** Words that carry no identity, so the initials skip them. */
const SKIP = new Set(["the", "of", "a", "an", "el", "la", "los", "las", "de", "del"]);

/**
 * Initials of the first two significant words.
 *
 * This is the fallback's whole job: on this reading list "Genius" appears in
 * three titles and "Regressed" in two, so a generic grey box would leave the
 * colliding ones indistinguishable — which is the problem the cover grid
 * exists to solve.
 */
export function initials(title: string): string {
  const words = title
    .replace(/[^\p{L}\p{N} ]/gu, " ")
    .split(/\s+/)
    .filter((word) => word && !SKIP.has(word.toLowerCase()));
  const picked = (words.length > 0 ? words : [title.trim() || "?"]).slice(0, 2);
  return picked.map((word) => (word[0] ?? "?").toUpperCase()).join("");
}

/**
 * A stable hue per title, so a manga keeps its colour across reloads and
 * across devices. Derived from the title rather than from the id because the
 * colour is a memory aid for a human, and the human reads titles.
 */
export function hueOf(title: string): number {
  let hash = 0;
  for (const char of title) {
    hash = (hash * 31 + (char.codePointAt(0) ?? 0)) % 360;
  }
  return hash;
}
