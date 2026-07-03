"""
URL configuration for defense_scheduler project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.conf import settings
from django.http import Http404, HttpResponse
from django.urls import include, path, re_path
from django.utils._os import safe_join
from pathlib import Path
import mimetypes


def frontend_index(_request):
    index_path = settings.FRONTEND_DIST_DIR / 'index.html'
    if not index_path.exists():
        raise Http404('Frontend build not found. Run npm run build first.')
    return HttpResponse(index_path.read_bytes(), content_type='text/html')


def frontend_asset(_request, path):
    try:
        asset_path = Path(safe_join(settings.FRONTEND_DIST_DIR / 'assets', path))
    except ValueError as exc:
        raise Http404('Asset not found.') from exc
    if not asset_path.exists() or not asset_path.is_file():
        raise Http404('Asset not found.')
    content_type = mimetypes.guess_type(asset_path.name)[0] or 'application/octet-stream'
    return HttpResponse(asset_path.read_bytes(), content_type=content_type)


def frontend_public_file(_request, path):
    try:
        file_path = Path(safe_join(settings.FRONTEND_DIST_DIR, path))
    except ValueError as exc:
        raise Http404('Frontend file not found.') from exc
    if not file_path.exists() or not file_path.is_file():
        raise Http404('Frontend file not found.')
    content_type = mimetypes.guess_type(file_path.name)[0] or 'application/octet-stream'
    return HttpResponse(file_path.read_bytes(), content_type=content_type)


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
    re_path(r'^assets/(?P<path>.*)$', frontend_asset),
    re_path(r'^(?P<path>favicon\.svg)$', frontend_public_file),
    path('', frontend_index),
    re_path(r'^(?!api/|admin/|assets/).*$', frontend_index),
]
