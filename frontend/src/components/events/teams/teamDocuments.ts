import { DOCUMENT_TYPES, MAX_DOCUMENT_BYTES } from '@/components/events/teams/teamHelpers'

import type { TeamDocumentRead } from '@/client/types.gen'

/**
 * Raw `fetch` (the generated client does not do multipart) answers with a
 * plain Response; shape a failure like an axios error so `toastApiError`
 * translates the problem `code` (`team.document_too_large`,
 * `sandbox.upload_disabled`, …) the same way as for every other request.
 */
async function responseError(response: Response) {
  const data: unknown = await response.json().catch(() => null)
  return Object.assign(new Error(`Request failed: ${response.status}`), {
    isAxiosError: true,
    response: { status: response.status, data },
  })
}

function documentUrl(eventId: string, teamId: string, requirementId: string): string {
  return `${import.meta.env.VITE_API_URL}/events/${eventId}/teams/${teamId}/join/documents/${requirementId}`
}

/** Why a picked file will be refused before it is sent, if it will. */
export function documentProblem(file: File): 'type' | 'size' | null {
  if (!DOCUMENT_TYPES.includes(file.type)) return 'type'
  if (file.size > MAX_DOCUMENT_BYTES) return 'size'
  return null
}

/** Attach (or replace) the caller's file for one requirement of a pending request. */
export async function uploadTeamDocument(
  token: string,
  eventId: string,
  teamId: string,
  requirementId: string,
  file: File,
): Promise<TeamDocumentRead> {
  const body = new FormData()
  body.append('file', file, file.name)
  const response = await fetch(documentUrl(eventId, teamId, requirementId), {
    method: 'PUT',
    headers: { Authorization: `Bearer ${token}` },
    body,
  })
  if (!response.ok) throw await responseError(response)
  return (await response.json()) as TeamDocumentRead
}

/** Take the caller's file back off their pending request. */
export async function deleteTeamDocument(
  token: string,
  eventId: string,
  teamId: string,
  requirementId: string,
): Promise<void> {
  const response = await fetch(documentUrl(eventId, teamId, requirementId), {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw await responseError(response)
}
