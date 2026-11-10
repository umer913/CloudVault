import { HttpClient, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { CreatedShare, FileList, FileRecord, Folder, FolderContents, FolderTree, Share, Usage, User } from '../models/api.models';
import { environment } from '../../../environments/environment';

export function getApiErrorMessage(error: unknown, fallback = 'Request failed.') {
  if (error instanceof HttpErrorResponse) {
    const message = error.error?.message;
    if (typeof message === 'string' && message) return message;
    if (error.status === 0) return 'Cannot connect to the CloudVault API.';
  }
  return error instanceof Error && error.message ? error.message : fallback;
}

class DirectUploadUnavailable extends Error {}
export class UploadCancelledError extends Error {
  constructor() {
    super('Upload was cancelled.');
    this.name = 'UploadCancelledError';
  }
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = environment.apiUrl;

  login(email: string, password: string) {
    const body = new URLSearchParams({ username: email, password });
    return firstValueFrom(this.http.post<{ access_token: string }>(
      `${this.baseUrl}/api/auth/login`,
      body.toString(),
      { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } },
    ));
  }

  register(name: string, email: string, password: string) {
    return firstValueFrom(this.http.post<User>(`${this.baseUrl}/api/auth/register`, { name, email, password }));
  }

  user() { return firstValueFrom(this.http.get<User>(`${this.baseUrl}/api/auth/me`)); }
  usage() { return firstValueFrom(this.http.get<Usage>(`${this.baseUrl}/api/storage/usage`)); }

  folderTree() {
    return firstValueFrom(this.http.get<FolderTree[]>(`${this.baseUrl}/api/folders/tree`));
  }

  listFiles(options: {
    folderId: number | null;
    query?: string;
    type?: string;
    sort?: string;
    order?: string;
    limit?: number;
    offset?: number;
  }) {
    let params = new HttpParams()
      .set('limit', options.limit ?? 12)
      .set('offset', options.offset ?? 0)
      .set('sort', options.sort ?? 'created_at')
      .set('order', options.order ?? 'desc');
    if (options.folderId !== null) params = params.set('folder_id', options.folderId);
    if (options.query) params = params.set('q', options.query);
    if (options.type) params = params.set('type', options.type);
    return firstValueFrom(this.http.get<FileList>(`${this.baseUrl}/api/files`, { params }));
  }

  rootContents(fileOptions?: Omit<Parameters<ApiService['listFiles']>[0], 'folderId'>) {
    return Promise.all([
      firstValueFrom(this.http.get<Folder[]>(`${this.baseUrl}/api/folders`)),
      this.listFiles({ ...fileOptions, folderId: null }),
    ]).then(([folders, files]) => ({
      id: 0,
      name: 'My files',
      parent_id: null,
      created_at: new Date(0).toISOString(),
      breadcrumbs: [],
      folders,
      files: files.items,
      total: files.total,
    }));
  }

  folderContents(id: number, fileOptions?: Omit<Parameters<ApiService['listFiles']>[0], 'folderId'>) {
    return Promise.all([
      firstValueFrom(this.http.get<FolderContents>(`${this.baseUrl}/api/folders/${id}`)),
      this.listFiles({ ...fileOptions, folderId: id }),
    ]).then(([contents, files]) => ({ ...contents, files: files.items, total: files.total }));
  }

  createFolder(name: string, parentId: number | null) {
    return firstValueFrom(this.http.post<Folder>(
      `${this.baseUrl}/api/folders`,
      { name, parent_id: parentId },
    ));
  }

  renameFolder(id: number, name: string) {
    return firstValueFrom(this.http.patch<Folder>(
      `${this.baseUrl}/api/folders/${id}`,
      { name },
    ));
  }

  deleteFolder(id: number) {
    return firstValueFrom(this.http.delete<void>(`${this.baseUrl}/api/folders/${id}`));
  }

  renameFile(id: number, name: string) {
    return firstValueFrom(this.http.patch<FileRecord>(
      `${this.baseUrl}/api/files/${id}`,
      { name },
    ));
  }

  deleteFile(id: number) {
    return firstValueFrom(this.http.delete<void>(`${this.baseUrl}/api/files/${id}`));
  }

  createShare(fileId: number, permission: Share['permission'], expiresAt: string, password?: string) {
    return firstValueFrom(this.http.post<CreatedShare>(`${this.baseUrl}/api/shares`, {
      file_id: fileId,
      permission,
      expires_at: expiresAt,
      ...(password ? { password } : {}),
    }));
  }

  listShares() {
    return firstValueFrom(this.http.get<Share[]>(`${this.baseUrl}/api/shares`));
  }

  revokeShare(id: number) {
    return firstValueFrom(this.http.delete<void>(`${this.baseUrl}/api/shares/${id}`));
  }

  publicShareUrl(token: string) {
    return `${this.baseUrl}/api/public/share/${token}/content`;
  }

  downloadFile(id: number, inline = false) {
    return firstValueFrom(this.http.get(
      `${this.baseUrl}/api/files/${id}/download?inline=${inline}`,
      { observe: 'response', responseType: 'blob' },
    ));
  }

  signedFileUrl(id: number, inline = false) {
    return firstValueFrom(this.http.get<{ url: string }>(
      `${this.baseUrl}/api/files/${id}/signed-url?inline=${inline}`,
    ));
  }

  uploadProgress(uploadId: string) {
    return firstValueFrom(this.http.get<{
      loaded: number;
      total: number;
      phase: string;
      complete: boolean;
    }>(`${this.baseUrl}/api/files/upload-progress/${uploadId}`));
  }

  upload(
    file: File,
    folderId: number | null,
    onProgress?: (progress: number | null) => void,
    signal?: AbortSignal,
  ) {
    return this.uploadDirect(file, folderId, onProgress, signal).catch((error: unknown) => {
      if (error instanceof DirectUploadUnavailable) {
        return this.uploadLegacy(file, folderId, onProgress, signal);
      }
      throw error;
    });
  }

  private async uploadDirect(
    file: File,
    folderId: number | null,
    onProgress?: (progress: number | null) => void,
    signal?: AbortSignal,
  ) {
    if (signal?.aborted) throw new UploadCancelledError();
    const head = new Uint8Array(await file.slice(0, 8192).arrayBuffer());
    let binary = '';
    for (const byte of head) binary += String.fromCharCode(byte);
    let start: {
      token: string;
      part_size: number;
      parts: Array<{ part_number: number; url: string }>;
    };
    try {
      start = await firstValueFrom(this.http.post<{
        token: string;
        part_size: number;
        parts: Array<{ part_number: number; url: string }>;
      }>(`${this.baseUrl}/api/files/direct-upload/start`, {
        filename: file.name,
        size: file.size,
        folder_id: folderId,
        content_head: btoa(binary),
      }));
    } catch (error) {
      if (error instanceof HttpErrorResponse && error.status === 409) {
        throw new DirectUploadUnavailable();
      }
      throw error;
    }

    const loaded = new Array<number>(start.parts.length).fill(0);
    const etags = new Array<string>(start.parts.length);
    const report = () => {
      const transferred = loaded.reduce((total, part) => total + part, 0);
      onProgress?.(Math.min(99, Math.round((transferred / file.size) * 99)));
    };
    let nextPart = 0;
    const uploadWorker = async () => {
      while (nextPart < start.parts.length) {
        if (signal?.aborted) throw new UploadCancelledError();
        const index = nextPart++;
        const part = start.parts[index];
        const offset = index * start.part_size;
        const chunk = file.slice(offset, Math.min(file.size, offset + start.part_size));
        const etag = await this.uploadPartWithRetry(part.url, chunk, (value) => {
          loaded[index] = value;
          report();
        }, signal);
        loaded[index] = chunk.size;
        report();
        etags[index] = etag;
      }
    };

    try {
      await Promise.all(
        Array.from(
          { length: Math.min(4, start.parts.length) },
          () => uploadWorker(),
        ),
      );
      return await firstValueFrom(this.http.post<FileRecord>(
        `${this.baseUrl}/api/files/direct-upload/complete`,
        {
          parts: start.parts.map((part, index) => ({
            part_number: part.part_number,
            etag: etags[index],
          })),
        },
        { params: { token: start.token } },
      ));
    } catch (error) {
      await firstValueFrom(this.http.post<void>(
        `${this.baseUrl}/api/files/direct-upload/abort`,
        {},
        { params: { token: start.token } },
      )).catch(() => undefined);
      throw error;
    }
  }

  private uploadPart(
    url: string,
    chunk: Blob,
    onProgress: (loaded: number) => void,
    signal?: AbortSignal,
  ): Promise<string> {
    return new Promise((resolve, reject) => {
      const request = new XMLHttpRequest();
      request.open('PUT', url);
      const abort = () => {
        request.abort();
        reject(new UploadCancelledError());
      };
      signal?.addEventListener('abort', abort, { once: true });
      request.upload.addEventListener('progress', (event) => {
        onProgress(event.lengthComputable ? event.loaded : 0);
      });
      request.addEventListener('load', () => {
        signal?.removeEventListener('abort', abort);
        if (request.status >= 200 && request.status < 300) {
          const etag = request.getResponseHeader('ETag');
          if (etag) {
            resolve(etag);
          } else {
            reject(new Error('B2 did not return an upload part identifier.'));
          }
          return;
        }
        reject(new HttpErrorResponse({
          status: request.status,
          statusText: request.statusText,
          url: request.responseURL || url,
        }));
      });
      request.addEventListener('error', () => reject(new HttpErrorResponse({
        status: 0,
        statusText: 'Network Error',
        url,
      })));
      request.addEventListener('abort', () => {
        signal?.removeEventListener('abort', abort);
        reject(signal?.aborted ? new UploadCancelledError() : new Error('Upload was cancelled.'));
      });
      request.send(chunk);
    });
  }

  private async uploadPartWithRetry(
    url: string,
    chunk: Blob,
    onProgress: (loaded: number) => void,
    signal?: AbortSignal,
  ) {
    let lastError: unknown;
    for (let attempt = 1; attempt <= 3; attempt += 1) {
      if (signal?.aborted) throw new UploadCancelledError();
      try {
        return await this.uploadPart(url, chunk, onProgress, signal);
      } catch (error) {
        lastError = error;
        if (error instanceof UploadCancelledError || attempt === 3) throw error;
        onProgress(0);
        await new Promise((resolve) => setTimeout(resolve, 500 * attempt));
      }
    }
    throw lastError;
  }

  private uploadLegacy(
    file: File,
    folderId: number | null,
    onProgress?: (progress: number | null) => void,
    signal?: AbortSignal,
  ) {
    const body = new FormData();
    body.append('file', file);
    if (folderId !== null) body.append('folder_id', String(folderId));
    const uploadId = crypto.randomUUID();
    return new Promise<FileRecord>((resolve, reject) => {
      const request = new XMLHttpRequest();
      request.open('POST', `${this.baseUrl}/api/files/upload`);
      signal?.addEventListener('abort', () => request.abort(), { once: true });
      const token = localStorage.getItem('cloudvault_token');
      if (token) request.setRequestHeader('Authorization', `Bearer ${token}`);
      request.setRequestHeader('X-Upload-ID', uploadId);
      let polling = true;
      const pollStorage = async () => {
        while (polling) {
          try {
            const progress = await this.uploadProgress(uploadId);
            if (progress.total > 0) {
              const storagePercent = Math.round((progress.loaded / progress.total) * 50);
              onProgress?.(Math.min(99, 50 + storagePercent));
            }
            if (progress.complete) return;
          } catch {
            // The route is not registered until multipart parsing finishes.
          }
          await new Promise((wait) => setTimeout(wait, 400));
        }
      };
      void pollStorage();

      request.upload.addEventListener('progress', (event) => {
        if (!event.lengthComputable || event.total <= 0) {
          onProgress?.(null);
          return;
        }
        onProgress?.(Math.min(50, Math.round((event.loaded / event.total) * 50)));
      });
      request.upload.addEventListener('loadstart', () => onProgress?.(0));
      request.addEventListener('load', () => {
        polling = false;
        if (request.status >= 200 && request.status < 300) {
          onProgress?.(100);
          try {
            resolve(JSON.parse(request.responseText) as FileRecord);
          } catch {
            reject(new Error('The upload response was invalid.'));
          }
          return;
        }
        let detail: unknown;
        try {
          detail = JSON.parse(request.responseText);
        } catch {
          detail = undefined;
        }
        reject(new HttpErrorResponse({
          status: request.status,
          statusText: request.statusText,
          url: request.responseURL,
          error: detail,
        }));
      });
      request.addEventListener('error', () => {
        polling = false;
        reject(new HttpErrorResponse({
        status: 0,
        statusText: 'Network Error',
        url: request.responseURL,
        }));
      });
      request.addEventListener('abort', () => {
        polling = false;
        reject(new Error('Upload was cancelled.'));
      });
      request.send(body);
    });
  }
}
