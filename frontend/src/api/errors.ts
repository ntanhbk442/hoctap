import { ApiError } from './client'

/** Where the UI should go for an auth error from a guarded parent route, if anywhere. */
export function authRedirect(error: unknown): string | null {
  if (!(error instanceof ApiError)) return null
  if (error.status === 403 && error.code === 'SETUP_REQUIRED') return '/setup'
  if (error.status === 401 && error.code === 'UNAUTHORIZED') return '/parent/login'
  return null
}

export const GENERIC_ERROR = 'Đã xảy ra lỗi. Vui lòng thử lại.'

/**
 * A Vietnamese message for any error thrown by the API helpers. Only messages from the
 * server's error envelope are shown; anything else (HTTP statusText such as
 * "Bad Gateway", network failures) gets a generic Vietnamese message.
 */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError && error.code !== 'HTTP_ERROR' && error.message) {
    return error.message
  }
  return GENERIC_ERROR
}
