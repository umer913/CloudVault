import { Injectable, inject, signal } from '@angular/core';
import { ApiService } from '../api/api.service';
import { User } from '../models/api.models';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly api = inject(ApiService);
  readonly user = signal<User | null>(null);
  readonly isLoading = signal(true);
  readonly isBusy = signal(false);

  constructor() {
    const token = localStorage.getItem('cloudvault_token');
    if (!token) {
      this.isLoading.set(false);
      return;
    }
    this.api.user()
      .then((user) => this.user.set(user))
      .catch(() => this.logout())
      .finally(() => this.isLoading.set(false));
  }

  async login(email: string, password: string) {
    this.isBusy.set(true);
    try {
      const result = await this.api.login(email, password);
      localStorage.setItem('cloudvault_token', result.access_token);
      this.user.set(await this.api.user());
    } finally {
      this.isBusy.set(false);
    }
  }

  async register(name: string, email: string, password: string) {
    this.isBusy.set(true);
    try {
      await this.api.register(name, email, password);
      const result = await this.api.login(email, password);
      localStorage.setItem('cloudvault_token', result.access_token);
      this.user.set(await this.api.user());
    } finally {
      this.isBusy.set(false);
    }
  }

  logout() {
    localStorage.removeItem('cloudvault_token');
    this.user.set(null);
    this.isLoading.set(false);
  }
}
