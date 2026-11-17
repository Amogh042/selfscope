// 12x12 pixel-art glyphs for each data source (generic shapes, not brand logos).
import type { DetectedSource } from '../lib/import/detect'

// Each row is a string of 12 chars: '#' = filled pixel, '.' = empty.
const GLYPHS: Record<DetectedSource, { color: string; rows: string[] }> = {
  whatsapp: {
    color: 'var(--color-xp)',
    rows: [
      '............',
      '.##########.',
      '#..........#',
      '#.##.##.##.#',
      '#..........#',
      '#.######...#',
      '#..........#',
      '.#########..',
      '..##........',
      '.##.........',
      '##..........',
      '............',
    ],
  },
  spotify: {
    color: 'var(--color-orange-light)',
    rows: [
      '.....#######',
      '.....#######',
      '.....#....##',
      '.....#....##',
      '.....#....##',
      '.....#....##',
      '.....#....##',
      '..####..####',
      '.#####.#####',
      '.#####.#####',
      '..###...###.',
      '............',
    ],
  },
  youtube: {
    color: 'var(--color-danger)',
    rows: [
      '............',
      '############',
      '#..........#',
      '#...##.....#',
      '#...####...#',
      '#...######.#',
      '#...####...#',
      '#...##.....#',
      '#..........#',
      '############',
      '............',
      '............',
    ],
  },
  unknown: {
    color: 'var(--color-muted)',
    rows: [
      '............',
      '...######...',
      '..##....##..',
      '..##....##..',
      '.......##...',
      '......##....',
      '.....##.....',
      '.....##.....',
      '............',
      '.....##.....',
      '.....##.....',
      '............',
    ],
  },
}

export function SourceIcon({ source, size = 36 }: { source: DetectedSource; size?: number }) {
  const { color, rows } = GLYPHS[source]
  return (
    <svg width={size} height={size} viewBox="0 0 12 12" shapeRendering="crispEdges" aria-hidden>
      {rows.flatMap((row, y) =>
        [...row].map((c, x) => (c === '#' ? <rect key={`${x}-${y}`} x={x} y={y} width={1} height={1} fill={color} /> : null)),
      )}
    </svg>
  )
}
