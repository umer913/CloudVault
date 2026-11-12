import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { DashboardComponent } from './dashboard.component';
import { ApiService } from '../../core/api/api.service';
import { AuthService } from '../../core/auth/auth.service';

const apiMock = {
  rootContents: vi.fn(),
  folderContents: vi.fn(),
  usage: vi.fn(),
  listFiles: vi.fn(),
  regenerateShareLink: vi.fn(),
  listShares: vi.fn(),
  getFile: vi.fn(),
  publicShareUrl: vi.fn((token: string) => `https://cloudvault.example/api/public/share/${token}/content`),
};

const authMock = {
  user: signal<{ id: number; name: string; email: string; storage_quota: number; used_bytes: number } | null>(null),
  logout: vi.fn(),
};

describe('DashboardComponent', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    vi.restoreAllMocks();
    authMock.user.set(null);
    await TestBed.configureTestingModule({
      imports: [DashboardComponent],
      providers: [
        { provide: ApiService, useValue: apiMock },
        { provide: AuthService, useValue: authMock },
      ],
    }).compileComponents();
  });

  it('resets to the first page when search changes', () => {
    const component = TestBed.createComponent(DashboardComponent).componentInstance;
    component.page.set(3);

    component.onSearchChange(' report ');

    expect(component.searchQuery()).toBe(' report ');
    expect(component.page()).toBe(1);
  });

  it('calculates pagination from the server total', () => {
    const component = TestBed.createComponent(DashboardComponent).componentInstance;
    component.totalItems.set(25);

    expect(component.pageSize).toBe(12);
    expect(component.pageCount()).toBe(3);
    expect(component.hasPreviousPage()).toBe(false);
    expect(component.hasNextPage()).toBe(true);

    component.page.set(3);
    expect(component.hasPreviousPage()).toBe(true);
    expect(component.hasNextPage()).toBe(false);
  });

  it('uses a consistent title instead of the selected folder name', () => {
    const component = TestBed.createComponent(DashboardComponent).componentInstance;
    component.contents.set({
      id: 8,
      name: 'MyFolder',
      parent_id: null,
      created_at: '2026-11-10T00:00:00Z',
      breadcrumbs: [],
      folders: [],
      files: [],
      total: 0,
    });

    expect(component.pageTitle()).toBe('My Files');
    component.viewMode.set('recent');
    expect(component.pageTitle()).toBe('Recent');
    component.viewMode.set('starred');
    expect(component.pageTitle()).toBe('Starred');
  });

  it('keeps file type badges compact for arbitrary extensions', () => {
    const component = TestBed.createComponent(DashboardComponent).componentInstance;

    expect(component.fileTypeLabel('app')).toBe('APP');
    expect(component.fileTypeLabel('verylongextension')).toBe('VERY');
    expect(component.fileTypeLabel('')).toBe('FILE');
  });

  it('uses the same 12-item page size in Recent and Starred', () => {
    const component = TestBed.createComponent(DashboardComponent).componentInstance;

    component.viewMode.set('recent');
    component.totalItems.set(17);
    expect(component.pageSize).toBe(12);
    expect(component.pageCount()).toBe(2);

    component.viewMode.set('starred');
    expect(component.pageSize).toBe(12);
  });

  it('does not navigate outside the available pages', async () => {
    const component = TestBed.createComponent(DashboardComponent).componentInstance;
    component.totalItems.set(12);
    const refresh = vi.spyOn(component, 'refresh').mockResolvedValue();

    await component.changePage(2);
    await component.changePage(0);

    expect(component.page()).toBe(1);
    expect(refresh).not.toHaveBeenCalled();
  });

  it('opens and closes the mobile navigation', () => {
    const component = TestBed.createComponent(DashboardComponent).componentInstance;

    component.toggleMobileNav();
    expect(component.isMobileNavOpen()).toBe(true);

    component.onEscape();
    expect(component.isMobileNavOpen()).toBe(false);

    component.toggleMobileNav();
    component.toggleMobileNav();
    expect(component.isMobileNavOpen()).toBe(false);
  });

  it('shows errors in a themed alert dialog and allows dismissal', () => {
    const fixture = TestBed.createComponent(DashboardComponent);
    const component = fixture.componentInstance;
    authMock.user.set({
      id: 42,
      name: 'Test User',
      email: 'test@example.com',
      storage_quota: 1000,
      used_bytes: 0,
    });
    vi.spyOn(component, 'refresh').mockResolvedValue();
    component.error.set('Files must be 500 MB or smaller.');
    fixture.detectChanges();

    const alert = fixture.nativeElement.querySelector('[role="alertdialog"]');
    expect(alert).not.toBeNull();
    expect(alert.textContent).toContain('Files must be 500 MB or smaller.');
    expect(alert.textContent).toContain('This file is too large');

    component.onEscape();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role="alertdialog"]')).toBeNull();
  });

  it('provides a specific title and next step for API connection errors', () => {
    const component = TestBed.createComponent(DashboardComponent).componentInstance;
    component.error.set("Couldn't connect to CloudVault. Check your internet connection and confirm the server is available.");

    expect(component.errorTitle()).toBe('CloudVault is unreachable');
    expect(component.errorGuidance()).toContain('confirm the CloudVault server is online');
  });

  it('creates a fresh shared URL and keeps it visible when clipboard access is unavailable', async () => {
    const component = TestBed.createComponent(DashboardComponent).componentInstance;
    const share = {
      id: 12,
      file_id: 25,
      original_name: 'Quarterly report.pdf',
      permission: 'download' as const,
      expires_at: '2026-11-18T11:16:00Z',
      revoked_at: null,
      created_at: '2026-11-11T11:16:00Z',
    };
    apiMock.regenerateShareLink.mockResolvedValue({ ...share, token: 'fresh-token' });

    await component.regenerateAndCopyShareLink(share);

    expect(apiMock.regenerateShareLink).toHaveBeenCalledWith(12);
    expect(component.shareLinks().get(12)).toBe(
      'https://cloudvault.example/api/public/share/fresh-token/content',
    );
    expect(component.shareLinkStatus()?.shareId).toBe(12);
  });

  it('loads filenames for shared links from older API responses', async () => {
    const component = TestBed.createComponent(DashboardComponent).componentInstance;
    apiMock.listShares.mockResolvedValue([{
      id: 8,
      file_id: 25,
      permission: 'download',
      expires_at: '2026-11-18T11:16:00Z',
      revoked_at: null,
      created_at: '2026-11-11T11:16:00Z',
    }]);
    apiMock.getFile.mockResolvedValue({ original_name: 'Counter-Strike 2.zip' });

    await component.loadShares();

    expect(apiMock.getFile).toHaveBeenCalledWith(25);
    expect(component.shares()[0].original_name).toBe('Counter-Strike 2.zip');
  });

  it('explains upload size errors with a clear next step', () => {
    const component = TestBed.createComponent(DashboardComponent).componentInstance;
    component.error.set('Files must be 500 MB or smaller.');

    expect(component.errorTitle()).toBe('This file is too large');
    expect(component.errorGuidance()).toBe('Choose a file smaller than 500 MB.');
  });

  it('limits each page to 12 cards across folders and files', async () => {
    const component = TestBed.createComponent(DashboardComponent).componentInstance;
    component.totalItems.set(25);
    component.allContents.set({
      id: 0,
      name: 'My files',
      parent_id: null,
      created_at: '2026-11-10T00:00:00Z',
      breadcrumbs: [],
      folders: Array.from({ length: 16 }, (_, id) => ({
        id: id + 1,
        name: `Folder ${id + 1}`,
        parent_id: null,
        created_at: '2026-11-10T00:00:00Z',
      })),
      files: Array.from({ length: 9 }, (_, id) => ({
        id: id + 1,
        original_name: `file-${id + 1}.txt`,
        size: 12,
        mime_type: 'text/plain',
        extension: 'txt',
        folder_id: null,
        checksum: 'checksum',
        created_at: '2026-11-10T00:00:00Z',
        updated_at: '2026-11-10T00:00:00Z',
      })),
      total: 25,
    });

    await component.changePage(2);

    expect(component.contents()?.folders).toHaveLength(4);
    expect(component.contents()?.files).toHaveLength(8);
    expect((component.contents()?.folders.length ?? 0) + (component.contents()?.files.length ?? 0)).toBe(12);
  });

  it('opens the containing folder and page for a file selected in the sidebar', async () => {
    const component = TestBed.createComponent(DashboardComponent).componentInstance;
    const targetFile = {
      id: 3,
      original_name: 'umer.txt',
      size: 12,
      mime_type: 'text/plain',
      extension: 'txt',
      folder_id: 8,
      checksum: 'checksum',
      created_at: '2026-11-10T00:00:00Z',
      updated_at: '2026-11-10T00:00:00Z',
    };
    const contents = {
      id: 8,
      name: 'Folder 8',
      parent_id: null,
      created_at: '2026-11-10T00:00:00Z',
      breadcrumbs: [],
      folders: Array.from({ length: 11 }, (_, id) => ({
        id: id + 1,
        name: `Subfolder ${id + 1}`,
        parent_id: 8,
        created_at: '2026-11-10T00:00:00Z',
      })),
      files: [
        { ...targetFile, id: 1, original_name: 'first.txt' },
        { ...targetFile, id: 2, original_name: 'second.txt' },
        targetFile,
        { ...targetFile, id: 4, original_name: 'fourth.txt' },
      ],
      total: 4,
    };
    vi.spyOn(component, 'refresh').mockImplementation(async () => {
      component.allContents.set(contents);
    });

    await component.openFileLocation(targetFile);

    expect(component.viewMode()).toBe('all');
    expect(component.page()).toBe(2);
    expect(component.contents()?.files).toContainEqual(targetFile);
    expect(component.contents()?.folders).toHaveLength(0);
  });

  it('persists starred files for the signed-in user', () => {
    const fixture = TestBed.createComponent(DashboardComponent);
    const component = fixture.componentInstance;
    vi.spyOn(component, 'refresh').mockResolvedValue();
    authMock.user.set({
      id: 42,
      name: 'Test User',
      email: 'test@example.com',
      storage_quota: 1000,
      used_bytes: 0,
    });
    fixture.detectChanges();

    const file = {
      id: 7,
      original_name: 'notes.txt',
      size: 12,
      mime_type: 'text/plain',
      extension: 'txt',
      folder_id: null,
      checksum: 'checksum',
      created_at: '2026-11-10T00:00:00Z',
      updated_at: '2026-11-10T00:00:00Z',
    };
    const storageKey = 'cloudvault_starred_42';
    localStorage.removeItem(storageKey);

    component.toggleStar(file);
    expect(component.isStarred(file)).toBe(true);
    expect(JSON.parse(localStorage.getItem(storageKey) ?? '[]')).toEqual([7]);

    component.toggleStar(file);
    expect(component.isStarred(file)).toBe(false);
    expect(JSON.parse(localStorage.getItem(storageKey) ?? '[]')).toEqual([]);
    localStorage.removeItem(storageKey);
  });

  it('only signs out after confirmation', () => {
    const component = TestBed.createComponent(DashboardComponent).componentInstance;
    vi.spyOn(window, 'confirm').mockReturnValue(false);

    component.signOut();

    expect(authMock.logout).not.toHaveBeenCalled();
  });

  it('signs out when confirmation is accepted', () => {
    const component = TestBed.createComponent(DashboardComponent).componentInstance;
    vi.spyOn(window, 'confirm').mockReturnValue(true);

    component.signOut();

    expect(authMock.logout).toHaveBeenCalledOnce();
  });
});
