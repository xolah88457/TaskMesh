import { useEffect, useRef } from 'react'
import { io, Socket } from 'socket.io-client'

export interface TeamMember {
  id: string
  team_id: string
  name: string
  agent_type: string
  model: string | null
  spawn_prompt: string | null
  status: 'idle' | 'busy' | 'offline' | 'shutdown'
  is_lead: boolean
  created_at: string | null
  last_active_at: string | null
}

export interface TeamTask {
  id: string
  team_id: string
  title: string
  description: string | null
  status: 'pending' | 'in_progress' | 'done' | 'blocked' | 'failed'
  assigned_to: string | null
  depends_on: string[]
  result: string | null
  created_by: string | null
  created_at: string | null
  started_at: string | null
  completed_at: string | null
}

export interface TeamMessage {
  id: number
  team_id: string
  from_member: string
  to_member: string
  content: string
  created_at: string | null
}

export interface TeamHandlers {
  onTaskUpdate?:    (t: TeamTask) => void
  onMemberUpdate?:  (m: TeamMember) => void
  onMemberRemoved?: (member_id: string) => void
  onMessage?:       (m: TeamMessage) => void
  onTeamDeleted?:   () => void
}

/**
 * Subscribes a Socket.IO connection to one team's events. The hook does
 * not own React state — callers pass handler callbacks. Disconnects /
 * resubscribes whenever team_id changes.
 */
export function useTeamSocket(team_id: string | null, handlers: TeamHandlers) {
  const handlersRef = useRef(handlers)
  // Always invoke the latest callbacks without resubscribing on every render.
  handlersRef.current = handlers

  useEffect(() => {
    if (!team_id) return
    const url = import.meta.env.VITE_SOCKET_URL || undefined
    const socket: Socket = io(url, { path: '/socket.io', transports: ['websocket', 'polling'] })

    const send = () => socket.emit('team_subscribe', { team_id })
    socket.on('connect', send)
    if (socket.connected) send()

    socket.on('team_task_update',   (t: TeamTask)    => handlersRef.current.onTaskUpdate?.(t))
    socket.on('team_member_update', (m: TeamMember)  => handlersRef.current.onMemberUpdate?.(m))
    socket.on('team_member_removed', (p: { member_id: string }) => handlersRef.current.onMemberRemoved?.(p.member_id))
    socket.on('team_message',       (m: TeamMessage) => handlersRef.current.onMessage?.(m))
    socket.on('team_deleted',       ()               => handlersRef.current.onTeamDeleted?.())

    return () => {
      try { socket.emit('team_unsubscribe', { team_id }) } catch { /* ignore */ }
      socket.disconnect()
    }
  }, [team_id])
}
