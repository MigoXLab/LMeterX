import { message } from 'antd';
import i18n from '../i18n';
import { clearAuth } from './auth';

let isHandlingSessionExpired = false;

const isAuthRequest = (requestUrl?: string): boolean => {
  if (!requestUrl) {
    return false;
  }

  const path = requestUrl.split('?')[0].replace(/\/+$/, '');
  return path.endsWith('/auth/login') || path.endsWith('/auth/logout');
};

/**
 * Handle an expired authenticated session once, even when several requests
 * fail concurrently. Authentication endpoints are excluded because a login
 * failure also legitimately returns 401.
 */
export const handleUnauthorized = (requestUrl?: string): boolean => {
  if (
    isAuthRequest(requestUrl) ||
    window.location.pathname.startsWith('/login')
  ) {
    return false;
  }

  if (isHandlingSessionExpired) {
    return true;
  }

  isHandlingSessionExpired = true;
  clearAuth();

  Promise.resolve(
    message.error({
      content: i18n.t('common.sessionExpired'),
      duration: 1.5,
    })
  ).then(() => {
    window.location.assign('/login');
  });

  return true;
};

type HttpError = {
  response?: {
    status?: number;
  };
  config?: {
    url?: string;
  };
};

export const handleUnauthorizedError = (error: unknown): boolean => {
  const httpError = error as HttpError | null;
  return (
    httpError?.response?.status === 401 &&
    handleUnauthorized(httpError.config?.url)
  );
};

/**
 * Keep the original request pending while the toast is visible so local
 * request catch handlers cannot display a second, conflicting error.
 */
export const waitForLoginRedirect = (): Promise<never> =>
  new Promise<never>(() => {});
