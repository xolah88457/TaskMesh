import { motion } from 'framer-motion'
import type { Agent, NetMessage } from '../types'

interface Props {
  agents: Agent[]
  running: boolean
  messages: NetMessage[]
  selectedAgentIds: string[] | null
}

const VW = 800
const VH = 500
const CX = VW / 2
const CY = VH / 2
const R  = 44

function computePositions(agents: Agent[]): Record<string, { x: number; y: number }> {
  const positions: Record<string, { x: number; y: number }> = {}
  const mgr    = agents.find(a => a.id === 'manager')
  const others = agents.filter(a => a.id !== 'manager')
  const n      = others.length

  if (n === 0) {
    if (mgr) positions[mgr.id] = { x: CX, y: CY }
    return positions
  }

  if (n <= 5) {
    // Arc layout: manager top-center, others in semicircle below
    if (mgr) positions[mgr.id] = { x: CX, y: 105 }
    if (n === 1) {
      positions[others[0].id] = { x: CX, y: CY + 80 }
      return positions
    }
    const ew     = Math.min(300, (VW - 140) / 2)
    const eh     = 165
    const aStart = Math.PI * 0.1
    const aEnd   = Math.PI * 0.9
    others.forEach((agent, i) => {
      const t     = i / (n - 1)
      const angle = aStart + t * (aEnd - aStart)
      positions[agent.id] = {
        x: Math.round(CX + Math.cos(Math.PI - angle) * ew),
        y: Math.round(CY + 30 + Math.sin(angle) * eh),
      }
    })
  } else {
    // Hub-and-spoke: manager at center, others evenly in a ring
    if (mgr) positions[mgr.id] = { x: CX, y: CY }
    const radius = 185
    others.forEach((agent, i) => {
      const angle = (2 * Math.PI * i / n) - Math.PI / 2
      positions[agent.id] = {
        x: Math.round(CX + Math.cos(angle) * radius),
        y: Math.round(CY + Math.sin(angle) * radius),
      }
    })
  }

  return positions
}

function computeEdges(agents: Agent[]): Array<{ from: string; to: string; label: string }> {
  const others = agents.filter(a => a.id !== 'manager')
  const edges: Array<{ from: string; to: string; label: string }> = []
  const LABELS = ['interface {}', 'async/await', 'import *', 'schema', 'fetch()', 'assert', '→', '←', '⇄']
  let li = 0
  others.forEach(a => {
    edges.push({ from: 'manager', to: a.id, label: LABELS[li++ % LABELS.length] })
  })
  // Chain edges only for small arc layouts
  if (others.length <= 5) {
    for (let i = 0; i < others.length - 1; i++) {
      edges.push({ from: others[i].id, to: others[i + 1].id, label: LABELS[li++ % LABELS.length] })
    }
  }
  return edges
}

interface NodeProps {
  agent: Agent
  pos: { x: number; y: number }
  dimmed?: boolean
}

function AgentNode({ agent, pos, dimmed = false }: NodeProps) {
  const color    = agent.color
  const isActive = agent.status !== 'idle' && agent.status !== 'waiting' && agent.status !== 'done'
  const isDone   = agent.status === 'done'

  const dotColor = isDone ? '#3b82f6' : isActive ? '#22c55e' : '#374151'

  return (
    <g transform={`translate(${pos.x}, ${pos.y})`} opacity={dimmed ? 0.22 : 1} style={{ transition: 'opacity 0.5s' }}>
      {isActive && !dimmed && (
        <motion.circle
          r={R + 14} cx={0} cy={0}
          fill="none" stroke={color} strokeWidth="1"
          initial={{ scale: 0.85, opacity: 0.7 }}
          animate={{ scale: 1.45, opacity: 0 }}
          transition={{ duration: 1.6, repeat: Infinity, ease: 'easeOut' }}
        />
      )}
      <circle r={R + 5} cx={0} cy={0} fill="none" stroke={color} strokeWidth="0.5" opacity={0.25} />
      <circle r={R}     cx={0} cy={0} fill={`${color}1a`} stroke={color} strokeWidth="1.5" />
      <text textAnchor="middle" dominantBaseline="middle" fontSize="20" y={-7}>{agent.icon}</text>
      <text textAnchor="middle" fontSize="10.5" fill={color} y={12}
        fontFamily="JetBrains Mono, monospace" fontWeight="700">{agent.name}</text>
      <text textAnchor="middle" fontSize="8.5" y={23}
        style={{ fill: 'var(--c-text-3)' }}
        fontFamily="JetBrains Mono, monospace">{agent.role}</text>
      <motion.circle
        r={5.5} cx={R - 3} cy={-(R - 3)}
        fill={dotColor}
        animate={{ opacity: isActive ? [1, 0.35, 1] : 1 }}
        transition={{ duration: 0.9, repeat: Infinity }}
      />
    </g>
  )
}

export default function AgentNetwork({ agents, messages, selectedAgentIds }: Props) {
  if (agents.length === 0) return null

  const positions = computePositions(agents)
  const edges     = computeEdges(agents)
  const now       = Date.now()

  // During Phase 0 selection (selectedAgentIds is set), dim agents not chosen.
  // Manager is always visible. After run ends (null) everyone is full opacity.
  const isDimmed = (id: string) =>
    selectedAgentIds !== null && id !== 'manager' && !selectedAgentIds.includes(id)

  return (
    <div className="relative w-full h-full">
      <svg
        className="absolute inset-0 w-full h-full"
        viewBox={`0 0 ${VW} ${VH}`}
        preserveAspectRatio="xMidYMid meet"
      >
        <defs>
          {agents.map(a => (
            <filter key={a.id} id={`glow-${a.id}`} x="-60%" y="-60%" width="220%" height="220%">
              <feGaussianBlur stdDeviation="3" result="blur" />
              <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
            </filter>
          ))}
        </defs>

        {edges.map(({ from, to, label }) => {
          const a = positions[from]
          const b = positions[to]
          if (!a || !b) return null

          const dx  = b.x - a.x
          const dy  = b.y - a.y
          const len = Math.sqrt(dx * dx + dy * dy) || 1
          const ux  = dx / len
          const uy  = dy / len
          const x1  = a.x + ux * R
          const y1  = a.y + uy * R
          const x2  = b.x - ux * R
          const y2  = b.y - uy * R
          const mx  = (x1 + x2) / 2
          const my  = (y1 + y2) / 2

          // Find messages traveling on this edge (either direction) in the last 2s
          const edgeMsgs = messages.filter(m =>
            now - m.at < 2000 &&
            ((m.from === from && m.to === to) || (m.from === to && m.to === from))
          )

          return (
            <g key={`${from}-${to}`}>
              <line
                x1={x1} y1={y1} x2={x2} y2={y2}
                style={{ stroke: 'var(--c-border)' }} strokeWidth="1" strokeDasharray="5 4"
              />
              {edgeMsgs.map(msg => {
                const forward   = msg.from === from
                const [sx, sy, ex, ey] = forward ? [x1, y1, x2, y2] : [x2, y2, x1, y1]
                const fromAgent = agents.find(ag => ag.id === msg.from)
                return (
                  <motion.circle
                    key={msg.id}
                    r="3.5"
                    fill={fromAgent?.color ?? '#888'}
                    filter={`url(#glow-${msg.from})`}
                    initial={{ cx: sx, cy: sy, opacity: 1 }}
                    animate={{ cx: ex, cy: ey, opacity: [1, 1, 0] }}
                    transition={{
                      cx: { duration: 1.6, ease: 'linear' },
                      cy: { duration: 1.6, ease: 'linear' },
                      opacity: { duration: 1.6, times: [0, 0.65, 1] },
                    }}
                  />
                )
              })}
              <text x={mx} y={my - 7} textAnchor="middle" fontSize="8.5"
                style={{ fill: 'var(--c-text-4)' }} fontFamily="JetBrains Mono, monospace">
                {label}
              </text>
            </g>
          )
        })}

        {agents.map(agent => {
          const pos = positions[agent.id]
          return pos ? <AgentNode key={agent.id} agent={agent} pos={pos} dimmed={isDimmed(agent.id)} /> : null
        })}
      </svg>
    </div>
  )
}
