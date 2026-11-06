export type User = {
  id: number;
  name: string;
  email: string;
  storage_quota: number;
  used_bytes: number;
};

export type Folder = {
  id: number;
  name: string;
  parent_id: number | null;
};

export type FileRecord = {
  id: number;
  original_name: string;
  size: number;
  mime_type: string;
  extension: string;
  folder_id: number | null;
  created_at: string;
};

export type Usage = {
  used_bytes: number;
  quota_bytes: number;
  remaining_bytes: number;
  percent_used: number;
};

export type FolderContents = {
  id: number;
  name: string;
  parent_id: number | null;
  breadcrumbs: Folder[];
  folders: Folder[];
  files: FileRecord[];
  total: number;
};

export type FileList = {
  items: FileRecord[];
  total: number;
  limit: number;
  offset: number;
};

export type Share = {
  id: number;
  file_id: number;
  permission: 'view' | 'download';
  expires_at: string;
  revoked_at: string | null;
  created_at: string;
};

export type CreatedShare = Share & {
  token: string;
};
