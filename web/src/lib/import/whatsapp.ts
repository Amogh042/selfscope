// Runs the Python WhatsApp parser (src/python/parsers/whatsapp.py) in the worker.
// The parsed DataFrame stays in the worker's memory (session.EVENTS); only a
// summary and a 20-row preview come back to the UI.

import { pythonEngine } from '../pythonEngine'
import { ensurePythonModules } from '../pythonModules'
import type { EventRow } from '../schema'

export interface ChatSummary {
  chat: string | null
  platform: 'android' | 'ios' | null
  date_order: 'DMY' | 'MDY' | 'YMD' | null
  participants: string[]
  is_group: boolean
  events: number
  messages: number
  text_messages: number
  media: number
  deleted: number
  system: number
  first_date: string | null
  last_date: string | null
  per_person: Record<string, number>
  skipped_lines: number
  preview: EventRow[]
}

const CODE = `
import session
session.import_whatsapp(file_id, chat_text, chat_name)
`

export async function parseWhatsApp(fileId: string, text: string, chatName: string | undefined): Promise<ChatSummary> {
  await ensurePythonModules()
  const { result } = await pythonEngine.runPython(CODE, {
    file_id: fileId,
    chat_text: text,
    chat_name: chatName ?? null,
  })
  return JSON.parse(result as string) as ChatSummary
}
