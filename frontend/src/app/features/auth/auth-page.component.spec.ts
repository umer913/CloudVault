import { TestBed } from '@angular/core/testing';
import { ApiService } from '../../core/api/api.service';
import { AuthService } from '../../core/auth/auth.service';
import { AuthPageComponent } from './auth-page.component';

const authMock = {
  login: vi.fn(),
  register: vi.fn(),
};

describe('AuthPageComponent', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    authMock.register.mockResolvedValue(undefined);
    await TestBed.configureTestingModule({
      imports: [AuthPageComponent],
      providers: [
        { provide: AuthService, useValue: authMock },
        { provide: ApiService, useValue: {} },
      ],
    }).compileComponents();
  });

  it('clears credentials when switching between login and signup', () => {
    const component = TestBed.createComponent(AuthPageComponent).componentInstance;
    component.name = 'Example User';
    component.email = 'example@example.com';
    component.password = 'password123';

    component.toggleMode();

    expect(component.mode()).toBe('register');
    expect(component.name).toBe('');
    expect(component.email).toBe('');
    expect(component.password).toBe('');
  });

  it('returns to login after registration without logging in automatically', async () => {
    const component = TestBed.createComponent(AuthPageComponent).componentInstance;
    component.mode.set('register');
    component.name = 'Example User';
    component.email = 'example@example.com';
    component.password = 'password123';

    await component.submit();

    expect(authMock.register).toHaveBeenCalledWith(
      'Example User',
      'example@example.com',
      'password123',
    );
    expect(authMock.login).not.toHaveBeenCalled();
    expect(component.mode()).toBe('login');
    expect(component.success()).toBe('Account created. Please sign in.');
    expect(component.password).toBe('');
  });
});
