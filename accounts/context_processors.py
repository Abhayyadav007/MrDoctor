from django.conf import settings


def oauth_providers(request):
    google_apps = settings.SOCIALACCOUNT_PROVIDERS.get("google", {}).get("APPS", [])
    return {"google_oauth_enabled": bool(google_apps and google_apps[0].get("client_id"))}
