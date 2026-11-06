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
  user: signal(null),
};

describe('DashboardComponent', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
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
    component.totalFiles.set(25);

    expect(component.pageCount()).toBe(3);
    expect(component.hasPreviousPage()).toBe(false);
    expect(component.hasNextPage()).toBe(true);

    component.page.set(3);
    expect(component.hasPreviousPage()).toBe(true);
    expect(component.hasNextPage()).toBe(false);
  });

  it('does not navigate outside the available pages', async () => {
    const component = TestBed.createComponent(DashboardComponent).componentInstance;
    component.totalFiles.set(12);
    const refresh = vi.spyOn(component, 'refresh').mockResolvedValue();

    await component.changePage(2);
    await component.changePage(0);

    expect(component.page()).toBe(1);
    expect(refresh).not.toHaveBeenCalled();
  });
});
