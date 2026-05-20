import { useEffect, useRef } from 'react'
import { motion } from 'framer-motion'

export default function Terminal({ lines }: { lines: string[] }) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight
  }, [lines])

  return (
    <div>
      <span className="text-[10px] tracking-widest font-mono uppercase block mb-2" style={{ color: 'var(--c-text-3)' }}>Terminal</span>
      <div
        ref={ref}
        className="rounded p-2 h-20 overflow-y-auto space-y-0.5"
        style={{ background: 'var(--c-terminal)', border: '1px solid var(--c-border)' }}
      >
        {lines.map((line, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-[10px] font-mono"
          >
            {line.startsWith('✓') ? (
              <span style={{ color: 'var(--c-accent)' }}>{line}</span>
            ) : line.startsWith('$') ? (
              <span style={{ color: 'var(--c-text-1)' }}>{line}</span>
            ) : (
              <span style={{ color: 'var(--c-text-2)' }}>{line}</span>
            )}
          </motion.div>
        ))}
        <span className="text-[10px] animate-pulse" style={{ color: 'var(--c-accent)' }}>█</span>
      </div>
    </div>
  )
}
