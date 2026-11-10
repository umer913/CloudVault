import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService, getApiErrorMessage } from '../../core/api/api.service';
import { AuthService } from '../../core/auth/auth.service';

@Component({
  selector: 'app-auth-page',
  imports: [FormsModule],
  templateUrl: './auth-page.component.html',
  styleUrl: './auth-page.component.scss',
})
export class AuthPageComponent {
  readonly auth = inject(AuthService);
  private readonly api = inject(ApiService);
  readonly mode = signal<'login' | 'register'>('login');
  readonly error = signal('');
  readonly success = signal('');
  readonly submitting = signal(false);
  name = '';
  email = '';
  password = '';

  toggleMode() {
    this.mode.update((mode) => mode === 'login' ? 'register' : 'login');
    this.name = '';
    this.email = '';
    this.password = '';
    this.error.set('');
    this.success.set('');
  }

  async submit() {
    if (this.submitting()) return;
    this.error.set('');
    this.success.set('');
    this.submitting.set(true);
    try {
      if (this.mode() === 'login') await this.auth.login(this.email, this.password);
      else {
        await this.auth.register(this.name, this.email, this.password);
        this.mode.set('login');
        this.name = '';
        this.email = '';
        this.password = '';
        this.success.set('Account created. Please sign in.');
      }
    } catch (error) {
      this.error.set(getApiErrorMessage(error, 'Unable to continue.'));
    } finally {
      this.submitting.set(false);
    }
  }
}
