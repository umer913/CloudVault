import { HttpInterceptorFn } from '@angular/common/http';

export const authInterceptor: HttpInterceptorFn = (request, next) => {
  if (request.url.includes('/api/public/share/')) return next(request);
  const token = localStorage.getItem('cloudvault_token');
  return next(token
    ? request.clone({ setHeaders: { Authorization: `Bearer ${token}` } })
    : request);
};
