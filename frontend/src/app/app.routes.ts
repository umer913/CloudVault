import { Routes } from '@angular/router';
import { AboutComponent } from './features/about/about.component';
import { AuthPageComponent } from './features/auth/auth-page.component';
import { PublicShareComponent } from './features/public-share/public-share.component';

export const routes: Routes = [
  { path: '', component: AboutComponent, pathMatch: 'full' },
  { path: 'login', component: AuthPageComponent },
  { path: 'share/:token', component: PublicShareComponent },
  { path: '**', redirectTo: '' },
];
