import { useEffect, useRef } from 'react'

const CHARS = 'アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン0123456789ABCDEFabcdef{}[]<>/*+=|'

interface Props {
  rainColor: string
  rainBg: string
}

export default function MatrixRain({ rainColor, rainBg }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const colorsRef = useRef({ rainColor, rainBg })

  useEffect(() => {
    colorsRef.current = { rainColor, rainBg }
  }, [rainColor, rainBg])

  useEffect(() => {
    const canvas = canvasRef.current!
    const ctx = canvas.getContext('2d')!
    let animId: number

    const resize = () => {
      canvas.width = canvas.offsetWidth
      canvas.height = canvas.offsetHeight
    }
    resize()
    window.addEventListener('resize', resize)

    const fontSize = 13
    let cols = Math.floor(canvas.width / fontSize)
    const drops: number[] = Array(cols).fill(1)

    const draw = () => {
      const { rainColor: color, rainBg: bg } = colorsRef.current
      ctx.fillStyle = bg
      ctx.fillRect(0, 0, canvas.width, canvas.height)

      cols = Math.floor(canvas.width / fontSize)
      while (drops.length < cols) drops.push(Math.random() * canvas.height / fontSize)
      if (drops.length > cols) drops.length = cols

      ctx.font = `${fontSize}px monospace`
      for (let i = 0; i < cols; i++) {
        const char = CHARS[Math.floor(Math.random() * CHARS.length)]
        ctx.globalAlpha = Math.random() > 0.95 ? 1 : 0.75
        ctx.fillStyle = color
        ctx.fillText(char, i * fontSize, drops[i] * fontSize)
        ctx.globalAlpha = 1

        if (drops[i] * fontSize > canvas.height && Math.random() > 0.975) drops[i] = 0
        drops[i]++
      }
      animId = requestAnimationFrame(draw)
    }

    draw()
    return () => {
      cancelAnimationFrame(animId)
      window.removeEventListener('resize', resize)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 w-full h-full opacity-30 pointer-events-none"
    />
  )
}
