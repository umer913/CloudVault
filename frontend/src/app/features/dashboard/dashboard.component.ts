import { Component, computed, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService, getApiErrorMessage, UploadCancelledError } from '../../core/api/api.service';
import { AuthService } from '../../core/auth/auth.service';
import { CreatedShare, FileRecord, Folder, FolderContents, FolderTree, Share, Usage } from '../../core/models/api.models';

@Component({
  selector: 'app-dashboard',
  imports: [FormsModule],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.scss',
})
export class DashboardComponent {
  readonly auth = inject(AuthService);
  private readonly api = inject(ApiService);
  readonly viewMode = signal<'all' | 'recent' | 'starred'>('all');
  readonly contents = signal<FolderContents | null>(null);
  readonly allContents = signal<FolderContents | null>(null);
  readonly usage = signal<Usage | null>(null);
  readonly error = signal('');
  readonly isLoading = signal(false);
  readonly searchQuery = signal('');
  readonly fileType = signal('');
  readonly sortField = signal('created_at');
  readonly sortOrder = signal<'asc' | 'desc'>('desc');
  readonly page = signal(1);
  get pageSize() {
    return this.viewMode() === 'all' ? 4 : 8;
  }
  readonly totalFiles = signal(0);
  readonly totalItems = signal(0);
  readonly uploadProgress = signal<number | null>(null);
  readonly uploadPhase = signal('Preparing upload...');
  readonly isUploading = signal(false);
  readonly isDragActive = signal(false);
  readonly allFolders = signal<FolderTree[]>([]);
  readonly libraryFiles = signal<FileRecord[]>([]);
  readonly starredIds = signal<Set<number>>(new Set());
  readonly expandedFolders = signal<Set<number>>(new Set());
  readonly visibleTreeFolders = computed(() => {
    const folders = this.allFolders();
    const expanded = this.expandedFolders();
    const children = new Map<number | null, FolderTree[]>();
    for (const folder of folders) {
      const siblings = children.get(folder.parent_id) ?? [];
      siblings.push(folder);
      children.set(folder.parent_id, siblings);
    }
    const result: Array<
      | (FolderTree & { depth: number; kind: 'folder' })
      | { depth: number; kind: 'file'; file: FileRecord }
    > = [];
    const visit = (parentId: number | null, depth: number) => {
      for (const folder of children.get(parentId) ?? []) {
        result.push({ ...folder, depth, kind: 'folder' });
        if (expanded.has(folder.id)) {
          for (const file of folder.files) {
            result.push({ depth: depth + 1, kind: 'file', file });
          }
          visit(folder.id, depth + 1);
        }
      }
    };
    visit(null, 0);
    return result;
  });
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
      const user = this.auth.user();
      if (!user) {
        this.starredIds.set(new Set());
        return;
      }

      void this.refresh();
      this.loadStarredIds(user.id);
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
        limit: 100,
        offset: 0,
      };
      if (this.viewMode() === 'all') {
        const contents = await this.loadAllCurrentContents(folderId, options);
        const folders = await this.api.folderTree();
        this.allFolders.set(folders);
        if (sequence !== this.refreshSequence) return;
        this.allContents.set(contents);
        this.updateContentsPage(contents);
        this.totalFiles.set(contents.total);
      } else {
        const [folders, rootFiles] = await Promise.all([
          this.api.folderTree(),
          this.loadAllRootFiles(),
        ]);
        if (sequence !== this.refreshSequence) return;
        this.allFolders.set(folders);
        this.libraryFiles.set([
          ...rootFiles,
          ...folders.flatMap((folder) => folder.files),
        ]);
        this.updateLibraryContents();
      }
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
    this.viewMode.set('all');
    this.currentFolder = null;
    this.page.set(1);
    await this.refresh();
  }

  async openFolder(id: number) {
    if (this.isLoading()) return;
    this.viewMode.set('all');
    this.currentFolder = id;
    this.page.set(1);
    await this.refresh();
  }

  async openFileLocation(file: FileRecord) {
    if (this.isLoading()) return;
    this.viewMode.set('all');
    this.currentFolder = file.folder_id;
    this.searchQuery.set('');
    this.fileType.set('');
    this.sortField.set('created_at');
    this.sortOrder.set('desc');
    this.page.set(1);
    await this.refresh();

    const contents = this.allContents();
    const fileIndex = contents?.files.findIndex((item) => item.id === file.id) ?? -1;
    if (!contents || fileIndex < 0) return;

    this.page.set(Math.floor((contents.folders.length + fileIndex) / this.pageSize) + 1);
    this.updateContentsPage(contents);
  }

  async openLibraryView(view: 'recent' | 'starred') {
    if (this.isLoading()) return;
    this.viewMode.set(view);
    this.currentFolder = null;
    this.page.set(1);
    this.searchQuery.set('');
    this.fileType.set('');
    await this.refresh();
  }

  signOut() {
    if (window.confirm('Are you sure you want to sign out?')) {
      this.auth.logout();
    }
  }

  toggleStar(file: FileRecord) {
    const userId = this.auth.user()?.id;
    if (userId === undefined) return;

    const starred = new Set(this.starredIds());
    if (starred.has(file.id)) starred.delete(file.id);
    else starred.add(file.id);

    try {
      localStorage.setItem(this.starredStorageKey(userId), JSON.stringify([...starred]));
      this.starredIds.set(starred);
      if (this.viewMode() === 'starred') {
        this.page.set(1);
        this.updateLibraryContents();
      }
    } catch (error) {
      this.error.set(getApiErrorMessage(error, 'Unable to save starred files.'));
    }
  }

  toggleFolder(id: number) {
    const expanded = new Set(this.expandedFolders());
    if (expanded.has(id)) expanded.delete(id);
    else expanded.add(id);
    this.expandedFolders.set(expanded);
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
    if (this.viewMode() === 'all') {
      const contents = this.allContents();
      if (contents) this.updateContentsPage(contents);
    } else {
      this.updateLibraryContents();
    }
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
    const input = event.target as HTMLInputElement;
    input.value = '';
    if (file) await this.uploadFile(file);
  }

  onDragOver(event: DragEvent) {
    event.preventDefault();
    if (!this.isUploading()) this.isDragActive.set(true);
  }

  onDragLeave(event: DragEvent) {
    event.preventDefault();
    this.isDragActive.set(false);
  }

  async onDrop(event: DragEvent) {
    event.preventDefault();
    this.isDragActive.set(false);
    if (this.isUploading()) return;
    const file = event.dataTransfer?.files[0];
    if (file) await this.uploadFile(file);
  }

  private async uploadFile(file: File) {
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

  pageTitle() {
    if (this.viewMode() === 'recent') return 'Recent';
    if (this.viewMode() === 'starred') return 'Starred';
    return this.contents()?.name || 'My files';
  }

  isStarred(file: FileRecord) {
    return this.starredIds().has(file.id);
  }

  trackFile(_index: number, file: FileRecord) { return file.id; }

  pageCount() {
    return Math.max(1, Math.ceil(this.totalItems() / this.pageSize));
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

  private async loadAllRootFiles() {
    const files: FileRecord[] = [];
    let offset = 0;
    let total = 0;

    do {
      const page = await this.api.listFiles({
        folderId: null,
        sort: 'created_at',
        order: 'desc',
        limit: 100,
        offset,
      });
      files.push(...page.items);
      total = page.total;
      offset += page.items.length;
      if (!page.items.length) break;
    } while (offset < total);

    return files;
  }

  private async loadAllCurrentContents(
    folderId: number | null,
    options: Omit<Parameters<ApiService['listFiles']>[0], 'folderId'>,
  ) {
    const pageOptions = { ...options, limit: 100, offset: 0 };
    const contents = folderId === null
      ? await this.api.rootContents(pageOptions)
      : await this.api.folderContents(folderId, pageOptions);
    const files = [...contents.files];

    while (files.length < contents.total) {
      const page = await this.api.listFiles({
        ...options,
        folderId,
        limit: 100,
        offset: files.length,
      });
      if (!page.items.length) break;
      files.push(...page.items);
    }

    return { ...contents, files };
  }

  private updateContentsPage(contents: FolderContents) {
    const start = (this.page() - 1) * this.pageSize;
    const end = start + this.pageSize;
    const folderEnd = Math.min(end, contents.folders.length);
    const fileStart = Math.max(0, start - contents.folders.length);
    const fileEnd = Math.max(0, end - contents.folders.length);
    this.contents.set({
      ...contents,
      folders: contents.folders.slice(Math.min(start, contents.folders.length), folderEnd),
      files: contents.files.slice(fileStart, fileEnd),
    });
    this.totalItems.set(contents.folders.length + contents.files.length);
  }

  private updateLibraryContents() {
    const files = this.libraryFiles()
      .filter((file) => this.viewMode() !== 'starred' || this.starredIds().has(file.id))
      .sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at));
    const lastPage = Math.max(1, Math.ceil(files.length / this.pageSize));
    if (this.page() > lastPage) this.page.set(lastPage);
    const offset = (this.page() - 1) * this.pageSize;
    const pageFiles = files.slice(offset, offset + this.pageSize);
    this.contents.set({
      id: 0,
      name: this.pageTitle(),
      parent_id: null,
      created_at: new Date(0).toISOString(),
      breadcrumbs: [],
      folders: [],
      files: pageFiles,
      total: files.length,
    });
    this.totalFiles.set(files.length);
    this.totalItems.set(files.length);
  }

  private loadStarredIds(userId: number) {
    try {
      const saved = localStorage.getItem(this.starredStorageKey(userId));
      const parsed: unknown = saved ? JSON.parse(saved) : [];
      if (!Array.isArray(parsed)) {
        throw new Error('Saved starred files are invalid.');
      }
      const ids = parsed.filter(
        (id: unknown): id is number => typeof id === 'number' && Number.isInteger(id) && id > 0,
      );
      if (ids.length !== parsed.length) throw new Error('Saved starred files are invalid.');
      this.starredIds.set(new Set(ids));
    } catch (error) {
      this.starredIds.set(new Set());
      this.error.set(getApiErrorMessage(error, 'Unable to load starred files.'));
    }
  }

  private starredStorageKey(userId: number) {
    return `cloudvault_starred_${userId}`;
  }

  private defaultExpiry() {
    const expiry = new Date();
    expiry.setDate(expiry.getDate() + 7);
    expiry.setMinutes(expiry.getMinutes() - expiry.getTimezoneOffset());
    return expiry.toISOString().slice(0, 16);
  }
}
