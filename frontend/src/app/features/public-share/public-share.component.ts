import { Component, OnDestroy, OnInit, inject, signal } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { ApiService, getApiErrorMessage } from '../../core/api/api.service';
import { PublicShare } from '../../core/models/api.models';

@Component({
  selector: 'app-public-share',
  imports: [FormsModule],
  templateUrl: './public-share.component.html',
  styleUrl: './public-share.component.scss',
})
export class PublicShareComponent implements OnInit, OnDestroy {
  private readonly route = inject(ActivatedRoute);
  private readonly api = inject(ApiService);
  private readonly sanitizer = inject(DomSanitizer);
  readonly share = signal<PublicShare | null>(null);
  readonly isLoading = signal(true);
  readonly isOpening = signal(false);
  readonly passwordRequired = signal(false);
  readonly error = signal('');
  readonly previewUrl = signal<SafeResourceUrl | null>(null);
  readonly imagePreviewUrl = signal<string | null>(null);
  password = '';
  private readonly token = this.route.snapshot.paramMap.get('token') ?? '';
  private objectUrl: string | null = null;

  ngOnInit() {
    if (!this.token) {
      this.error.set('This share link is invalid.');
      this.isLoading.set(false);
      return;
    }
    void this.loadShare();
  }

  ngOnDestroy() {
    if (this.objectUrl) URL.revokeObjectURL(this.objectUrl);
  }

  async submitPassword() {
    if (!this.password.trim() || this.isLoading()) return;
    await this.loadShare(this.password);
  }

  async openSharedFile() {
    const share = this.share();
    if (!share || this.isOpening()) return;
    this.isOpening.set(true);
    this.error.set('');
    try {
      const content = await this.api.getPublicShareContent(this.token, this.password || undefined);
      this.setPreviewUrl(content);
    } catch (error) {
      this.error.set(await this.errorMessage(error, 'Unable to open this shared file.'));
    } finally {
      this.isOpening.set(false);
    }
  }

  async downloadSharedFile() {
    const share = this.share();
    if (!share || this.isOpening()) return;
    this.isOpening.set(true);
    this.error.set('');
    try {
      const content = await this.api.getPublicShareContent(this.token, this.password || undefined);
      this.setPreviewUrl(content);
      const anchor = document.createElement('a');
      anchor.href = this.objectUrl!;
      anchor.download = share.original_name;
      anchor.click();
    } catch (error) {
      this.error.set(await this.errorMessage(error, 'Unable to download this shared file.'));
    } finally {
      this.isOpening.set(false);
    }
  }

  formatBytes(bytes: number) {
    if (!bytes) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    return `${(bytes / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
  }

  private async loadShare(password?: string) {
    this.isLoading.set(true);
    this.error.set('');
    try {
      const share = await this.api.getPublicShare(this.token, password);
      this.share.set(share);
      this.passwordRequired.set(false);
    } catch (error) {
      if (this.isPasswordRequiredError(error)) {
        this.passwordRequired.set(true);
        this.error.set(password ? 'That password did not match. Please try again.' : '');
      } else {
        this.error.set(getApiErrorMessage(error, 'This share link is unavailable.'));
      }
    } finally {
      this.isLoading.set(false);
    }
  }

  private isPasswordRequiredError(error: unknown) {
    return error instanceof HttpErrorResponse
      && error.status === 401
      && error.error?.code === 'PASSWORD_REQUIRED';
  }

  private async errorMessage(error: unknown, fallback: string) {
    if (error instanceof HttpErrorResponse && error.error instanceof Blob) {
      try {
        const body: unknown = JSON.parse(await error.error.text());
        if (typeof body === 'object' && body !== null && 'message' in body
          && typeof body.message === 'string') return body.message;
      } catch {
        return fallback;
      }
    }
    return getApiErrorMessage(error, fallback);
  }

  private setPreviewUrl(content: Blob) {
    if (this.objectUrl) URL.revokeObjectURL(this.objectUrl);
    this.objectUrl = URL.createObjectURL(content);
    if (this.share()?.mime_type.startsWith('image/')) {
      this.imagePreviewUrl.set(this.objectUrl);
      this.previewUrl.set(null);
    } else {
      this.previewUrl.set(this.sanitizer.bypassSecurityTrustResourceUrl(this.objectUrl));
      this.imagePreviewUrl.set(null);
    }
  }
}
