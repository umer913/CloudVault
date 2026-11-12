import { HttpErrorResponse } from '@angular/common/http';
import { getApiErrorMessage } from './api.service';

describe('getApiErrorMessage', () => {
  it('explains when a CloudVault API request cannot connect', () => {
    const error = new HttpErrorResponse({ status: 0, url: '/api/auth/me' });

    expect(getApiErrorMessage(error)).toContain("Couldn't connect to CloudVault");
  });

  it('distinguishes an interrupted file transfer from an API connection failure', () => {
    const error = new HttpErrorResponse({
      status: 0,
      url: 'https://storage.example.com/upload',
    });

    expect(getApiErrorMessage(error)).toContain('file transfer was interrupted');
  });

  it('uses the specific message returned by the API', () => {
    const error = new HttpErrorResponse({
      status: 413,
      url: '/api/files/direct-upload/start',
      error: { code: 'FILE_TOO_LARGE', message: 'The file exceeds the maximum upload size.' },
    });

    expect(getApiErrorMessage(error)).toBe('The file exceeds the maximum upload size.');
  });
});
