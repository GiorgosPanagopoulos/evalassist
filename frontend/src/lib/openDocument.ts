import { ApiError, type ApiClient } from '../api/client'
import type { TimelinePoint } from '../api/types'

export type DocumentApi = Pick<ApiClient, 'documentFile'>

// Ουδέτερα μηνύματα: ποτέ ο τεχνικός λόγος του server.
export const DOCUMENT_UNAVAILABLE = 'Το έγγραφο δεν είναι διαθέσιμο'
export const POPUP_BLOCKED = 'Επιτρέψτε τα αναδυόμενα παράθυρα για να ανοίξει το έγγραφο'
export const LOADING_TEXT = 'Φόρτωση εγγράφου…'

// Ο viewer χρειάζεται το blob μόνο όσο φορτώνει· μετά απελευθερώνεται.
export const REVOKE_AFTER_MS = 60_000

export type OpenResult = 'opened' | 'unavailable' | 'popup_blocked' | 'unauthorized'

type OpenWindow = Pick<Window, 'open'>

/**
 * Ανοίγει το PDF σε νέα καρτέλα, στη σελίδα του σημείου.
 *
 * Η καρτέλα ανοίγει συγχρονικά, μέσα στο κλικ, πριν από το request: μετά από
 * ένα await οι popup blockers μπορεί να την μπλοκάρουν. Το PDF φτάνει με
 * fetch, ώστε μια αποτυχία να γίνει μήνυμα στο UI και όχι JSON σε νέα
 * καρτέλα. Ένα κλικ, ένα request: τίποτα δεν κρατιέται για επόμενο κλικ.
 */
export async function openDocument(
  api: DocumentApi,
  personId: string,
  point: TimelinePoint,
  win: OpenWindow = window,
): Promise<OpenResult> {
  const tab = win.open('', '_blank')
  if (!tab) return 'popup_blocked'
  // Ίδιο αποτέλεσμα με το noopener, που όμως θα επέστρεφε null αντί για την καρτέλα.
  tab.opener = null
  try {
    tab.document.title = LOADING_TEXT
    tab.document.body.textContent = LOADING_TEXT
  } catch {
    // Η καρτέλα αλλάζει σελίδα σε λίγο έτσι κι αλλιώς.
  }

  let blob: Blob
  try {
    blob = await api.documentFile(personId, point.doc_id, point.period)
  } catch (err) {
    tab.close()
    return err instanceof ApiError && err.status === 401 ? 'unauthorized' : 'unavailable'
  }

  const url = URL.createObjectURL(new Blob([blob], { type: 'application/pdf' }))
  tab.location.href = `${url}#page=${point.page ?? 1}`
  setTimeout(() => URL.revokeObjectURL(url), REVOKE_AFTER_MS)
  return 'opened'
}
