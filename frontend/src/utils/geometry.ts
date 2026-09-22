import type { Point2D } from '../api/types';

export interface BoundingBox {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
  width: number;
  height: number;
}

export interface IntersectionResult {
  hasIntersection: boolean;
  intersectingSegments?: [[Point2D, Point2D], [Point2D, Point2D]];
  intersectionPoint?: Point2D;
}

/**
 * Calculates the gross area of a 2D polygon in square meters using the Shoelace formula.
 */
export function calculatePolygonArea(points: Point2D[]): number {
  if (!points || points.length < 3) {
    return 0;
  }

  let area = 0;
  const n = points.length;

  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n;
    area += points[i][0] * points[j][1];
    area -= points[j][0] * points[i][1];
  }

  return Math.abs(area) / 2;
}

/**
 * Format an array of 2D coordinates into an SVG points string.
 */
export function polyToSvgPoints(poly: Point2D[]): string {
  if (!poly || poly.length === 0) return '';
  return poly.map(([x, y]) => `${x},${y}`).join(' ');
}

/**
 * Computes the axis-aligned bounding box for a set of 2D points.
 */
export function getPolygonBoundingBox(points: Point2D[]): BoundingBox {
  if (!points || points.length === 0) {
    return { minX: 0, minY: 0, maxX: 20, maxY: 20, width: 20, height: 20 };
  }

  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;

  for (const [x, y] of points) {
    if (x < minX) minX = x;
    if (y < minY) minY = y;
    if (x > maxX) maxX = x;
    if (y > maxY) maxY = y;
  }

  const width = Math.max(maxX - minX, 1);
  const height = Math.max(maxY - minY, 1);

  return { minX, minY, maxX, maxY, width, height };
}

/**
 * Snap a value to the nearest grid increment (e.g. 0.5m or 1.0m).
 */
export function snapToGrid(value: number, step: number = 0.5): number {
  if (step <= 0) return value;
  return Math.round(value / step) * step;
}

// Orientation test: 0 = collinear, 1 = clockwise, 2 = counterclockwise
function orientation(p: Point2D, q: Point2D, r: Point2D): number {
  const val = (q[1] - p[1]) * (r[0] - q[0]) - (q[0] - p[0]) * (r[1] - q[1]);
  if (Math.abs(val) < 1e-9) return 0;
  return val > 0 ? 1 : 2;
}

// Check if point q lies on segment pr
function onSegment(p: Point2D, q: Point2D, r: Point2D): boolean {
  return (
    q[0] <= Math.max(p[0], r[0]) + 1e-9 &&
    q[0] >= Math.min(p[0], r[0]) - 1e-9 &&
    q[1] <= Math.max(p[1], r[1]) + 1e-9 &&
    q[1] >= Math.min(p[1], r[1]) - 1e-9
  );
}

/**
 * Check if two line segments p1q1 and p2q2 intersect strictly or overlap.
 */
export function doSegmentsIntersect(
  p1: Point2D,
  q1: Point2D,
  p2: Point2D,
  q2: Point2D,
  excludeEndpoints: boolean = true
): boolean {
  const o1 = orientation(p1, q1, p2);
  const o2 = orientation(p1, q1, q2);
  const o3 = orientation(p2, q2, p1);
  const o4 = orientation(p2, q2, q1);

  // General strict crossing
  if (o1 !== o2 && o3 !== o4) {
    if (excludeEndpoints) {
      // If any orientation is collinear and shares an endpoint, it's touching, not crossing
      const isSharedEndpoint =
        (p1[0] === p2[0] && p1[1] === p2[1]) ||
        (p1[0] === q2[0] && p1[1] === q2[1]) ||
        (q1[0] === p2[0] && q1[1] === p2[1]) ||
        (q1[0] === q2[0] && q1[1] === q2[1]);
      if (isSharedEndpoint) {
        return false;
      }
    }
    return true;
  }

  // Collinear overlaps (only if not excluding endpoints or if strictly overlapping)
  if (o1 === 0 && onSegment(p1, p2, q1) && (!excludeEndpoints || (!isSamePoint(p1, p2) && !isSamePoint(q1, p2)))) return true;
  if (o2 === 0 && onSegment(p1, q2, q1) && (!excludeEndpoints || (!isSamePoint(p1, q2) && !isSamePoint(q1, q2)))) return true;
  if (o3 === 0 && onSegment(p2, p1, q2) && (!excludeEndpoints || (!isSamePoint(p2, p1) && !isSamePoint(q2, p1)))) return true;
  if (o4 === 0 && onSegment(p2, q1, q2) && (!excludeEndpoints || (!isSamePoint(p2, q1) && !isSamePoint(q2, q1)))) return true;

  return false;
}

function isSamePoint(p1: Point2D, p2: Point2D, eps: number = 1e-6): boolean {
  return Math.abs(p1[0] - p2[0]) < eps && Math.abs(p1[1] - p2[1]) < eps;
}

/**
 * Checks if a polygon contains any self-intersecting non-adjacent edges.
 */
export function checkPolygonSelfIntersection(
  points: Point2D[],
  isClosed: boolean = true
): IntersectionResult {
  if (!points || points.length < 4) {
    return { hasIntersection: false };
  }

  const n = points.length;
  // Edge list: if closed, edges are (i, i+1) for i = 0..n-1 with last wrapping to 0
  // if not closed, edges are (i, i+1) for i = 0..n-2
  const edgeCount = isClosed ? n : n - 1;

  for (let i = 0; i < edgeCount; i++) {
    const p1 = points[i];
    const q1 = points[(i + 1) % n];

    for (let j = i + 1; j < edgeCount; j++) {
      // Adjacent edges share a vertex, skip
      if (j === i) continue;
      if (j === (i + 1) % n) continue;
      if (isClosed && i === 0 && j === n - 1) continue;

      const p2 = points[j];
      const q2 = points[(j + 1) % n];

      if (doSegmentsIntersect(p1, q1, p2, q2, true)) {
        return {
          hasIntersection: true,
          intersectingSegments: [[p1, q1], [p2, q2]],
        };
      }
    }
  }

  return { hasIntersection: false };
}

/**
 * Common preset geometries in meters.
 */
export const PLOT_PRESETS: Record<string, { name: string; description: string; points: Point2D[] }> = {
  rectangle_standard: {
    name: 'Standard Suburban (15m × 25m)',
    description: '15m width by 25m depth rectangular plot (375 m²)',
    points: [
      [0, 0],
      [15, 0],
      [15, 25],
      [0, 25],
    ],
  },
  l_shaped: {
    name: 'L-Shaped Corner (20m × 20m cut)',
    description: 'Corner plot with rear cutout (300 m²)',
    points: [
      [0, 0],
      [20, 0],
      [20, 10],
      [10, 10],
      [10, 20],
      [0, 20],
    ],
  },
  trapezoid: {
    name: 'Trapezoid (Cul-de-sac)',
    description: 'Tapered front to back cul-de-sac plot (320 m²)',
    points: [
      [0, 0],
      [22, 0],
      [18, 16],
      [4, 16],
    ],
  },
  infill_5sided: {
    name: '5-Sided Urban Infill',
    description: 'Non-orthogonal irregular urban infill parcel (235.5 m²)',
    points: [
      [0, 0],
      [15, 0],
      [18, 12],
      [8, 20],
      [0, 15],
    ],
  },
};

/**
 * Check if a 2D point is strictly inside a polygon using ray casting algorithm.
 */
export function isPointInPolygon(point: Point2D, polygon: Point2D[]): boolean {
  if (!polygon || polygon.length < 3) return false;
  const [x, y] = point;
  let inside = false;
  const n = polygon.length;

  for (let i = 0, j = n - 1; i < n; j = i++) {
    const [xi, yi] = polygon[i];
    const [xj, yj] = polygon[j];

    const intersect = yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi;
    if (intersect) inside = !inside;
  }

  return inside;
}

/**
 * Calculate Euclidean distance from point P to line segment AB.
 */
export function distancePointToSegment(p: Point2D, a: Point2D, b: Point2D): number {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const l2 = dx * dx + dy * dy;
  if (l2 < 1e-9) {
    return Math.hypot(p[0] - a[0], p[1] - a[1]);
  }

  const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2));
  const projX = a[0] + t * dx;
  const projY = a[1] + t * dy;
  return Math.hypot(p[0] - projX, p[1] - projY);
}

/**
 * Calculate minimum distance from a point to any edge of the polygon.
 */
export function distanceToPolygonBoundary(point: Point2D, polygon: Point2D[]): number {
  if (!polygon || polygon.length < 2) return 0;
  let minDist = Infinity;
  const n = polygon.length;

  for (let i = 0; i < n; i++) {
    const a = polygon[i];
    const b = polygon[(i + 1) % n];
    const d = distancePointToSegment(point, a, b);
    if (d < minDist) minDist = d;
  }

  return minDist;
}

/**
 * Calculates a guaranteed interior representative label point for a room polygon.
 * Ensures the label anchor never falls outside or on a wall, even for L-shaped, U-shaped,
 * or non-convex irregular polygons.
 */
export function findInteriorLabelPoint(polygon: Point2D[]): Point2D {
  if (!polygon || polygon.length === 0) return [0, 0];
  if (polygon.length < 3) return polygon[0];

  // 1. Check arithmetic centroid first
  let sx = 0,
    sy = 0;
  for (const [x, y] of polygon) {
    sx += x;
    sy += y;
  }
  const centroid: Point2D = [sx / polygon.length, sy / polygon.length];

  // If centroid is well inside (clearance >= 0.45m), use it
  if (isPointInPolygon(centroid, polygon)) {
    const clearance = distanceToPolygonBoundary(centroid, polygon);
    if (clearance >= 0.45) {
      return centroid;
    }
  }

  // 2. Sample pole-of-inaccessibility across bounding box
  const bbox = getPolygonBoundingBox(polygon);
  const steps = 14;
  const stepX = bbox.width / steps;
  const stepY = bbox.height / steps;

  let bestPoint: Point2D = centroid;
  let maxClearance = -1;

  for (let ix = 1; ix < steps; ix++) {
    const cx = bbox.minX + ix * stepX;
    for (let iy = 1; iy < steps; iy++) {
      const cy = bbox.minY + iy * stepY;
      const candidate: Point2D = [cx, cy];

      if (isPointInPolygon(candidate, polygon)) {
        const dist = distanceToPolygonBoundary(candidate, polygon);
        if (dist > maxClearance) {
          maxClearance = dist;
          bestPoint = candidate;
        }
      }
    }
  }

  return bestPoint;
}

export interface LabelStyleConfig {
  nameLines: string[];
  areaText: string;
  nameFontSize: number; // in meters (SVG units)
  areaFontSize: number; // in meters (SVG units)
  lineSpacing: number; // in meters
  isCompact: boolean;
  boxWidth: number;
  boxHeight: number;
}

/**
 * Wrap and adapt room labels based on available room dimensions and area.
 */
export function getAdaptiveLabelConfig(
  roomType: string,
  areaSqm: number,
  polygon: Point2D[]
): LabelStyleConfig {
  const bbox = getPolygonBoundingBox(polygon);
  const w = bbox.width;
  const h = bbox.height;
  const minDim = Math.min(w, h);

  // Normalize name
  const rawName = roomType.replace(/_/g, ' ').trim().toUpperCase();

  // Determine compact abbreviations for very small rooms
  let displayName = rawName;
  const isMicro = areaSqm < 4.0 || minDim < 1.4;
  const isSmall = areaSqm < 9.0 || minDim < 2.0;

  if (isMicro) {
    if (rawName.includes('BATH') || rawName.includes('TOILET')) displayName = 'BATH';
    else if (rawName.includes('POWDER')) displayName = 'POWDER';
    else if (rawName.includes('BED')) displayName = 'BED';
    else if (rawName.includes('KITCHEN')) displayName = 'KIT';
    else if (rawName.includes('LIVING')) displayName = 'LIVING';
    else if (rawName.includes('STORE')) displayName = 'STORE';
  } else if (isSmall) {
    if (rawName.includes('MASTER') && rawName.includes('BED')) displayName = 'M. BEDROOM';
  }

  // Word wrap based on available width
  const words = displayName.split(/\s+/);
  const nameLines: string[] = [];

  // Max characters per line based on width in meters
  // Assuming average char width is ~0.5 * font_size
  // If font size is ~0.25m, each char is ~0.13m
  const maxChars = Math.max(7, Math.floor((w * 0.8) / 0.18));

  if (words.length === 1 || displayName.length <= maxChars) {
    nameLines.push(displayName);
  } else {
    let curLine = '';
    for (const word of words) {
      if (!curLine) {
        curLine = word;
      } else if ((curLine + ' ' + word).length <= maxChars) {
        curLine += ' ' + word;
      } else {
        nameLines.push(curLine);
        curLine = word;
      }
    }
    if (curLine) nameLines.push(curLine);
  }

  // Compute adaptive font sizes in world meters for clean architectural drafting readability
  let nameFontSize = 0.48;
  let areaFontSize = 0.34;

  if (areaSqm >= 24 && minDim >= 3.0) {
    nameFontSize = 0.58;
    areaFontSize = 0.40;
  } else if (areaSqm >= 12 && minDim >= 2.2) {
    nameFontSize = 0.48;
    areaFontSize = 0.34;
  } else if (isSmall) {
    nameFontSize = 0.38;
    areaFontSize = 0.28;
  } else if (isMicro) {
    nameFontSize = 0.28;
    areaFontSize = 0.20;
  }

  // Safe clamping relative to available room dimensions
  nameFontSize = Math.min(nameFontSize, Math.max(0.22, minDim * 0.22));
  areaFontSize = Math.min(areaFontSize, nameFontSize * 0.72);

  const lineSpacing = nameFontSize * 1.28;
  const areaText = areaSqm > 0 ? `${areaSqm.toFixed(1)} m²` : '';

  const totalLines = nameLines.length + (areaText ? 1 : 0);
  const maxLineLen = Math.max(...nameLines.map((l) => l.length), areaText.length);
  const boxWidth = Math.min(w * 0.92, maxLineLen * (nameFontSize * 0.58) + nameFontSize * 0.6);
  const boxHeight = totalLines * lineSpacing + nameFontSize * 0.4;

  return {
    nameLines,
    areaText,
    nameFontSize: Math.round(nameFontSize * 100) / 100,
    areaFontSize: Math.round(areaFontSize * 100) / 100,
    lineSpacing: Math.round(lineSpacing * 100) / 100,
    isCompact: isMicro,
    boxWidth: Math.round(boxWidth * 100) / 100,
    boxHeight: Math.round(boxHeight * 100) / 100,
  };
}
