/**
 * Seam #1 (design "Owner-Reserved", spec-panel-v1b.md fase 2): maps a day's
 * `chapters` value to a 0-4 intensity level for the heatmap's colour scale.
 *
 * The thresholds below are a PROVISIONAL first guess, not a design decision —
 * bucket count, boundaries and the colours a consumer paints per level are
 * owner-reserved (D7/D8, `/prototype` + `impeccable`). This file is meant to
 * be replaced WHOLESALE once that visual pass happens.
 *
 * Deliberately UNTESTED: the owner's `/prototype` output should be able to
 * swap this file for a different one without touching a single test.
 */

export type HeatmapLevel = 0 | 1 | 2 | 3 | 4;

export function heatmapLevel(chapters: number): HeatmapLevel {
  if (chapters <= 0) return 0;
  if (chapters < 2) return 1;
  if (chapters < 5) return 2;
  if (chapters < 10) return 3;
  return 4;
}
