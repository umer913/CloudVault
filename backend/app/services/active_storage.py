from app.config import settings
from app.services.b2_storage_service import B2Storage
from app.services.supabase_storage_service import SupabaseStorage


def create_storage():
    if settings.STORAGE_PROVIDER == "b2":
        return B2Storage()
    if settings.STORAGE_PROVIDER == "supabase":
        return SupabaseStorage()
    raise ValueError("STORAGE_PROVIDER must be 'supabase' or 'b2'.")
