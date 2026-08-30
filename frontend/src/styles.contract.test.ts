import { describe, expect, it } from "vitest";
// Raw text, not a stylesheet import: this file is read as a string on
// purpose, never applied to the DOM. `?raw` is Vite's own import suffix
// (declared in vite/client.d.ts), so no new dependency and no Node `fs`
// typing is needed for a browser-only tsconfig.
import css from "./styles.css?raw";

/**
 * `styles.css` read as text, not as computed style.
 *
 * jsdom has no layout engine, so every rect is 0 and no cascade actually
 * resolves -- a computed-style assertion here would pass regardless of the
 * real rule (design's own jsdom caveat, `design.md` "Testing Strategy").
 * These two rules are exactly the ones a naive edit is likely to reintroduce
 * silently, so the source text is what this suite checks instead.
 */
const withoutComments = css.replace(/\/\*[\s\S]*?\*\//g, "");

function ruleBody(pattern: RegExp): string {
  const match = withoutComments.match(pattern);
  if (!match) throw new Error(`selector not found in styles.css: ${pattern}`);
  return match[1];
}

describe("styles.css contract", () => {
  it("keeps the .meta row from ever wrapping to a second line", () => {
    // The jsdom-safe proxy for "the meta row must stay on one line" (Requirement
    // "The card is the poster, with a single non-wrapping meta row"): no real
    // layout runs in vitest, so `white-space: nowrap` in the source is what
    // this suite can actually verify.
    const body = ruleBody(/(?:^|[\s,}])\.meta\s*\{([^}]*)\}/);
    expect(body).toMatch(/white-space:\s*nowrap/);
  });

  it("writes the saving opacity as the two-class selector, never the bare one (design D7)", () => {
    const body = ruleBody(/(?:^|[\s,}])\.card\.card-saving\s*\{([^}]*)\}/);
    expect(body).toMatch(/opacity:\s*0\.55/);

    // `.card-saving` alone is specificity (0,1,0) and loses to
    // `.card[data-done]` (0,1,1) the instant both apply to one card, which
    // silently kills the "being written" signal. `(?<!\.card)` excludes the
    // compound selector above -- only a reintroduced bare rule can match.
    expect(withoutComments).not.toMatch(/(?<!\.card)\.card-saving\s*\{/);
  });

  it("keeps the popover below the add-manga modal (design D2 z-index correction)", () => {
    // PROTO ports verbatim at z-index 30; `.modal-backdrop` here is 20
    // (verified at the selector below), so a popover above the add modal
    // would be a defect, not a detail.
    const body = ruleBody(/(?:^|[\s,}])\.pop\s*\{([^}]*)\}/);
    expect(body).toMatch(/z-index:\s*10\b/);
    expect(body).not.toMatch(/z-index:\s*30\b/);

    const backdropBody = ruleBody(/(?:^|[\s,}])\.modal-backdrop\s*\{([^}]*)\}/);
    expect(backdropBody).toMatch(/z-index:\s*20\b/);
  });
});
