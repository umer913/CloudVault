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

    expect(component.pageSize).toBe(4);
    expect(component.pageCount()).toBe(7);
    expect(component.hasPreviousPage()).toBe(false);
    expect(component.hasNextPage()).toBe(true);

    component.page.set(7);
    expect(component.hasPreviousPage()).toBe(true);
    expect(component.hasNextPage()).toBe(false);
  });

  it('allows eight files per page in Recent and Starred', () => {
    const component = TestBed.createComponent(DashboardComponent).componentInstance;

    component.viewMode.set('recent');
    component.totalItems.set(17);
    expect(component.pageSize).toBe(8);
    expect(component.pageCount()).toBe(3);

    component.viewMode.set('starred');
    expect(component.pageSize).toBe(8);
  });

  it('does not navigate outside the available pages', async () => {
    const component = TestBed.createComponent(DashboardComponent).componentInstance;
    component.totalItems.set(4);
    const refresh = vi.spyOn(component, 'refresh').mockResolvedValue();

    await component.changePage(2);
    await component.changePage(0);

    expect(component.page()).toBe(1);
    expect(refresh).not.toHaveBeenCalled();
  });

  it('limits each page to four cards across folders and files', async () => {
    const component = TestBed.createComponent(DashboardComponent).componentInstance;
    component.totalItems.set(9);
    component.allContents.set({
      id: 0,
      name: 'My files',
      parent_id: null,
      created_at: '2026-11-10T00:00:00Z',
      breadcrumbs: [],
      folders: Array.from({ length: 5 }, (_, id) => ({
        id: id + 1,
        name: `Folder ${id + 1}`,
        parent_id: null,
        created_at: '2026-11-10T00:00:00Z',
      })),
      files: Array.from({ length: 4 }, (_, id) => ({
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
      total: 4,
    });

    await component.changePage(2);

    expect(component.contents()?.folders).toHaveLength(1);
    expect(component.contents()?.files).toHaveLength(3);
    expect((component.contents()?.folders.length ?? 0) + (component.contents()?.files.length ?? 0)).toBe(4);
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
      folders: Array.from({ length: 5 }, (_, id) => ({
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
    expect(component.contents()?.folders).toHaveLength(1);
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
