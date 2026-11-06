import { Component, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService, getApiErrorMessage, UploadCancelledError } from '../../core/api/api.service';
import { AuthService } from '../../core/auth/auth.service';
import { CreatedShare, FileRecord, FolderContents, Share, Usage } from '../../core/models/api.models';

@Component({
  selector: 'app-dashboard',
  imports: [FormsModule],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.scss',
})
export class DashboardComponent {
  readonly auth = inject(AuthService);
  private readonly api = inject(ApiService);
  readonly contents = signal<FolderContents | null>(null);
  readonly usage = signal<Usage | null>(null);
  readonly error = signal('');
  readonly isLoading = signal(false);
  readonly searchQuery = signal('');
  readonly fileType = signal('');
  readonly sortField = signal('created_at');
  readonly sortOrder = signal<'asc' | 'desc'>('desc');
  readonly page = signal(1);
  readonly pageSize = 12;
  readonly totalFiles = signal(0);
  readonly uploadProgress = signal<number | null>(null);
  readonly uploadPhase = signal('Preparing upload...');
  readonly isUploading = signal(false);
  readonly isFolderDialogOpen = signal(false);
  readonly isCreatingFolder = signal(false);
  readonly fileActionId = signal<number | null>(null);
  readonly isRenameDialogOpen = signal(false);
  readonly isFolderRenameDialogOpen = signal(false);
  readonly isShareDialogOpen = signal(false);
  readonly isSharesDialogOpen = signal(false);
  readonly shares = signal<Share[]>([]);
  readonly shareResult = signal<CreatedShare | null>(null);
  readonly isSharing = signal(false);
  readonly isLoadingShares = signal(false);
  readonly shareTarget = signal<FileRecord | null>(null);
  readonly renameTarget = signal<FileRecord | null>(null);
  readonly folderRenameTarget = signal<number | null>(null);
  readonly folderActionId = signal<number | null>(null);
  renameName = '';
  folderName = '';
  sharePermission: Share['permission'] = 'download';
  shareExpiresAt = this.defaultExpiry();
  sharePassword = '';
  private currentFolder: number | null = null;
  private refreshSequence = 0;
  private searchTimer?: ReturnType<typeof setTimeout>;
  private uploadController?: AbortController;
  private readonly maxUploadBytes = 500 * 1024 * 1024;

  constructor() {
    effect(() => {
      if (this.auth.user()) void this.refresh();
    });
  }

  async refresh() {
    const sequence = ++this.refreshSequence;
    const folderId = this.currentFolder;
    this.isLoading.set(true);
    try {
      this.error.set('');
      const options = {
        query: this.searchQuery().trim(),
        type: this.fileType(),
        sort: this.sortField(),
        order: this.sortOrder(),
        limit: this.pageSize,
        offset: (this.page() - 1) * this.pageSize,
      };
      const contents = folderId === null
        ? await this.api.rootContents(options)
        : await this.api.folderContents(folderId, options);
      if (sequence !== this.refreshSequence) return;
      this.contents.set(contents);
      this.totalFiles.set(contents.total);
    } catch (error) {
      if (sequence !== this.refreshSequence) return;
      this.error.set(getApiErrorMessage(error, 'Unable to load files.'));
    } finally {
      if (sequence === this.refreshSequence) this.isLoading.set(false);
    }

    try {
      const usage = await this.api.usage();
      if (sequence === this.refreshSequence) this.usage.set(usage);
    } catch (error) {
      if (sequence === this.refreshSequence) {
        this.error.set(getApiErrorMessage(error, 'Unable to load storage usage.'));
      }
    }
  }

  async openRoot() {
    if (this.isLoading()) return;
    this.currentFolder = null;
    this.page.set(1);
    await this.refresh();
  }

  async openFolder(id: number) {
    if (this.isLoading()) return;
    this.currentFolder = id;
    this.page.set(1);
    await this.refresh();
  }

  onSearchChange(value: string) {
    this.searchQuery.set(value);
    this.page.set(1);
    clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => void this.refresh(), 250);
  }

  async changeFilter() {
    this.page.set(1);
    await this.refresh();
  }

  async changePage(page: number) {
    if (page < 1 || page > this.pageCount() || this.isLoading()) return;
    this.page.set(page);
    await this.refresh();
  }

  showFolderDialog() {
    this.folderName = '';
    this.error.set('');
    this.isFolderDialogOpen.set(true);
  }

  closeFolderDialog() {
    if (!this.isCreatingFolder()) this.isFolderDialogOpen.set(false);
  }

  async createFolder() {
    const name = this.folderName.trim();
    if (!name || this.isCreatingFolder()) return;
    this.isCreatingFolder.set(true);
    this.error.set('');
    try {
      await this.api.createFolder(name, this.currentFolder);
      this.isFolderDialogOpen.set(false);
      await this.refresh();
    } catch (error) {
      this.error.set(getApiErrorMessage(error, 'Unable to create folder.'));
    } finally {
      this.isCreatingFolder.set(false);
    }
  }

  showFolderRenameDialog(folderId: number, name: string) {
    this.folderRenameTarget.set(folderId);
    this.folderName = name;
    this.error.set('');
    this.isFolderRenameDialogOpen.set(true);
  }

  closeFolderRenameDialog() {
    if (!this.folderActionId()) this.isFolderRenameDialogOpen.set(false);
  }

  async renameFolder() {
    const folderId = this.folderRenameTarget();
    const name = this.folderName.trim();
    if (folderId === null || !name || this.folderActionId()) return;
    this.folderActionId.set(folderId);
    try {
      await this.api.renameFolder(folderId, name);
      this.isFolderRenameDialogOpen.set(false);
      await this.refresh();
    } catch (error) {
      this.error.set(getApiErrorMessage(error, 'Unable to rename folder.'));
    } finally {
      this.folderActionId.set(null);
    }
  }

  async deleteFolder(id: number, name: string) {
    if (this.folderActionId() || !window.confirm(`Delete "${name}" and everything inside it?`)) return;
    this.folderActionId.set(id);
    try {
      await this.api.deleteFolder(id);
      await this.refresh();
    } catch (error) {
      this.error.set(getApiErrorMessage(error, 'Unable to delete folder.'));
    } finally {
      this.folderActionId.set(null);
    }
  }

  showRenameDialog(file: FileRecord) {
    this.renameTarget.set(file);
    this.renameName = file.original_name;
    this.error.set('');
    this.isRenameDialogOpen.set(true);
  }

  closeRenameDialog() {
    if (!this.fileActionId()) this.isRenameDialogOpen.set(false);
  }

  async renameFile() {
    const file = this.renameTarget();
    const name = this.renameName.trim();
    if (!file || !name || this.fileActionId()) return;
    this.fileActionId.set(file.id);
    try {
      await this.api.renameFile(file.id, name);
      this.isRenameDialogOpen.set(false);
      await this.refresh();
    } catch (error) {
      this.error.set(getApiErrorMessage(error, 'Unable to rename file.'));
    } finally {
      this.fileActionId.set(null);
    }
  }

  async deleteFile(file: FileRecord) {
    if (this.fileActionId() || !window.confirm(`Delete "${file.original_name}"?`)) return;
    this.fileActionId.set(file.id);
    try {
      await this.api.deleteFile(file.id);
      await this.refresh();
    } catch (error) {
      this.error.set(getApiErrorMessage(error, 'Unable to delete file.'));
    } finally {
      this.fileActionId.set(null);
    }
  }

  showShareDialog(file: FileRecord) {
    this.shareTarget.set(file);
    this.shareResult.set(null);
    this.sharePermission = 'download';
    this.shareExpiresAt = this.defaultExpiry();
    this.sharePassword = '';
    this.error.set('');
    this.isShareDialogOpen.set(true);
  }

  closeShareDialog() {
    if (!this.isSharing()) this.isShareDialogOpen.set(false);
  }

  async createShare() {
    const file = this.shareTarget();
    if (!file || this.isSharing()) return;
    this.isSharing.set(true);
    this.error.set('');
    try {
      const expiresAt = new Date(this.shareExpiresAt).toISOString();
      const share = await this.api.createShare(
        file.id,
        this.sharePermission,
        expiresAt,
        this.sharePassword.trim() || undefined,
      );
      this.shareResult.set(share);
      await this.loadShares();
    } catch (error) {
      this.error.set(getApiErrorMessage(error, 'Unable to create share.'));
    } finally {
      this.isSharing.set(false);
    }
  }

  async showShares() {
    this.isSharesDialogOpen.set(true);
    await this.loadShares();
  }

  closeShares() {
    if (!this.isLoadingShares()) this.isSharesDialogOpen.set(false);
  }

  async loadShares() {
    this.isLoadingShares.set(true);
    try {
      this.shares.set(await this.api.listShares());
    } catch (error) {
      this.error.set(getApiErrorMessage(error, 'Unable to load shares.'));
    } finally {
      this.isLoadingShares.set(false);
    }
  }

  async revokeShare(share: Share) {
    if (this.isLoadingShares() || !window.confirm('Revoke this share link?')) return;
    this.isLoadingShares.set(true);
    try {
      await this.api.revokeShare(share.id);
      await this.loadShares();
    } catch (error) {
      this.error.set(getApiErrorMessage(error, 'Unable to revoke share.'));
      this.isLoadingShares.set(false);
    }
  }

  async copyShareLink(share: CreatedShare) {
    try {
      await navigator.clipboard.writeText(this.shareLink(share.token));
    } catch (error) {
      this.error.set(getApiErrorMessage(error, 'Unable to copy share link.'));
    }
  }

  async downloadFile(file: FileRecord, inline = false) {
    if (this.fileActionId()) return;
    this.fileActionId.set(file.id);
    try {
      const { url } = await this.api.signedFileUrl(file.id, inline);
      if (inline) {
        window.open(url, '_blank', 'noopener,noreferrer');
      } else {
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = file.original_name;
        anchor.click();
      }
    } catch (error) {
      this.error.set(getApiErrorMessage(error, 'Unable to download file.'));
    } finally {
      this.fileActionId.set(null);
    }
  }

  async upload(event: Event) {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file) return;
    const input = event.target as HTMLInputElement;
    input.value = '';
    if (file.size > this.maxUploadBytes) {
      this.error.set('Files must be 500 MB or smaller.');
      return;
    }
    if (this.isUploading()) return;

    this.error.set('');
    this.isUploading.set(true);
    this.uploadController = new AbortController();
    this.uploadProgress.set(0);
    this.uploadPhase.set('Uploading to CloudVault...');
    try {
      await this.api.upload(file, this.currentFolder, (progress) => {
        if (progress === null) {
          this.uploadProgress.set(null);
          this.uploadPhase.set('Uploading file...');
          return;
        }
        this.uploadProgress.set(progress);
        this.uploadPhase.set(progress >= 50
          ? 'Saving file to secure storage...'
          : 'Uploading file to CloudVault...');
      }, this.uploadController.signal);
      this.uploadProgress.set(100);
      this.uploadPhase.set('File saved successfully.');
      await this.refresh();
    } catch (error) {
      if (error instanceof UploadCancelledError) {
        this.uploadPhase.set('Upload cancelled.');
      } else {
        this.error.set(getApiErrorMessage(error, 'Upload failed.'));
      }
    } finally {
      this.isUploading.set(false);
      this.uploadController = undefined;
      this.uploadProgress.set(null);
      this.uploadPhase.set('Preparing upload...');
    }
  }

  cancelUpload() {
    this.uploadController?.abort();
  }

  formatBytes(bytes: number) {
    if (!bytes) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    return `${(bytes / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
  }

  trackFile(_index: number, file: FileRecord) { return file.id; }

  pageCount() {
    return Math.max(1, Math.ceil(this.totalFiles() / this.pageSize));
  }

  hasPreviousPage() {
    return this.page() > 1;
  }

  hasNextPage() {
    return this.page() < this.pageCount();
  }

  formatDate(value: string) {
    return new Date(value).toLocaleString();
  }

  shareLink(token: string) {
    return this.api.publicShareUrl(token);
  }

  private defaultExpiry() {
    const expiry = new Date();
    expiry.setDate(expiry.getDate() + 7);
    expiry.setMinutes(expiry.getMinutes() - expiry.getTimezoneOffset());
    return expiry.toISOString().slice(0, 16);
  }
}
