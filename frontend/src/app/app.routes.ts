import { Routes } from '@angular/router';
import { PublicShareComponent } from './features/public-share/public-share.component';

export const routes: Routes = [
  { path: 'share/:token', component: PublicShareComponent },
];
