def notifications(request):
    if not request.user.is_authenticated:
        return {}
    items = request.user.notifications.filter(is_read=False)[:5]
    return {"recent_notifications": items, "unread_notifications": request.user.notifications.filter(is_read=False).count()}
