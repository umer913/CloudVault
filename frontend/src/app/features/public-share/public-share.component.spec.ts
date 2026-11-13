import { HttpErrorResponse } from '@angular/common/http';
import { convertToParamMap } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { ApiService } from '../../core/api/api.service';
import { ActivatedRoute } from '@angular/router';
import { PublicShareComponent } from './public-share.component';

const apiMock = {
  getPublicShare: vi.fn(),
  getPublicShareContent: vi.fn(),
};

describe('PublicShareComponent', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    apiMock.getPublicShare.mockRejectedValue(new HttpErrorResponse({
      status: 401,
      error: { code: 'PASSWORD_REQUIRED', message: 'A valid share password is required.' },
    }));
    await TestBed.configureTestingModule({
      imports: [PublicShareComponent],
      providers: [
        { provide: ApiService, useValue: apiMock },
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: convertToParamMap({ token: 'share-token' }) } },
        },
      ],
    }).compileComponents();
  });

  it('prompts for the share password and unlocks with the entered password', async () => {
    const fixture = TestBed.createComponent(PublicShareComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Password-protected file');
    expect(fixture.nativeElement.querySelector('input[type="password"]')).not.toBeNull();

    apiMock.getPublicShare.mockResolvedValue({
      file_id: 7,
      original_name: 'report.pdf',
      size: 1024,
      mime_type: 'application/pdf',
      permission: 'download',
      expires_at: '2026-11-18T00:00:00Z',
      password_required: true,
    });
    fixture.componentInstance.password = 'correct-password';
    await fixture.componentInstance.submitPassword();
    fixture.detectChanges();

    expect(apiMock.getPublicShare).toHaveBeenLastCalledWith('share-token', 'correct-password');
    expect(fixture.nativeElement.textContent).toContain('report.pdf');
    expect(fixture.nativeElement.textContent).toContain('Download file');
  });

  it('shows an error when the password is rejected', async () => {
    const fixture = TestBed.createComponent(PublicShareComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.componentInstance.password = 'wrong-password';

    await fixture.componentInstance.submitPassword();
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('That password did not match.');
  });

  it('renders image previews as contained images instead of browser-native iframe previews', async () => {
    const fixture = TestBed.createComponent(PublicShareComponent);
    fixture.detectChanges();
    await fixture.whenStable();

    fixture.componentInstance.share.set({
      file_id: 7,
      original_name: 'photo.png',
      size: 1024,
      mime_type: 'image/png',
      permission: 'view',
      expires_at: '2026-11-18T00:00:00Z',
      password_required: false,
    });
    fixture.componentInstance.imagePreviewUrl.set('blob:preview');
    fixture.detectChanges();

    const image = fixture.nativeElement.querySelector('.share-image-preview');
    expect(image.getAttribute('src')).toBe('blob:preview');
    expect(image.getAttribute('alt')).toBe('Preview of photo.png');
    expect(fixture.nativeElement.querySelector('iframe')).toBeNull();
  });
});
