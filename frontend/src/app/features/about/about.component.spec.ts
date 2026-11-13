import { provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { AboutComponent } from './about.component';

describe('AboutComponent', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AboutComponent],
      providers: [provideRouter([])],
    }).compileComponents();
  });

  it('explains CloudVault and provides a sign-in route', () => {
    const fixture = TestBed.createComponent(AboutComponent);
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('h1')?.textContent).toContain('Your files,');
    expect(element.querySelector('a[routerLink="/login"]')?.textContent).toContain('Sign in');
    expect(element.querySelector('#how-it-works')).not.toBeNull();
  });
});
