async def handle_user_profile(request):
    try:
        return await _handle_user_profile_impl(request)
    except Exception as e:
        logger.error(f"Profile Page Crash: {e}", exc_info=True)
        return web.Response(text=f"Server Error (Logged): {e}", status=500)

