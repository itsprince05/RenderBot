import asyncio
from aiohttp import web
import logging
from telethon import utils
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

def format_bytes(size):
    size = float(size)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"

async def handle_chat_page(request):
    try:
        user_id = int(request.match_info.get('user_id'))
        peer_id_str = request.match_info.get('peer_id')
        peer_id = int(peer_id_str) if peer_id_str.lstrip('-').isdigit() else peer_id_str
        
        active_sessions = request.app['active_sessions']
        session = active_sessions.get(user_id)
        
        if not session or not session.client or not session.client.is_connected():
            return web.Response(text="Session not found or disconnected", status=404)
            
        entity = await session.client.get_entity(peer_id)
        name = utils.get_display_name(entity) or "Unknown"
        name_initial = name[0].upper() if name else '?'

        # Build status subtitle
        entity_type = type(entity).__name__
        status_text = ""
        try:
            is_bot = getattr(entity, 'bot', False)
            if entity_type == 'User' and not is_bot:
                user_status = getattr(entity, 'status', None)
                status_type = type(user_status).__name__ if user_status else ''
                if status_type == 'UserStatusOnline':
                    status_text = "online"
                elif status_type == 'UserStatusRecently':
                    status_text = "last seen recently"
                elif status_type == 'UserStatusLastWeek':
                    status_text = "last seen within a week"
                elif status_type == 'UserStatusLastMonth':
                    status_text = "last seen within a month"
                elif status_type == 'UserStatusOffline':
                    was_online = getattr(user_status, 'was_online', None)
                    if was_online:
                        now_ist = datetime.utcnow() + timedelta(hours=5, minutes=30)
                        dt_ist = was_online + timedelta(hours=5, minutes=30)
                        
                        date_now = now_ist.date()
                        date_dt = dt_ist.date()
                        time_str = dt_ist.strftime("%I:%M %p").lstrip("0")
                        
                        if date_dt == date_now:
                            status_text = f"last seen at {time_str}"
                        elif date_dt == date_now - timedelta(days=1):
                            status_text = f"last seen yesterday at {time_str}"
                        elif date_dt.year == date_now.year:
                            month_str = dt_ist.strftime("%b")
                            status_text = f"last seen {month_str} {dt_ist.day} at {time_str}"
                        else:
                            month_str = dt_ist.strftime("%b")
                            status_text = f"last seen {month_str} {dt_ist.day}, {dt_ist.year} at {time_str}"
                    else:
                        status_text = "last seen a long time ago"
                elif status_type == 'UserStatusEmpty' or not status_type:
                    status_text = "last seen a long time ago"
            
            elif is_bot:
                status_text = "bot"
                try:
                    from telethon.tl.functions.users import GetFullUserRequest
                    full_res = await session.client(GetFullUserRequest(entity))
                    d = full_res.full_user.to_dict()
                    users_count = None
                    if 'bot_active_users' in d: users_count = d['bot_active_users']
                    elif 'bot_info' in d and 'monthly_active_users' in d['bot_info']: users_count = d['bot_info']['monthly_active_users']
                    elif hasattr(full_res.full_user, 'bot_active_users'): users_count = full_res.full_user.bot_active_users
                    if users_count:
                        status_text = f"{int(users_count):,} monthly users"
                except Exception:
                    pass
            
            elif entity_type in ('Chat', 'Channel'):
                is_channel = getattr(entity, 'broadcast', False)
                count = getattr(entity, 'participants_count', 0)
                online_count = 0
                
                try:
                    if is_channel or getattr(entity, 'megagroup', False):
                        from telethon.tl.functions.channels import GetFullChannelRequest
                        full = await session.client(GetFullChannelRequest(entity))
                        fc = full.full_chat
                        if hasattr(fc, 'participants_count') and fc.participants_count:
                            count = fc.participants_count
                        if hasattr(fc, 'online_count') and fc.online_count:
                            online_count = fc.online_count
                    else:
                        from telethon.tl.functions.messages import GetFullChatRequest
                        full = await session.client(GetFullChatRequest(peer_id))
                        fc = full.full_chat
                        count = getattr(fc, 'participants_count', count)
                        users = full.users
                        if users:
                            count = len(users)
                            online_count = sum(1 for u in users if type(getattr(u, 'status', None)).__name__ == 'UserStatusOnline')
                except Exception:
                    pass

                if is_channel:
                    if count:
                        status_text = f"{count:,} subscribers"
                    else:
                        status_text = "channel"
                else: 
                    if count and online_count > 0:
                        status_text = f"{count:,} members {online_count:,} online"
                    elif count:
                        status_text = f"{count:,} members"
                    else:
                        status_text = "group"
        except Exception:
            status_text = ""
        voice_icon = ""
        # Only show if group/channel and has active call
        if getattr(entity, 'call_active', False):
            voice_icon = f"""<a href="/user/{user_id}/vc/{peer_id}" target="_blank" style="color: white; background: rgba(255,255,255,0.15); width: 34px; height: 34px; border-radius: 50%; display: flex; align-items: center; justify-content: center; cursor: pointer; flex-shrink: 0; position: relative; z-index: 1000; text-decoration: none;" title="Voice Chat">
                        <svg style="pointer-events: none;" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 10v3"/><path d="M6 6v11"/><path d="M10 3v18"/><path d="M14 8v7"/><path d="M18 5v13"/><path d="M22 10v3"/></svg>
                    </a>"""
        
        html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
            <title>Chat - {name}</title>
            <script src="https://unpkg.com/@lottiefiles/lottie-player@latest/dist/lottie-player.js"></script>
            <style>
                :root {{
                    --bg-color: #f0f2f5;
                    --primary: #3390ec;
                    --text-main: #000000;
                    --text-muted: #707579;
                    --msg-in: #ffffff;
                    --msg-out: #eeffde;
                    --msg-time: #687b8f;
                    --msg-time-out: #4caf50;
                    --header-bg: #ffffff;
                    --border: #dfdfdf;
                    --surface-hover: #f4f4f5;
                }}
                body {{
                    margin: 0; padding: 0;
                    font-family: -apple-system, BlinkMacSystemFont, "Roboto", "Segoe UI", "Helvetica Neue", Arial, sans-serif;
                    background: var(--bg-color);
                    color: var(--text-main);
                    height: 100vh;
                    height: 100dvh;
                    display: flex;
                    flex-direction: column;
                    overflow: hidden;
                    position: relative;
                }}
                .chat-bg {{
                    position: absolute; top: 0; left: 0; width: 100%; height: 100%; z-index: -1;
                    background-image: url('https://web.telegram.org/a/chat-bg-pattern-light.png');
                    background-size: 400px;
                    opacity: 0.4;
                    mix-blend-mode: overlay;
                }}
                .action-bar {{
                    position: sticky; top: 0; z-index: 100; height: 56px;
                    background: #2481cc;
                    display: flex; align-items: center; padding: 0 10px; gap: 10px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.2);
                    box-sizing: border-box;
                    width: 100%;
                }}
                .back-btn {{
                    background: rgba(255,255,255,0.15); border: none; color: white; width: 34px; height: 34px; border-radius: 50%; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: background 0.15s; outline: none; flex-shrink: 0; padding: 0;
                }}
                .back-btn:hover {{ background: rgba(255,255,255,0.25); }}
                .back-btn svg {{ width: 18px; height: 18px; }}
                .avatar {{ width: 42px; height: 42px; border-radius: 50%; object-fit: cover; background: #eee; flex-shrink: 0; border: 1.5px solid rgba(255,255,255,0.5); }}
                .user-info {{ flex: 1; min-width: 0; display: flex; flex-direction: column; justify-content: center; height: 100%; }}
                .user-title {{ font-size: 16px; font-weight: 600; text-overflow: ellipsis; overflow: hidden; white-space: nowrap; line-height: 1.2; color: white; }}
                .user-status {{ font-size: 13px; color: rgba(255,255,255,0.75); line-height: 1.2; margin-top: 1px; text-overflow: ellipsis; overflow: hidden; white-space: nowrap; }}
                .header-actions {{ display: flex; align-items: center; gap: 12px; }}
                
                .chat-scroll-area {{
                    flex: 1; overflow-y: auto; overflow-x: hidden; position: relative;
                    display: flex; flex-direction: column; align-items: center;
                }}
                ::-webkit-scrollbar {{ width: 5px; }}
                ::-webkit-scrollbar-thumb {{ background: rgba(0,0,0,0.2); border-radius: 5px; }}
                ::-webkit-scrollbar-thumb:hover {{ background: rgba(0,0,0,0.3); }}
                
                .chat-container {{ width: 100%; max-width: 728px; display: flex; flex-direction: column; padding: 0 16px; box-sizing: border-box; margin-top: auto; }}
                
                .message-wrapper {{ width: 100%; display: flex; margin-bottom: 8px; position: relative; animation: fadeIn 0.2s ease-out; }}
                @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(10px); }} to {{ opacity: 1; transform: translateY(0); }} }}
                .message-wrapper.in {{ justify-content: flex-start; }}
                .message-wrapper.out {{ justify-content: flex-end; }}
                
                .group-avatar {{ width: 34px; height: 34px; border-radius: 50%; object-fit: cover; margin-right: 12px; flex-shrink: 0; align-self: flex-end; cursor: pointer; }}
                
                .message {{
                    max-width: 75%; min-width: 0; padding: 10px;
                    border-radius: 10px; font-size: 15px; line-height: 1.4; word-wrap: break-word;
                    position: relative; width: fit-content;
                    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
                }}
                .message.in {{ background: var(--msg-in); border-bottom-left-radius: 4px; color: #000; }}
                .message.out {{ background: var(--msg-out); border-bottom-right-radius: 4px; color: #000; }}
                
                .sender-name {{ font-size: 13px; font-weight: 600; margin-bottom: 2px; display: block; line-height: 1.2; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; cursor: pointer; }}
                
                .msg-text {{ white-space: pre-wrap; word-break: break-word; display: inline; }}
                
                .msg-meta {{
                    float: right; margin-left: 14px; margin-top: 4px; margin-bottom: -4px;
                    display: inline-flex; align-items: center; gap: 4px;
                    font-size: 11px; line-height: 1; color: var(--msg-time); 
                    white-space: nowrap;
                }}
                .message.out .msg-meta {{ color: var(--msg-time-out); }}
                
                .system-message {{
                    align-self: center; background: rgba(0,0,0,0.15); color: white;
                    padding: 4px 12px; border-radius: 12px; font-size: 13px; font-weight: 500;
                    margin: 0; text-align: center; max-width: 90%;
                    display: inline-block; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
                }}
                
                .media-preview {{ max-width: 100%; border-radius: 10px; margin-bottom: 6px; display: block; }}
                .reply-box {{
                    border-left: 2px solid var(--primary); padding-left: 10px; margin-bottom: 8px;
                    font-size: 13px; color: #555; background: rgba(51, 144, 236, 0.1); border-radius: 0 6px 6px 0;
                    padding-top: 6px; padding-bottom: 6px; cursor: pointer; max-width: 100%; overflow: hidden;
                    position: relative;
                }}
                .reply-box:hover {{ background: rgba(51, 144, 236, 0.15); }}
                .reply-title {{ color: var(--primary); font-weight: 600; margin-bottom: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
                .reply-text {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--text-muted); }}
                
                .loader {{ position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); color: var(--primary); font-size: 14px; text-align: center; }}
                .spinner-svg {{ width: 32px; height: 32px; animation: spin 1s linear infinite; }}
                @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
                
                .highlight-msg {{ animation: highlight 2s ease-out; }}
                @keyframes highlight {{ 0% {{ background-color: rgba(51, 144, 236, 0.4); }} 100% {{ background-color: var(--msg-in); }} }}
                .highlight-msg.out {{ animation: highlightOut 2s ease-out; }}
                @keyframes highlightOut {{ 0% {{ background-color: rgba(51, 144, 236, 0.4); }} 100% {{ background-color: var(--msg-out); }} }}
                
                .fab-btn {{
                    position: fixed;
                    bottom: 15px;
                    right: 15px;
                    width: 34px;
                    height: 34px;
                    background: #f2f2f2;
                    color: #3390ec;
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    cursor: pointer;
                    box-shadow: 0 2px 6px rgba(0,0,0,0.3);
                    z-index: 1000;
                    transition: transform 0.2s, opacity 0.2s;
                    opacity: 0;
                    pointer-events: none;
                }}
                .fab-btn.visible {{
                    opacity: 1;
                    pointer-events: auto;
                }}
                .fab-btn:active {{ transform: scale(0.9); }}
                .fab-btn svg {{ width: 18px; height: 18px; }}
            </style>
            <script>
                let isLoading = false;
                let minMsgId = null;
                let maxMsgId = null;
                let hasMore = true;
                let hasMoreDown = true;
                const storageKey = 'chat_data_' + {user_id} + '_' + {peer_id};

                function updateMsgIds() {{
                    const msgs = Array.from(document.querySelectorAll('[id^="msg-"]'));
                    if (msgs.length > 0) {{
                        minMsgId = Math.min(...msgs.map(m => parseInt(m.id.replace('msg-', ''))));
                        maxMsgId = Math.max(...msgs.map(m => parseInt(m.id.replace('msg-', ''))));
                    }}
                }}

                function saveState() {{
                    const scrollArea = document.getElementById('chat-scroll-area');
                    localStorage.setItem(storageKey, JSON.stringify({{
                        html: document.getElementById('chat-container').innerHTML,
                        minMsgId: minMsgId,
                        maxMsgId: maxMsgId,
                        scrollTop: scrollArea ? scrollArea.scrollTop : 0,
                        ts: Date.now()
                    }}));
                }}

                function saveScrollOnly() {{
                    const scrollArea = document.getElementById('chat-scroll-area');
                    const cached = localStorage.getItem(storageKey);
                    if (cached) {{
                        const data = JSON.parse(cached);
                        data.scrollTop = scrollArea.scrollTop;
                        localStorage.setItem(storageKey, JSON.stringify(data));
                    }}
                }}

                async function loadMessages() {{
                    const cached = localStorage.getItem(storageKey);
                    if (cached) {{
                        const data = JSON.parse(cached);
                        if (Date.now() - data.ts < 3600000) {{ // 1 hour cache
                            document.getElementById('chat-container').innerHTML = data.html;
                            minMsgId = data.minMsgId;
                            maxMsgId = data.maxMsgId || null;
                            const scrollArea = document.getElementById('chat-scroll-area');
                            scrollArea.scrollTop = data.scrollTop;
                            scrollArea.addEventListener('scroll', handleScroll);
                            checkFab();
                            return;
                        }}
                    }}
                    try {{
                        isLoading = true;
                        const res = await fetch(`/api/user/{user_id}/chat/{peer_id}/messages`);
                        if(res.ok) {{
                            const html = await res.text();
                            const container = document.getElementById('chat-container');
                            container.innerHTML = html;
                            updateMsgIds();
                            
                            const scrollArea = document.getElementById('chat-scroll-area');
                            
                            const boundary = document.getElementById('unread-boundary');
                            if (boundary) {{
                                boundary.scrollIntoView({{block: "center"}});
                            }} else {{
                                scrollArea.scrollTop = scrollArea.scrollHeight;
                            }}
                            
                            saveState();
                            scrollArea.addEventListener('scroll', handleScroll);
                            checkFab();
                        }} else {{
                            document.getElementById('chat-container').innerHTML = '<div class="loader">Failed to load messages</div>';
                        }}
                    }} catch(e) {{
                        document.getElementById('chat-container').innerHTML = '<div class="loader">Error loading messages</div>';
                    }} finally {{
                        isLoading = false;
                    }}
                }}
                
                async function loadOldMessages() {{
                    if (isLoading || !hasMore || !minMsgId) return;
                    try {{
                        isLoading = true;
                        const scrollArea = document.getElementById('chat-scroll-area');
                        const container = document.getElementById('chat-container');
                        
                        const loaderWrap = document.createElement('div');
                        loaderWrap.id = 'top-loader';
                        loaderWrap.style = "width:100%;text-align:center;padding:12px 0;color:var(--primary);";
                        loaderWrap.innerHTML = '<svg class="spinner-svg" style="width:24px;height:24px;" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v4"/><path d="m16.2 7.8 2.9-2.9"/><path d="M18 12h4"/><path d="m16.2 16.2 2.9 2.9"/><path d="M12 18v4"/><path d="m4.9 19.1 2.9-2.9"/><path d="M2 12h4"/><path d="m4.9 4.9 2.9 2.9"/></svg>';
                        container.prepend(loaderWrap);
                        
                        const oldScrollHeight = scrollArea.scrollHeight;
                        const currentScrollTop = scrollArea.scrollTop;
                        
                        const res = await fetch(`/api/user/{user_id}/chat/{peer_id}/messages?offset_id=${{minMsgId}}`);
                        if(res.ok) {{
                            const html = await res.text();
                            const topLoader = document.getElementById('top-loader');
                            if(topLoader) topLoader.remove();
                            
                            if (!html.trim()) {{
                                hasMore = false;
                                return;
                            }}
                            
                            container.insertAdjacentHTML('afterbegin', html);
                            
                            const newScrollHeight = scrollArea.scrollHeight;
                            scrollArea.scrollTop = currentScrollTop + (newScrollHeight - oldScrollHeight);
                            
                            updateMsgIds();
                            saveState();
                        }}
                    }} catch(e) {{
                        const l = document.getElementById('top-loader');
                        if(l) l.remove();
                    }} finally {{
                        isLoading = false;
                    }}
                }}

                async function loadNewMessages() {{
                    if (isLoading || !hasMoreDown || !maxMsgId) return;
                    try {{
                        isLoading = true;
                        const scrollArea = document.getElementById('chat-scroll-area');
                        const container = document.getElementById('chat-container');
                        
                        const loaderWrap = document.createElement('div');
                        loaderWrap.id = 'bottom-loader';
                        loaderWrap.style = "width:100%;text-align:center;padding:12px 0;color:var(--primary);";
                        loaderWrap.innerHTML = '<svg class="spinner-svg" style="width:24px;height:24px;" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v4"/><path d="m16.2 7.8 2.9-2.9"/><path d="M18 12h4"/><path d="m16.2 16.2 2.9 2.9"/><path d="M12 18v4"/><path d="m4.9 19.1 2.9-2.9"/><path d="M2 12h4"/><path d="m4.9 4.9 2.9 2.9"/></svg>';
                        container.appendChild(loaderWrap);
                        
                        const res = await fetch(`/api/user/{user_id}/chat/{peer_id}/messages?min_id=${{maxMsgId}}`);
                        if(res.ok) {{
                            let html = await res.text();
                            const bottomLoader = document.getElementById('bottom-loader');
                            if(bottomLoader) bottomLoader.remove();
                            
                            if (!html.trim()) {{
                                hasMoreDown = false;
                                checkFab();
                                return;
                            }}
                            
                            container.insertAdjacentHTML('beforeend', html);
                            updateMsgIds();
                            saveState();
                            checkFab();
                        }}
                    }} catch(e) {{
                        const l = document.getElementById('bottom-loader');
                        if(l) l.remove();
                    }} finally {{
                        isLoading = false;
                    }}
                }}
                
                function checkFab() {{
                    const scrollArea = document.getElementById('chat-scroll-area');
                    const isAtBottom = scrollArea.scrollHeight - scrollArea.scrollTop - scrollArea.clientHeight < 50;
                    const fab = document.getElementById('fabBtn');
                    if (fab) {{
                        if (!isAtBottom || hasMoreDown) {{
                            fab.classList.add('visible');
                        }} else {{
                            fab.classList.remove('visible');
                        }}
                    }}
                }}

                function handleScroll() {{
                    saveScrollOnly();
                    checkFab();
                    const scrollArea = document.getElementById('chat-scroll-area');
                    if (scrollArea.scrollTop < 100) {{
                        loadOldMessages();
                    }} else if (scrollArea.scrollHeight - scrollArea.scrollTop - scrollArea.clientHeight < 100) {{
                        loadNewMessages();
                    }}
                }}
                
                async function scrollToLatest() {{
                    if (hasMoreDown) {{
                        if(isLoading) return;
                        isLoading = true;
                        hasMoreDown = false;
                        hasMore = true;
                        
                        const container = document.getElementById('chat-container');
                        container.innerHTML = '<div class="loader"><svg class="spinner-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v4"/><path d="m16.2 7.8 2.9-2.9"/><path d="M18 12h4"/><path d="m16.2 16.2 2.9 2.9"/><path d="M12 18v4"/><path d="m4.9 19.1 2.9-2.9"/><path d="M2 12h4"/><path d="m4.9 4.9 2.9 2.9"/></svg></div>';
                        
                        const res = await fetch(`/api/user/{user_id}/chat/{peer_id}/messages?force_latest=1`);
                        isLoading = false;
                        if(res.ok) {{
                            container.innerHTML = await res.text();
                            updateMsgIds();
                            
                            const scrollArea = document.getElementById('chat-scroll-area');
                            scrollArea.scrollTop = scrollArea.scrollHeight;
                            saveState();
                            checkFab();
                        }}
                    }} else {{
                        const scrollArea = document.getElementById('chat-scroll-area');
                        scrollArea.scrollTo({{ top: scrollArea.scrollHeight, behavior: 'smooth' }});
                        checkFab();
                    }}
                }}

                function scrollToMsg(id) {{
                    const el = document.getElementById('msg-' + id);
                    if (el) {{
                        el.scrollIntoView({{behavior: 'smooth', block: 'center'}});
                        el.classList.add('highlight-msg');
                        setTimeout(() => el.classList.remove('highlight-msg'), 2000);
                    }}
                }}
                function goBack() {{
                    if (window.history.length > 1) {{
                        window.history.back();
                    }} else {{
                        window.close();
                    }}
                }}
                window.onload = loadMessages;
                window.addEventListener("beforeunload", saveState);
                document.addEventListener("visibilitychange", function() {{
                    if (document.visibilityState === 'hidden') saveState();
                }});
                function showToast(msg) {{
                const toast = document.createElement('div');
                toast.textContent = msg;
                toast.style.position = 'fixed';
                toast.style.bottom = '20px';
                toast.style.left = '50%';
                toast.style.transform = 'translateX(-50%)';
                toast.style.background = 'rgba(0,0,0,0.8)';
                toast.style.color = 'white';
                toast.style.padding = '8px 16px';
                toast.style.borderRadius = '20px';
                toast.style.fontSize = '14px';
                toast.style.zIndex = '9999';
                toast.style.pointerEvents = 'none';
                toast.style.opacity = '0';
                toast.style.transition = 'opacity 0.3s ease-in-out';
                document.body.appendChild(toast);
                
                // Trigger reflow to animate in
                void toast.offsetWidth;
                toast.style.opacity = '1';
                
                setTimeout(() => {{
                    toast.style.opacity = '0';
                    setTimeout(() => toast.remove(), 300);
                }}, 2000);
            }}
            
            async function copyStickerLink(btn, setId, setHash, shortName) {{
                let originalBg = btn.style.background;
                btn.style.background = 'rgba(0,0,0,0.12)';
                setTimeout(() => btn.style.background = originalBg, 200);
                
                let link = "";
                if (shortName && shortName !== 'None' && shortName !== '') {{
                    link = "https://t.me/addstickers/" + shortName;
                }} else {{
                    const userId = location.pathname.split('/')[2];
                    const res = await fetch(`/api/user/${{userId}}/sticker_link?id=${{setId}}&hash=${{setHash}}`);
                    if (res.ok) {{
                        const sname = await res.text();
                        if (sname && !sname.includes('http')) {{
                            link = "https://t.me/addstickers/" + sname;
                        }} else {{
                            link = sname;
                        }}
                    }}
                }}
                
                if (link) {{
                    const textArea = document.createElement("textarea");
                    textArea.value = link;
                    // Reset all styles to prevent scroll jumps or visibility issues that break execCommand
                    textArea.style.position = "fixed";
                    textArea.style.top = "50%";
                    textArea.style.left = "50%";
                    textArea.style.width = "2em";
                    textArea.style.height = "2em";
                    textArea.style.padding = "0";
                    textArea.style.border = "none";
                    textArea.style.outline = "none";
                    textArea.style.boxShadow = "none";
                    textArea.style.background = "transparent";
                    textArea.style.opacity = "0";
                    document.body.appendChild(textArea);
                    textArea.focus();
                    textArea.select();
                    try {{
                        const successful = document.execCommand('copy');
                        if (successful) {{
                            showToast("Sticker Pack Link Copied");
                        }} else {{
                            window.prompt("Copy link:", link);
                        }}
                    }} catch (err) {{
                        console.error('Fallback copy failed', err);
                        window.prompt("Copy link:", link);
                    }}
                    document.body.removeChild(textArea);
                }} else {{
                    showToast("Could not find link");
                }}
            }}
        </script>
        </head>
        <body>
            <div class="chat-bg"></div>
            <div class="action-bar">
                <button class="back-btn" onclick="goBack()" title="Back">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-arrow-left-icon lucide-arrow-left"><path d="m12 19-7-7 7-7"/><path d="M19 12H5"/></svg>
                </button>
                <a href="/user/{user_id}/info/{peer_id}" target="_blank" style="text-decoration: none; display: flex; align-items: center; flex: 1; min-width: 0; gap: 10px;">
                    <img src="/avatar/{user_id}/{peer_id}" class="avatar" onerror="this.outerHTML='<div class=\\'avatar\\' style=\\'background: rgba(255,255,255,0.2); display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; font-size: 18px; width:42px; height:42px; border-radius:50%; flex-shrink:0; border: 1.5px solid rgba(255,255,255,0.5);\\' >{name_initial}</div>'">
                    <div class="user-info">
                        <div class="user-title">{name}</div>
                        <div class="user-status">{status_text}</div>
                    </div>
                </a>
                <div class="header-actions">
                    {voice_icon}
                </div>
            </div>
            <div class="chat-scroll-area" id="chat-scroll-area">
                <div class="chat-container" id="chat-container">
                    <div class="loader">
                        <svg class="spinner-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v4"/><path d="m16.2 7.8 2.9-2.9"/><path d="M18 12h4"/><path d="m16.2 16.2 2.9 2.9"/><path d="M12 18v4"/><path d="m4.9 19.1 2.9-2.9"/><path d="M2 12h4"/><path d="m4.9 4.9 2.9 2.9"/></svg>
                    </div>
                </div>
            </div>
            
            <div class="fab-btn" id="fabBtn" onclick="scrollToLatest()">
                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-arrow-down-icon lucide-arrow-down"><path d="M12 5v14"/><path d="m19 12-7 7-7-7"/></svg>
            </div>
        </body>
        </html>
        """
        return web.Response(text=html, content_type='text/html')
        
    except Exception as e:
        logger.error(f"Error serving chat page: {e}", exc_info=True)
        return web.Response(text=f"Internal Server Error: {e}", status=500)

async def handle_chat_messages_api(request):
    try:
        user_id = int(request.match_info.get('user_id'))
        peer_id_str = request.match_info.get('peer_id')
        peer_id = int(peer_id_str) if peer_id_str.lstrip('-').isdigit() else peer_id_str
        
        active_sessions = request.app['active_sessions']
        session = active_sessions.get(user_id)
        
        if not session or not session.client or not session.client.is_connected():
            return web.Response(status=404)
            
        try:
            entity = await session.client.get_entity(peer_id)
            is_group = getattr(entity, 'broadcast', False) is False and (hasattr(entity, 'participants_count') or getattr(entity, 'megagroup', False))
        except Exception as e:
            logger.warning(f"Could not fetch entity for {peer_id}: {e}")
            entity = None
            is_group = True if isinstance(peer_id, int) and peer_id < 0 else False
            
        group_admins = {}
        if is_group:
            try:
                from telethon.tl.types import ChannelParticipantsAdmins
                async for admin in session.client.iter_participants(peer_id, filter=ChannelParticipantsAdmins):
                    participant = getattr(admin, 'participant', None)
                    custom_tag = getattr(participant, 'rank', None)
                    if custom_tag and isinstance(custom_tag, str) and custom_tag.strip():
                        group_admins[admin.id] = custom_tag.strip()
                    else:
                        p_type = type(participant).__name__ if participant else ''
                        if 'Creator' in p_type:
                            group_admins[admin.id] = 'owner'
                        else:
                            # Any other user/bot returned by ChannelParticipantsAdmins is an admin
                            group_admins[admin.id] = 'admin'
            except Exception:
                pass
                
        read_outbox_max_id = 0
        read_inbox_max_id = 0
        unread_count = 0
        try:
            from telethon.tl.functions.messages import GetPeerDialogsRequest
            peer_input = await session.client.get_input_entity(peer_id)
            dialogs_result = await session.client(GetPeerDialogsRequest(peers=[peer_input]))
            if dialogs_result and hasattr(dialogs_result, 'dialogs') and dialogs_result.dialogs:
                d = dialogs_result.dialogs[0]
                read_outbox_max_id = getattr(d, 'read_outbox_max_id', 0)
                read_inbox_max_id = getattr(d, 'read_inbox_max_id', 0)
                unread_count = getattr(d, 'unread_count', 0)
        except Exception as e:
            pass

        try:
            offset_id = request.query.get('offset_id')
            min_id = request.query.get('min_id')
            force_latest = request.query.get('force_latest')
            
            if min_id and min_id.isdigit():
                messages = await session.client.get_messages(peer_id, limit=50, offset_id=int(min_id), reverse=True)
                messages = list(reversed(messages))
            elif offset_id and offset_id.isdigit():
                messages = await session.client.get_messages(peer_id, limit=50, offset_id=int(offset_id))
            else:
                if force_latest == '1':
                    messages = await session.client.get_messages(peer_id, limit=100)
                elif unread_count > 0 and read_inbox_max_id > 0:
                    messages = await session.client.get_messages(peer_id, limit=50, offset_id=read_inbox_max_id, add_offset=-40)
                else:
                    messages = await session.client.get_messages(peer_id, limit=100)
                
            if not messages:
                return web.Response(text="", content_type='text/html')
        except Exception as e:
            logger.error(f"Could not fetch messages for {peer_id}: {e}")
            return web.Response(text="<div style='text-align:center; padding: 20px; color:red;'>Error fetching messages from Telegram server.</div>", content_type='text/html', status=200)
        
        double_check_svg = '''<svg xmlns="http://www.w3.org/2000/svg" height="15px" viewBox="0 0 24 24" width="15px" fill="currentColor"><path d="M0 0h24v24H0V0z" fill="none"/><path d="M17.3 6.3c-.39-.39-1.02-.39-1.41 0l-5.64 5.64 1.41 1.41L17.3 7.7c.38-.38.38-1.02 0-1.4zm4.24-.01l-9.88 9.88-3.48-3.47c-.39-.39-1.02-.39-1.41 0-.39.39-.39 1.02 0 1.41l4.18 4.18c.39.39 1.02.39 1.41 0L22.95 7.71c.39-.39.39-1.02 0-1.41h-.01c-.38-.4-1.01-.4-1.4-.01zM1.12 14.12L5.3 18.3c.39.39 1.02.39 1.41 0l.7-.7-4.88-4.9c-.39-.39-1.02-.39-1.41 0-.39.39-.39 1.03 0 1.42z"/></svg>'''
        
        html = ""

        # Pre-process messages for quick replies
        msg_dict = {m.id: m for m in messages if m}
        
        reply_ids_to_fetch = []
        for m in messages:
            if getattr(m, 'reply_to', None) and getattr(m.reply_to, 'reply_to_msg_id', None):
                r_id = m.reply_to.reply_to_msg_id
                if r_id not in msg_dict and r_id not in reply_ids_to_fetch:
                    reply_ids_to_fetch.append(r_id)
        
        if reply_ids_to_fetch:
            try:
                # Telethon get_messages with ids= list fetches multiple specific messages
                fetched_replies = await session.client.get_messages(peer_id, ids=reply_ids_to_fetch)
                # Just in case some missing messages are returned or None is returned
                if not isinstance(fetched_replies, list):
                    fetched_replies = [fetched_replies]
                for rm in fetched_replies:
                    if rm:
                        msg_dict[rm.id] = rm
            except Exception as e:
                pass
        
        last_date_str = ""

        def get_date_str(msg):
            if msg and msg.date:
                dt = msg.date + timedelta(hours=5, minutes=30)
                return dt.strftime("%B %d, %Y")
            return ""

        messages_list = list(reversed(messages))
        unread_boundary_shown = False
        
        for i, m in enumerate(messages_list):
            try:
                if (unread_count > 0 and read_inbox_max_id > 0 
                    and not unread_boundary_shown and m.id > read_inbox_max_id):
                    unread_boundary_shown = True
                    html += f"""
                    <div id="unread-boundary" style="width: 100%; display: flex; align-items: center; justify-content: center; margin: 15px 0;">
                        <div style="flex: 1; height: 1px; background: rgba(0,0,0,0.1);"></div>
                        <div style="padding: 0 10px; font-size: 13px; font-weight: 500; color: #10b981; display: flex; align-items: center; gap: 6px;">
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-message-square-dot-icon lucide-message-square-dot"><path d="M12.7 3H4a2 2 0 0 0-2 2v16.286a.71.71 0 0 0 1.212.502l2.202-2.202A2 2 0 0 1 6.828 19H20a2 2 0 0 0 2-2v-4.7"/><circle cx="19" cy="6" r="3"/></svg>
                            Unread Messages
                        </div>
                        <div style="flex: 1; height: 1px; background: rgba(0,0,0,0.1);"></div>
                    </div>
                    """
                    
                date_str = get_date_str(m)
                if date_str and date_str != last_date_str:
                    today_str = (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime("%B %d, %Y")
                    disp_date = "Today" if date_str == today_str else date_str
                    html += f'<div style="width: 100%; text-align: center; margin-bottom: 8px;"><span class="system-message">{disp_date}</span></div>'
                    last_date_str = date_str

                is_first_in_block = True
                is_last_in_block = True
                
                prev_m = messages_list[i-1] if i > 0 else None
                next_m = messages_list[i+1] if i + 1 < len(messages_list) else None
                
                def is_same_block(m1, m2):
                    if not m1 or not m2: return False
                    if getattr(m1, 'action', None) or getattr(m2, 'action', None): return False
                    if getattr(m1, 'out', False) != getattr(m2, 'out', False): return False
                    if getattr(m1, 'sender_id', None) != getattr(m2, 'sender_id', None): return False
                    if get_date_str(m1) != get_date_str(m2): return False
                    dt1 = m1.date
                    dt2 = m2.date
                    if dt1 and dt2 and abs((dt2 - dt1).total_seconds()) > 300: return False
                    return True

                if is_same_block(prev_m, m):
                    is_first_in_block = False
                if is_same_block(m, next_m):
                    is_last_in_block = False

                time_str = ""
                if m.date:
                    time_str = (m.date + timedelta(hours=5, minutes=30)).strftime("%I:%M %p").lstrip("0")
                    
                is_phone_call = False
                action_obj = getattr(m, 'action', None)
                if action_obj and action_obj.__class__.__name__ == 'MessageActionPhoneCall':
                    is_phone_call = True
    
                if action_obj and not is_phone_call:
                    action_text = "Service message"
                    action_type = action_obj.__class__.__name__
                    
                    actor_name = ""
                    sender = getattr(m, 'sender', None)
                    if sender:
                        actor_name = utils.get_display_name(sender)
                    else:
                        sender_id = getattr(m, 'sender_id', None)
                        if sender_id:
                            try:
                                ent = await session.client.get_entity(sender_id)
                                actor_name = utils.get_display_name(ent)
                            except:
                                actor_name = f"User {sender_id}"
                        else:
                            actor_name = "Someone"
                    
                    if action_type == 'MessageActionChatAddUser': 
                        added_users = []
                        users = getattr(action_obj, 'users', [])
                        if len(users) == 1 and users[0] == getattr(m, 'sender_id', None):
                            action_text = f"{actor_name} joined the group"
                        else:
                            for uid in users:
                                try:
                                    user_peer = await asyncio.wait_for(session.client.get_entity(uid), timeout=1.0)
                                    added_users.append(utils.get_display_name(user_peer))
                                except:
                                    added_users.append(str(uid))
                            users_str = ", ".join(added_users) if added_users else "user(s)"
                            action_text = f"{actor_name} invited {users_str}"
                    elif action_type == 'MessageActionChatDeleteUser': 
                        target_id = getattr(action_obj, 'user_id', None)
                        sender_id = getattr(m, 'sender_id', None)
                        if target_id and target_id != sender_id:
                            removed_name = str(target_id)
                            try:
                                t_user = await asyncio.wait_for(session.client.get_entity(target_id), timeout=1.0)
                                removed_name = utils.get_display_name(t_user)
                            except: pass
                            action_text = f"{actor_name} removed {removed_name}"
                        else:
                            action_text = f"{actor_name} left the group"
                    elif action_type == 'MessageActionChatJoinedByLink':
                        action_text = f"{actor_name} joined via invite link"
                    elif action_type == 'MessageActionChatJoinedByRequest':
                        action_text = f"{actor_name} was accepted into the group"
                    elif action_type == 'MessageActionPinMessage': 
                        action_text = f"{actor_name} pinned a message"
                    elif action_type == 'MessageActionChatEditTitle': 
                        new_title = getattr(action_obj, 'title', 'group name')
                        action_text = f"{actor_name} changed group/channel name to '{new_title}'"
                    elif action_type == 'MessageActionGroupCall':
                        dur = getattr(action_obj, 'duration', 0)
                        if dur and dur > 0:
                            h = dur // 3600
                            md = (dur % 3600) // 60
                            sd = dur % 60
                            dstr = f"{h}h {md:02d}m {sd:02d}s" if h > 0 else (f"{md}m {sd:02d}s" if md > 0 else f"{sd}s")
                            action_text = f"{actor_name} ended the video chat ({dstr})"
                        else:
                            action_text = f"{actor_name} started a video chat"
                    elif action_type == 'MessageActionChatCreate':
                        title = getattr(action_obj, 'title', 'the group')
                        action_text = f"{actor_name} created the group '{title}'"
                    elif action_type == 'MessageActionChannelCreate':
                        title = getattr(action_obj, 'title', 'the channel')
                        action_text = f"Channel '{title}' created"
                    elif action_type == 'MessageActionChatEditPhoto':
                        action_text = f"{actor_name} updated chat photo"
                    elif action_type == 'MessageActionChatDeletePhoto':
                        action_text = f"{actor_name} removed chat photo"
                    elif action_type == 'MessageActionChatMigrateTo':
                        action_text = f"Group upgraded to a supergroup"
                    elif action_type == 'MessageActionChannelMigrateFrom':
                        title = getattr(action_obj, 'title', 'the group')
                        action_text = f"Supergroup upgraded from '{title}'"
                    elif action_type == 'MessageActionHistoryClear':
                        action_text = f"{actor_name} cleared history"
                    elif action_type == 'MessageActionGameScore':
                        score = getattr(action_obj, 'score', 0)
                        action_text = f"{actor_name} scored {score} in a game"
                    elif action_type == 'MessageActionPaymentSentMe':
                        amount = getattr(action_obj, 'total_amount', 0)
                        currency = getattr(action_obj, 'currency', '')
                        action_text = f"You received a payment of {amount} {currency}"
                    elif action_type == 'MessageActionPaymentSent':
                        amount = getattr(action_obj, 'total_amount', 0)
                        currency = getattr(action_obj, 'currency', '')
                        action_text = f"{actor_name} sent a payment of {amount} {currency}"
                    elif action_type == 'MessageActionScreenshotTaken':
                        action_text = f"{actor_name} took a screenshot!"
                    elif action_type == 'MessageActionBotAllowed':
                        domain = getattr(action_obj, 'domain', 'a bot')
                        action_text = f"{actor_name} logged in via {domain}"
                    elif action_type == 'MessageActionContactSignUp':
                        action_text = f"{actor_name} joined Telegram!"
                    elif action_type == 'MessageActionGeoProximityReached':
                        try:
                            dist = getattr(action_obj, 'distance', 0)
                            to_peer_id = getattr(action_obj, 'to_id', None)
                            peer_name = "someone"
                            if to_peer_id:
                                try:
                                    to_peer_ent = await asyncio.wait_for(session.client.get_entity(to_peer_id), timeout=1.0)
                                    peer_name = utils.get_display_name(to_peer_ent)
                                except: pass
                            action_text = f"{actor_name} is now within {dist} meters of {peer_name}"
                        except:
                            action_text = f"{actor_name} is now in proximity"
                    elif action_type == 'MessageActionInviteToGroupCall':
                        invited_users = []
                        for uid in getattr(action_obj, 'users', []):
                            try:
                                user_peer = await asyncio.wait_for(session.client.get_entity(uid), timeout=1.0)
                                invited_users.append(utils.get_display_name(user_peer))
                            except:
                                invited_users.append(str(uid))
                        users_str = ", ".join(invited_users) if invited_users else "user(s)"
                        action_text = f"{actor_name} invited {users_str} to the video chat"
                    elif action_type == 'MessageActionSetMessagesTTL':
                        period = getattr(action_obj, 'period', 0)
                        if period > 0:
                            period_str = f"{period} seconds"
                            if period >= 86400: period_str = f"{period // 86400} days"
                            elif period >= 3600: period_str = f"{period // 3600} hours"
                            elif period >= 60: period_str = f"{period // 60} minutes"
                            action_text = f"{actor_name} set messages to auto-delete in {period_str}"
                        else:
                            action_text = f"{actor_name} disabled auto-delete"
                    elif action_type == 'MessageActionGroupCallScheduled':
                        sch = getattr(action_obj, 'schedule_date', None)
                        dt_str = sch.strftime("%B %d, %H:%M") if sch else "the future"
                        action_text = f"{actor_name} scheduled a video chat for {dt_str}"
                    elif action_type == 'MessageActionSetChatTheme':
                        theme = getattr(action_obj, 'emoticon', 'default theme')
                        action_text = f"{actor_name} changed the chat theme to {theme}"
                    elif action_type == 'MessageActionTopicCreate':
                        title = getattr(action_obj, 'title', 'a topic')
                        action_text = f"{actor_name} created topic '{title}'"
                    elif action_type == 'MessageActionTopicEdit':
                        action_text = f"{actor_name} edited the topic"
                    elif action_type == 'MessageActionSuggestProfilePhoto':
                        action_text = f"{actor_name} suggested a profile photo"
                    elif action_type == 'MessageActionSetChatWallPaper':
                        action_text = f"{actor_name} set a new chat wallpaper"
                    elif action_type == 'MessageActionGiftPremium':
                        months = getattr(action_obj, 'months', 0)
                        action_text = f"{actor_name} gifted Telegram Premium for {months} months!"
                    elif action_type == 'MessageActionBotAssignAndResign':
                        action_text = f"{actor_name} updated bot admin rights"
                    elif action_type == 'MessageActionCustomAction':
                        action_text = getattr(action_obj, 'message', "Service message")
                    else:
                        msg_str = getattr(m, 'message', "")
                        action_text = msg_str if msg_str else f"{actor_name} performed {action_type}"
                    
                    html += f'<div id="msg-{m.id}" style="width: 100%; text-align: center; margin-bottom: 8px;"><span class="system-message">{action_text}</span></div>'
                    continue
                
                # Verify Media Status correctly
                display_media = m.media
                media_type_name = type(display_media).__name__ if display_media else None
                is_media_empty_obj = media_type_name == 'MessageMediaEmpty'
                is_media_unsupported = media_type_name == 'MessageMediaUnsupported'
                
                is_empty_media_attr = False
                if display_media:
                    if hasattr(display_media, 'photo') and not getattr(display_media, 'photo', None):
                        is_empty_media_attr = True
                    if hasattr(display_media, 'document') and not getattr(display_media, 'document', None):
                        is_empty_media_attr = True

                has_ttl_seconds = getattr(display_media, 'ttl_seconds', None) is not None
                is_view_once_expired = has_ttl_seconds and getattr(m, 'media_unread', False) is False

                is_expired_overall = is_media_empty_obj or is_empty_media_attr or is_view_once_expired

                if is_expired_overall or is_media_unsupported:
                    display_media = None
                    
                msg_text_content = (getattr(m, 'message', "") or "").strip()
                has_text = bool(msg_text_content)
                
                is_expired_bubble = False
                if action_obj is None and display_media is None and getattr(m, 'media', None):
                    is_expired_bubble = True

                # Just string safety empty text check
                if action_obj is None and not getattr(m, 'media', None) and not display_media and not has_text:
                    continue
    
                cls = "out" if getattr(m, 'out', False) else "in"
                
                if is_phone_call:
                    action_reason = getattr(action_obj, 'reason', None)
                    reason_type = str(type(action_reason)) if action_reason else ""
                    
                    is_missed = 'Missed' in reason_type or 'Busy' in reason_type
                    dur = getattr(action_obj, 'duration', 0)
                    if not dur and getattr(action_reason, 'duration', 0):
                        dur = action_reason.duration
                        
                    dur_text = ""
                    if dur and dur > 0:
                        h = dur // 3600
                        md = (dur % 3600) // 60
                        sd = dur % 60
                        if h > 0: dur_text = f"{h}h {md:02d}m {sd:02d}s"
                        elif md > 0: dur_text = f"{md}m {sd:02d}s"
                        else: dur_text = f"{sd}s"
                    elif not is_missed:
                        dur_text = "Canceled"
                    
                    title = "Incoming Call"
                    icon_color = "#52b146" if getattr(m, 'out', False) else "#3390ec"
                    
                    if getattr(m, 'out', False):
                        title = "Outgoing Call"
                    
                    if is_missed:
                        title = "Missed Call"
                        icon_color = "#ff5e5e"
                        dur_text = ""
                    
                    msg_text = f"""<div style="display: flex; align-items: center; gap: 12px; margin-top: 2px; margin-bottom: 2px; padding-right: 20px;">
                        <div style="width: 36px; height: 36px; border-radius: 50%; background: {icon_color}; display: flex; align-items: center; justify-content: center; color: white; flex-shrink: 0;">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"></path></svg>
                        </div>
                        <div style="display: flex; flex-direction: column;">
                            <span style="font-weight: 500; font-size: 15px; white-space: nowrap;">{title}</span>
                            <span style="font-size: 13px; opacity: 0.7; margin-top: 2px; white-space: nowrap; display: {'block' if dur_text else 'none'};">{dur_text}</span>
                        </div>
                    </div>"""
                else:
                    msg_text = msg_text_content.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    if is_expired_bubble:
                        if not has_text:
                            if is_media_unsupported:
                                msg_text = "<span style='opacity: 0.7; font-style: italic; display: inline-flex; align-items: center; gap: 6px;'><svg width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><circle cx='12' cy='12' r='10'></circle><line x1='12' y1='8' x2='12' y2='12'></line><line x1='12' y1='16' x2='12.01' y2='16'></line></svg> Unsupported Media</span>"
                            elif is_expired_overall:
                                msg_text = "<span style='opacity: 0.7; font-style: italic; display: inline-flex; align-items: center; gap: 6px;'><svg width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><circle cx='12' cy='12' r='10'></circle><path d='m4.9 4.9 14.2 14.2'></path></svg> Expired Media</span>"
                            else:
                                msg_text = "<span style='opacity: 0.7; font-style: italic;'>Deleted Message</span>"
                        else:
                            msg_text = f"<span style='opacity: 0.7; font-style: italic; display: inline-flex; align-items: center; gap: 6px;'><svg width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><circle cx='12' cy='12' r='10'></circle><path d='m4.9 4.9 14.2 14.2'></path></svg> {msg_text}</span>"
                
                # Forwarded / Reply
                fwd_html = ""
                if getattr(m, 'fwd_from', None):
                    fwd_name = "Unknown"
                    fwd_obj = getattr(m, 'forward', None)
                    if fwd_obj and getattr(fwd_obj, 'sender', None):
                        fwd_name = utils.get_display_name(fwd_obj.sender)
                    elif fwd_obj and getattr(fwd_obj, 'chat', None):
                        fwd_name = utils.get_display_name(fwd_obj.chat)
                    elif getattr(m.fwd_from, 'from_name', None):
                        fwd_name = m.fwd_from.from_name
                    elif getattr(m.fwd_from, 'from_id', None):
                        try:
                            fwd_name = str(utils.get_peer_id(m.fwd_from.from_id))
                        except: pass
                    fwd_html = f"<div style='font-size: 13px; color: var(--primary); font-weight: 500; margin-bottom: 3px;'>Forwarded from {fwd_name}</div>"
    
                reply_html = ""
                if getattr(m, 'reply_to', None) and getattr(m.reply_to, 'reply_to_msg_id', None):
                    reply_msg_id = m.reply_to.reply_to_msg_id
                    reply_title = "Message"
                    reply_text = "Message"
                    
                    if reply_msg_id in msg_dict:
                        rm = msg_dict[reply_msg_id]
                        if getattr(rm, 'sender', None): reply_title = utils.get_display_name(rm.sender)
                        reply_text = (getattr(rm, 'message', "") or "").replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                        if rm.media: reply_text = "(Media) " + reply_text
                    
                    reply_html = f"<div class='reply-box' onclick='scrollToMsg({reply_msg_id})'><div class='reply-title'>{reply_title}</div><div class='reply-text'>{reply_text}</div></div>"
                    
                media_html = ""
                is_sticker_only = False
                
                has_header = bool(fwd_html or reply_html or (is_group and not getattr(m, 'out', False)))
                media_margin = f"margin-top: {'8px' if has_header else '0px'}; margin-bottom: 10px; display: flex; flex-direction: column; align-items: flex-start; gap: 10px; width: 100%; box-sizing: border-box;"
                
                if display_media:
                    media_url = f"/api/user/{user_id}/chat/{peer_id}/media/{m.id}"
                    
                    download_btn = ""
                    media_size = 0
                    if hasattr(display_media, 'document'):
                        media_size = getattr(display_media.document, 'size', 0)
                    elif hasattr(display_media, 'photo'):
                        sizes = getattr(display_media.photo, 'sizes', [])
                        valid_sizes = [getattr(s, 'size', 0) for s in sizes] + [0]
                        media_size = max(valid_sizes)
                    
                    if media_size > 0:
                        size_str = format_bytes(media_size)
                        download_btn = f"<div style='width: 100%; box-sizing: border-box;'><a href='{media_url}?download=1' download style='display: flex; justify-content: center; align-items: center; gap: 6px; background: rgba(0,0,0,0.05); color: var(--primary); padding: 8px 12px; border-radius: 8px; font-size: 14px; text-decoration: none; font-weight: bold; width: 100%; box-sizing: border-box;'><svg width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'><path d='M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4'/><polyline points='7 10 12 15 17 10'/><line x1='12' y1='15' x2='12' y2='3'/></svg> Download ({size_str})</a></div>"

                    if hasattr(display_media, 'photo'):
                        rad = '12px' if not has_header else '8px'
                        media_html = f"<div style='{media_margin}'><a href='{media_url}' target='_blank' style='width: 100%; text-align: left;'><img src='{media_url}' style='width: 100%; min-width: 240px; max-width: 300px; height: auto; border-radius: {rad}; display: block;'/></a>{download_btn}</div>"
                    elif hasattr(display_media, 'document'):
                        mime = getattr(display_media.document, 'mime_type', '') or ''
                        attributes = getattr(display_media.document, 'attributes', [])
                        is_sticker = attributes and any(type(x).__name__ == 'DocumentAttributeSticker' for x in attributes)
                        is_animated = attributes and any(type(x).__name__ == 'DocumentAttributeAnimated' for x in attributes)
                        is_video = 'video/' in mime or any(type(x).__name__ == 'DocumentAttributeVideo' for x in attributes)
                        
                        is_tgs = 'application/x-tgsticker' in mime
                        is_gif = 'image/gif' in mime or (is_animated and not is_sticker and 'video/mp4' in mime)
                        is_video_sticker = is_video and (is_sticker or (getattr(display_media.document, 'size', 0) < 1000000 and not msg_text and is_animated and not is_gif))
                        is_static_sticker = 'image/webp' in mime and (is_sticker or (getattr(display_media.document, 'size', 0) < 500000 and not msg_text))
                        
                        if is_tgs or is_video_sticker or is_static_sticker:
                            is_sticker_only = not msg_text
                            download_btn = "" # Hidden for stickers
                            
                            sticker_html_content = ""
                            if is_tgs:
                                sticker_html_content = f"<lottie-player autoplay loop src='{media_url}' style='width: 200px; height: 200px; display: block; margin-bottom: 4px;'></lottie-player>"
                            elif is_video_sticker:
                                sticker_html_content = f"<video src='{media_url}' autoplay loop muted playsinline style='max-width: 200px; max-height: 200px; border-radius: 8px; display: block; margin-bottom: 4px;'></video>"
                            else:
                                sticker_html_content = f"<img src='{media_url}' style='max-width: 200px; max-height: 200px; display: block; margin-bottom: 4px;'/>"
                            
                            sticker_set_name = ""
                            sticker_set_id = ""
                            sticker_set_hash = ""
                            for attr in attributes:
                                if type(attr).__name__ == "DocumentAttributeSticker" and getattr(attr, 'stickerset', None):
                                    sset = attr.stickerset
                                    if hasattr(sset, 'short_name') and sset.short_name:
                                        sticker_set_name = sset.short_name
                                    elif hasattr(sset, 'id') and hasattr(sset, 'access_hash'):
                                        sticker_set_id = str(sset.id)
                                        sticker_set_hash = str(sset.access_hash)
                            
                            sticker_copy_btn = ""
                            if sticker_set_name or (sticker_set_id and sticker_set_hash and sticker_set_id != "0"):
                                svg_icon = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" width="24px" height="24px" fill="#1f1f1f"><path d="M360-240q-33 0-56.5-23.5T280-320v-480q0-33 23.5-56.5T360-880h360q33 0 56.5 23.5T800-800v480q0 33-23.5 56.5T720-240H360Zm0-80h360v-480H360v480ZM200-80q-33 0-56.5-23.5T120-160v-560h80v560h440v80H200Zm160-240v-480 480Z"/></svg>'
                                js_call = f"copyStickerLink(this, '{sticker_set_id}', '{sticker_set_hash}', '{sticker_set_name}');"
                                sticker_copy_btn = f"""<div style=\"cursor: pointer; display: flex; align-items: center; justify-content: center; width: 38px; height: 38px; padding: 7px; box-sizing: border-box; border-radius: 50%; background: rgba(0,0,0,0.06); transition: background 0.15s; margin: 0 8px; flex-shrink: 0;\" onclick=\"{js_call}\" onmouseover=\"this.style.background='rgba(0,0,0,0.12)'\" onmouseout=\"this.style.background='rgba(0,0,0,0.06)'\" title=\"Copy Sticker Pack Link\">{svg_icon}</div>"""
                                
                            if sticker_copy_btn:
                                if getattr(m, 'out', False):
                                    media_html = f"<div style='{media_margin}'><div style='display: flex; align-items: center; justify-content: flex-end; width: 100%;'>{sticker_copy_btn}{sticker_html_content}</div></div>"
                                else:
                                    media_html = f"<div style='{media_margin}'><div style='display: flex; align-items: center; justify-content: flex-start; width: 100%;'>{sticker_html_content}{sticker_copy_btn}</div></div>"
                            else:
                                media_html = f"<div style='{media_margin}'>{sticker_html_content}</div>"
                                
                        elif is_gif:
                            rad = '12px' if not has_header else '8px'
                            media_html = f"<div style='{media_margin}'><video src='{media_url}' autoplay loop muted playsinline style='max-width: 250px; max-height: 250px; border-radius: {rad}; display: block;'></video>{download_btn}</div>"
                                
                        elif any(type(x).__name__ == 'DocumentAttributeAudio' and getattr(x, 'voice', False) for x in attributes) and 'ogg' in mime:
                            is_voice = True # This variable was missing, added for context
                            media_html = f"<div style='{media_margin}'><audio src='{media_url}' controls style='width: 300px; max-width: 100%; height: 40px; border-radius: 8px;'></audio>{download_btn}</div>"
                            
                        elif 'image/' in mime and not ('image/gif' in mime) and not ('webp' in mime):
                            rad = '12px' if not has_header else '8px'
                            media_html = f"<div style='{media_margin}'><a href='{media_url}' target='_blank' style='width: 100%; text-align: left;'><img src='{media_url}' style='width: 300px; max-width: 100%; height: auto; border-radius: {rad}; display: block;'/></a>{download_btn}</div>"
                            
                        elif is_video and not is_video_sticker:
                            rad = '12px' if not has_header else '8px'
                            
                            dur_str = ""
                            for attr in attributes:
                                if type(attr).__name__ == "DocumentAttributeVideo":
                                    dur_sec = getattr(attr, 'duration', 0)
                                    if dur_sec:
                                        dur_str = f"{int(dur_sec // 60)}:{int(dur_sec % 60):02d}"
                                        
                            meta_tag = f"<div style='position: absolute; top: 8px; left: 8px; background: rgba(0,0,0,0.5); color: white; padding: 2px 6px; border-radius: 6px; font-size: 11px; font-weight: 500;'>{dur_str}</div>" if dur_str else ""
                            play_svg = '<svg width="44" height="44" viewBox="0 0 24 24" fill="white" stroke="white" stroke-width="1"><circle cx="12" cy="12" r="10" fill="rgba(0,0,0,0.4)" stroke="white" stroke-width="1.5"></circle><polygon points="10 8 16 12 10 16 10 8"></polygon></svg>'
                            
                            media_html = f"<div style='{media_margin}; position: relative;'><a href='{media_url}' target='_blank' style='position: relative; display: flex; align-items: center; justify-content: flex-start; border-radius: {rad}; overflow: hidden; background: #333; width: 300px; max-width: 100%; text-decoration: none;'><img src='{media_url}?thumb=1' style='width: 300px; max-width: 100%; height: auto; min-height: 120px; display: block; object-fit: cover;' onerror=\"this.style.opacity=0;\"/><div style='position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); display: flex; align-items: center; justify-content: center;'>{play_svg}</div>{meta_tag}</a>{download_btn}</div>"

                        else:
                            name = "Document"
                            if 'image/gif' in mime:
                                name = "Video Animation"
                            elif 'audio/' in mime:
                                name = "Audio"
                                
                            dur_str = ""
                            for attr in attributes:
                                if hasattr(attr, 'file_name') and attr.file_name: 
                                    name = attr.file_name
                                if type(attr).__name__ in ["DocumentAttributeAudio", "DocumentAttributeVideo"]:
                                    dur_sec = getattr(attr, 'duration', 0)
                                    if dur_sec:
                                        dur_str = f"{int(dur_sec // 60)}:{int(dur_sec % 60):02d}"
                            
                            icon_svg = ""
                            if 'audio/' in mime:
                                icon_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-headphones-icon lucide-headphones"><path d="M3 14h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-7a9 9 0 0 1 18 0v7a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3"/></svg>'
                            elif 'video/' in mime or 'image/gif' in mime:
                                icon_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-film-icon lucide-film"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M7 3v18"/><path d="M3 7.5h4"/><path d="M3 12h18"/><path d="M3 16.5h4"/><path d="M17 3v18"/><path d="M17 7.5h4"/><path d="M17 16.5h4"/></svg>'
                            else:
                                icon_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-file-icon lucide-file"><path d="M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z"/><path d="M14 2v5a1 1 0 0 0 1 1h5"/></svg>'
                                
                            rad = '12px' if not has_header else '8px'
                            media_html = f"<div style='{media_margin}'><a href='{media_url}' target='_blank' style='background: rgba(0,0,0,0.05); padding: 8px 12px; border-radius: {rad}; display: flex; align-items: center; justify-content: flex-start; gap: 12px; width: 100%; box-sizing: border-box; text-decoration: none; color: inherit;'><div style='width: 36px; height: 36px; border-radius: 50%; background: var(--primary); color: white; display: flex; align-items: center; justify-content: center; flex-shrink: 0;'>{icon_svg}</div><div style='display: flex; flex-direction: column; overflow: hidden; width: 100%;'><span style='font-size: 14px; font-weight: 500; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; white-space: normal; color: inherit; word-break: break-word;'>{name}</span><span style='font-size: 12px; color: var(--text-muted); display: {'block' if dur_str else 'none'};'>{dur_str}</span></div></a>{download_btn}</div>"
                    elif hasattr(display_media, 'webpage'):
                        # Small preview for webpage since it's tricky to replicate
                        media_html = f"<div style='border-left: 2px solid var(--primary); padding-left: 8px; margin-bottom: 4px; font-size: 13px; color: #555;'>Link Preview</div>"
                    else:
                        media_html = "<div style='background: rgba(0,0,0,0.05); padding: 6px; border-radius: 8px; margin-bottom: 4px; display: flex; align-items: center; gap: 8px;'><svg xmlns=\"http://www.w3.org/2000/svg\" width=\"20\" height=\"20\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><rect width=\"18\" height=\"18\" x=\"3\" y=\"3\" rx=\"2\" ry=\"2\"/><circle cx=\"9\" cy=\"9\" r=\"2\"/><path d=\"m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21\"/></svg>Unsupported Media</div>"
                
                # Tick: single tick = sent (unseen), double tick = seen
                single_check_svg = '''<svg xmlns="http://www.w3.org/2000/svg" height="15px" viewBox="0 0 24 24" width="15px" fill="currentColor"><path d="M0 0h24v24H0V0z" fill="none"/><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z"/></svg>'''
                if getattr(m, 'out', False):
                    # We rely purely on read_outbox_max_id.
                    # If it's 0 (meaning nothing is seen yet by the other peer), m.id <= 0 will be False.
                    is_seen = m.id <= read_outbox_max_id
                    tick_icon = double_check_svg if is_seen else single_check_svg
                else:
                    tick_icon = ""
                
                bubble_style = ""
                if is_sticker_only:
                    bubble_style = 'style="background: transparent; box-shadow: none; padding: 0;"'
    
                if is_first_in_block:
                    grp_align = "flex-end" if getattr(m, 'out', False) else "flex-start"
                    html += f'<div class="message-block" style="display: flex; justify-content: {grp_align}; margin-bottom: 8px; position: relative; width: 100%;">'
                    
                    if is_group and not getattr(m, 'out', False):
                        sender_name = "Unknown"
                        sender_id = getattr(m, 'sender_id', None) or 0
                        if getattr(m, 'sender', None):
                            sender_name = utils.get_display_name(m.sender) or "Unknown"
                        color = f"hsl({(sender_id * 137) % 360}, 65%, 45%)"
                        sender_initial = sender_name[0].upper() if sender_name else '?'
                        
                        avatar_dom = f"""<img src="/avatar/{user_id}/{sender_id}" style="width: 34px; height: 34px; border-radius: 50%; object-fit: cover; background: {color};" onerror="this.outerHTML='<div style=\\'width: 34px; height: 34px; border-radius: 50%; background: {color}; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; font-size: 14px;\\'>{sender_initial}</div>'" onclick="window.location.href='/user/{user_id}/chat/{sender_id}'"/>"""
                        
                        html += f'<div class="sticky-avatar-wrapper" style="align-self: flex-end; position: sticky; bottom: 8px; margin-right: 12px; flex-shrink: 0; cursor: pointer;">{avatar_dom}</div>'
                        
                    html += '<div class="message-group-content" style="display: flex; flex-direction: column; max-width: 100%;">'
                
                sender_html = ""
                if is_group and not getattr(m, 'out', False) and is_first_in_block:
                    s_name = "Unknown"
                    if getattr(m, 'sender', None):
                        s_name = utils.get_display_name(m.sender) or "Unknown"
                    s_id = getattr(m, 'sender_id', None) or 0
                    s_color = f"hsl({(s_id * 137) % 360}, 65%, 45%)"
                    
                    role_tag = ""
                    if s_id in group_admins:
                        tag_text = group_admins[s_id]
                        role_tag = f"<span style='margin-left: 6px; font-size: 11px; color: #10b981; background: rgba(16, 185, 129, 0.15); padding: 2px 8px; border-radius: 50px; font-weight: 500; white-space: nowrap; flex-shrink: 0; display: inline-flex; align-items: center; justify-content: center;'>{tag_text}</span>"
                    
                    sender_html = f'<div style="display: flex; align-items: center; margin-bottom: 2px; font-size: 13px; line-height: 1.2; width: 100%; overflow: hidden;"><span style="color: {s_color}; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; cursor: pointer; flex-shrink: 1;">{s_name}</span>{role_tag}</div>'

                # Wrap message content
                msg_content = f"""
                <div id="msg-{m.id}" class="message {cls}" {bubble_style}>
                    {fwd_html}
                    {sender_html}
                    {reply_html}
                    {media_html}
                    <span class="msg-text" style="display:{'inline' if msg_text else 'none'}">{msg_text}</span>
                    <span class="msg-meta" style="{'background: rgba(0,0,0,0.3); border-radius: 10px; padding: 2px 6px; color: white;' if is_sticker_only else ''}">
                        <span class="msg-time">{time_str}</span>
                        <span class="msg-tick" style="display:{'flex' if tick_icon else 'none'}; align-items:center;">{tick_icon}</span>
                    </span>
                </div>
                """
                
                wrapper_margin = "0px" if not is_last_in_block else "0px"
                message_gap = "2px" if not is_last_in_block else "0px"
                
                html += f"""
                <div class="message-wrapper {cls}" style="margin-bottom: {message_gap}; width: 100%; justify-content: {'flex-end' if getattr(m, 'out', False) else 'flex-start'}">
                    {msg_content}
                </div>
                """
                
                if is_last_in_block:
                    html += '</div></div>'
            except Exception as e:
                logger.error(f"Error parsing message {getattr(m, 'id', 'unknown')}: {e}", exc_info=True)
                # Ignore this bad message to let the rest load
                 
            
        if not html:
            html = '<div style="text-align:center; padding: 40px; color:var(--text-muted); font-size: 14px;">No earlier messages</div>'
            
        return web.Response(text=html, content_type='text/html')
    except Exception as e:
        logger.error(f"Error fetching messages: {e}", exc_info=True)
        return web.Response(status=500)

async def handle_chat_media_api(request):
    try:
        user_id = int(request.match_info.get('user_id'))
        peer_id_str = request.match_info.get('peer_id')
        peer_id = int(peer_id_str) if peer_id_str.lstrip('-').isdigit() else peer_id_str
        msg_id = int(request.match_info.get('message_id'))
        
        active_sessions = request.app['active_sessions']
        session = active_sessions.get(user_id)
        
        if not session or not session.client or not session.client.is_connected():
            return web.Response(status=404)
            
        message = await session.client.get_messages(peer_id, ids=msg_id)
        if not message or not message.media:
            return web.Response(status=404)
            
        import io
        out = io.BytesIO()
        is_thumb = request.query.get('thumb') == '1'
        
        if is_thumb:
            thumb_obj = None
            if hasattr(message.media, 'document') and hasattr(message.media.document, 'thumbs') and message.media.document.thumbs:
                thumb_obj = message.media.document.thumbs[-1]
            elif hasattr(message.media, 'photo') and hasattr(message.media.photo, 'sizes') and message.media.photo.sizes:
                thumb_obj = message.media.photo.sizes[-1]
                
            if thumb_obj:
                await session.client.download_media(message.media, out, thumb=thumb_obj)
            else:
                await session.client.download_media(message.media, out, thumb=1)
        else:
            await session.client.download_media(message.media, out)
            
        out.seek(0)
        
        content_type = 'application/octet-stream'
        if is_thumb:
            content_type = 'image/jpeg'
        elif hasattr(message.media, 'document') and hasattr(message.media.document, 'mime_type'):
            content_type = message.media.document.mime_type
        elif hasattr(message.media, 'photo'):
            content_type = 'image/jpeg'
            
        if out.getbuffer().nbytes == 0:
            return web.Response(status=404)
            
        data = out.read()
        if 'application/x-tgsticker' in content_type:
            import gzip
            try:
                data = gzip.decompress(data)
                content_type = 'application/json'
            except Exception as e:
                pass
                
        headers = {}
        if request.query.get('download') == '1':
            fn = None
            if hasattr(message.media, 'document'):
                for attr in getattr(message.media.document, 'attributes', []):
                    if hasattr(attr, 'file_name') and attr.file_name:
                        fn = attr.file_name
                        break
                        
            import mimetypes
            ext = mimetypes.guess_extension(content_type) or ""
            if content_type == 'audio/ogg': ext = '.ogg'
            elif content_type == 'video/mp4': ext = '.mp4'
            elif content_type == 'application/x-tgsticker': ext = '.tgs'
            elif 'webp' in content_type: ext = '.webp'
            
            if not fn:
                fn = f"media_{msg_id}{ext}"
            elif '.' not in fn and ext:
                fn = f"{fn}{ext}"
                
            headers['Content-Disposition'] = f'attachment; filename="{fn}"'
            
        return web.Response(body=data, content_type=content_type, headers=headers)
    except Exception as e:
        logger.error(f"Error fetching media: {e}")
        return web.Response(status=500)

async def handle_sticker_link_api(request):
    try:
        user_id = int(request.match_info.get('user_id'))
    except (TypeError, ValueError):
        return web.Response(status=400)
        
    sid = request.query.get('id')
    shash = request.query.get('hash')
    
    active_sessions = request.app['active_sessions']
    session = active_sessions.get(user_id)
    
    if not session or not session.client or not sid or not shash:
        return web.Response(status=404)
        
    try:
        from telethon import types, functions
        stickerset = types.InputStickerSetID(id=int(sid), access_hash=int(shash))
        pack = await session.client(functions.messages.GetStickerSetRequest(stickerset=stickerset, hash=0))
        if hasattr(pack, 'set') and hasattr(pack.set, 'short_name'):
            return web.Response(text=pack.set.short_name, content_type="text/plain")
        return web.Response(status=404)
    except Exception as e:
        logger.error(f"Error fetching sticker link: {e}")
        return web.Response(status=500)

async def handle_peer_info_page(request):
    try:
        user_id = int(request.match_info.get('user_id'))
        peer_id_str = request.match_info.get('peer_id')
        peer_id = int(peer_id_str) if peer_id_str.lstrip('-').isdigit() else peer_id_str

        active_sessions = request.app['active_sessions']
        session = active_sessions.get(user_id)

        if not session or not session.client or not session.client.is_connected():
            return web.Response(text='Session not found or disconnected', status=404)

        client = session.client
        entity = await client.get_entity(peer_id)
        name = utils.get_display_name(entity) or 'Unknown'
        name_initial = name[0].upper() if name else '?'
        entity_type = type(entity).__name__

        is_user = entity_type == 'User'
        is_bot = getattr(entity, 'bot', False)
        is_channel = getattr(entity, 'broadcast', False)
        is_group = entity_type in ('Chat', 'Channel') and not is_channel

        # Common fields
        peer_id_val = utils.get_peer_id(entity)
        username = f"@{entity.username}" if getattr(entity, 'username', None) else 'None'
        bio = 'None'
        members_count = 0
        online_count = 0
        creation_date = 'Unknown'
        common_groups_count = 'N/A'
        phone = 'Hidden'
        first_name = 'None'
        last_name = 'None'
        dc_id = 'Unknown'
        is_verified = getattr(entity, 'verified', False)
        is_scam = getattr(entity, 'scam', False)
        is_fake = getattr(entity, 'fake', False)
        is_restricted = getattr(entity, 'restricted', False)
        is_premium = False
        status_text = ''
        linked_chat = 'None'
        has_geo = False
        slowmode = 'Off'

        # DC ID from photo
        if getattr(entity, 'photo', None) and hasattr(entity.photo, 'dc_id'):
            dc_id = str(entity.photo.dc_id)

        if is_user:
            first_name = getattr(entity, 'first_name', '') or 'None'
            last_name = getattr(entity, 'last_name', '') or 'None'
            phone_val = getattr(entity, 'phone', None)
            if phone_val:
                phone = f'+{phone_val}'
            is_premium = getattr(entity, 'premium', False)

            # Status
            user_status = getattr(entity, 'status', None)
            status_type_name = type(user_status).__name__ if user_status else ''
            if status_type_name == 'UserStatusOnline':
                status_text = 'online'
            elif status_type_name == 'UserStatusRecently':
                status_text = 'last seen recently'
            elif status_type_name == 'UserStatusLastWeek':
                status_text = 'last seen within a week'
            elif status_type_name == 'UserStatusLastMonth':
                status_text = 'last seen within a month'
            elif status_type_name == 'UserStatusOffline':
                was_online = getattr(user_status, 'was_online', None)
                if was_online:
                    ist_dt = was_online + timedelta(hours=5, minutes=30)
                    now_ist = datetime.utcnow() + timedelta(hours=5, minutes=30)
                    time_str = ist_dt.strftime('%I:%M %p').lstrip('0')
                    if ist_dt.date() == now_ist.date():
                        status_text = f"last seen at {time_str}"
                    elif ist_dt.date() == (now_ist - timedelta(days=1)).date():
                        status_text = f"last seen yesterday at {time_str}"
                    else:
                        month_str = ist_dt.strftime('%b')
                        status_text = f"last seen {month_str} {ist_dt.day} at {time_str}"
                else:
                    status_text = 'last seen a long time ago'
            else:
                status_text = 'last seen a long time ago'

            # Full user info
            try:
                from telethon.tl.functions.users import GetFullUserRequest
                full_res = await client(GetFullUserRequest(entity))
                fu = full_res.full_user
                bio = getattr(fu, 'about', None) or 'None'
                cg = getattr(fu, 'common_chats_count', None)
                if cg is not None:
                    common_groups_count = str(cg)
            except Exception:
                pass

        elif is_channel or is_group:
            if is_channel:
                status_text = 'Channel'
            else:
                status_text = 'Group'

            try:
                if is_channel or getattr(entity, 'megagroup', False):
                    from telethon.tl.functions.channels import GetFullChannelRequest
                    full = await client(GetFullChannelRequest(entity))
                    fc = full.full_chat
                else:
                    from telethon.tl.functions.messages import GetFullChatRequest
                    full = await client(GetFullChatRequest(peer_id))
                    fc = full.full_chat

                bio = getattr(fc, 'about', None) or 'None'
                members_count = getattr(fc, 'participants_count', 0) or getattr(entity, 'participants_count', 0) or 0
                online_count = getattr(fc, 'online_count', 0) or 0
                linked_id = getattr(fc, 'linked_chat_id', None)
                if linked_id:
                    try:
                        linked_entity = await client.get_entity(linked_id)
                        linked_chat = utils.get_display_name(linked_entity) or str(linked_id)
                    except Exception:
                        linked_chat = str(linked_id)
                has_geo = bool(getattr(fc, 'location', None))
                sm = getattr(fc, 'slowmode_seconds', 0)
                if sm and sm > 0:
                    if sm >= 3600:
                        slowmode = f"{sm // 3600}h"
                    elif sm >= 60:
                        slowmode = f"{sm // 60}m"
                    else:
                        slowmode = f"{sm}s"
            except Exception:
                members_count = getattr(entity, 'participants_count', 0) or 0

            # Creation date from entity.date
            e_date = getattr(entity, 'date', None)
            if e_date:
                ist_dt = e_date + timedelta(hours=5, minutes=30)
                _t = ist_dt.strftime('%I:%M %p').lstrip('0')
                _d = ist_dt.strftime('%d/%m/%Y')
                creation_date = f"{_t} {_d}"
        else:
            # Chat type (basic group)
            try:
                from telethon.tl.functions.messages import GetFullChatRequest
                full = await client(GetFullChatRequest(peer_id))
                fc = full.full_chat
                bio = getattr(fc, 'about', None) or 'None'
                users = full.users
                if users:
                    members_count = len(users)
            except Exception:
                pass

        # Type badge
        if is_bot:
            type_badge = 'Bot'
            type_color = '#9c27b0'
        elif is_user:
            type_badge = 'User'
            type_color = '#2481cc'
        elif is_channel:
            type_badge = 'Channel'
            type_color = '#e67e22'
        else:
            type_badge = 'Group'
            type_color = '#27ae60'

        # Flags
        flags_html = ''
        if is_verified:
            flags_html += '<span style="background: #2481cc; color: white; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 600;">Verified</span> '
        if is_premium:
            flags_html += '<span style="background: #7c3aed; color: white; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 600;">Premium</span> '
        if is_scam:
            flags_html += '<span style="background: #e53935; color: white; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 600;">SCAM</span> '
        if is_fake:
            flags_html += '<span style="background: #e53935; color: white; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 600;">FAKE</span> '
        if is_restricted:
            flags_html += '<span style="background: #ff9800; color: white; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 600;">Restricted</span> '

        # Copy SVG — same as user details page
        c_icon = '<svg xmlns="http://www.w3.org/2000/svg" height="18px" viewBox="0 -960 960 960" width="18px" fill="#707579" class="copy-hover" style="margin-left:8px; cursor:pointer;" onclick="{onclick}"><path d="M360-240q-33 0-56.5-23.5T280-320v-480q0-33 23.5-56.5T360-880h360q33 0 56.5 23.5T800-800v480q0 33-23.5 56.5T720-240H360Zm0-80h360v-480H360v480ZM200-80q-33 0-56.5-23.5T120-160v-560h80v560h440v80H200Zm160-240v-480 480Z"/></svg>'

        def make_copy_icon(text):
            if text and str(text).lower() not in ('none', 'unknown', 'hidden', 'n/a', 'off', '0', '-'):
                safe = str(text).replace("'", "\\'").replace('<br>', ' ')
                return c_icon.replace('{onclick}', f"copyText('{safe}')")
            return ''

        # Build info rows — copyable param controls whether copy icon appears
        def info_row(icon_svg, label, value, copyable=False):
            val_style = 'color: #999; font-weight: 400;' if str(value).lower() in ('none', 'unknown', 'hidden', 'n/a', 'off', '0') else 'color: #2481cc; font-weight: 500;'
            copy_btn = make_copy_icon(value) if copyable else ''
            return f"""<div class="info-item">
                <div class="info-left" style="flex-shrink:0;">
                    <div class="info-icon">{icon_svg}</div>
                    <span class="info-label">{label}</span>
                </div>
                <div style="display:flex; align-items:center; gap:0; overflow:hidden; margin-left:10px;">
                    <span class="info-value" style="{val_style}">{value}</span>
                    <span style="flex-shrink:0;">{copy_btn}</span>
                </div>
            </div>"""

        # Icons
        i_user = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 0 0-16 0"/></svg>'
        i_at = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-4 8"/></svg>'
        i_hash = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-hash"><line x1="4" x2="20" y1="9" y2="9"/><line x1="4" x2="20" y1="15" y2="15"/><line x1="10" x2="8" y1="3" y2="21"/><line x1="16" x2="14" y1="3" y2="21"/></svg>'
        i_phone = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13.832 16.568a1 1 0 0 0 1.213-.303l.355-.465A2 2 0 0 1 17 15h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2A18 18 0 0 1 2 4a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v3a2 2 0 0 1-.8 1.6l-.468.351a1 1 0 0 0-.292 1.233 14 14 0 0 0 6.392 6.384"/></svg>'
        i_info = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>'
        i_clock = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>'
        i_users = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>'
        i_globe = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/></svg>'
        i_link = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>'
        i_shield = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/></svg>'
        i_calendar = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/></svg>'
        i_timer = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="10" x2="14" y1="2" y2="2"/><line x1="12" x2="15" y1="14" y2="11"/><circle cx="12" cy="14" r="8"/></svg>'

        # Build sections based on entity type
        basic_rows = ''
        basic_rows += info_row(i_hash, 'ID', str(peer_id_val), copyable=True)
        if is_bot:
            basic_rows += info_row(i_user, 'Name', first_name, copyable=True)
            basic_rows += info_row(i_at, 'Username', username, copyable=True)
            basic_rows += info_row(i_globe, 'DC ID', dc_id)
        elif is_user:
            basic_rows += info_row(i_user, 'First Name', first_name, copyable=True)
            basic_rows += info_row(i_user, 'Last Name', last_name, copyable=True)
            basic_rows += info_row(i_at, 'Username', username, copyable=True)
            basic_rows += info_row(i_phone, 'Phone', phone, copyable=True)
            basic_rows += info_row(i_globe, 'DC ID', dc_id)
        else:
            # Channel or Group
            basic_rows += info_row(i_user, 'Name', name, copyable=True)
            basic_rows += info_row(i_at, 'Username', username, copyable=True)
            basic_rows += info_row(i_globe, 'DC ID', dc_id)

        bio_copy_btn = make_copy_icon(bio) if bio != 'None' else ''
        bio_text_color = 'color: #999; font-weight: 400;' if bio == 'None' else 'color: #2481cc; font-weight: 500;'
        bio_formatted = bio.replace('\n', '<br>') if bio != 'None' else 'None'
        bio_row = f"""<div class="info-item" style="flex-direction: column; align-items: flex-start; padding: 12px 16px !important; width: 100%; box-sizing: border-box;">
                <div style="width: 100%; display: flex; align-items: center; justify-content: space-between; box-sizing: border-box;">
                    <div class="info-left">
                        <div class="info-icon">{i_info}</div>
                        <span class="info-label">Bio</span>
                    </div>
                    <span style="flex-shrink:0;">{bio_copy_btn}</span>
                </div>
                <div style="width: 100%; margin-top: 6px; white-space: normal; word-break: break-word; overflow-wrap: break-word; font-size: 14px; padding-right: 26px; box-sizing: border-box; {bio_text_color}">{bio_formatted}</div>
            </div>"""
        basic_rows += bio_row
        if is_user and not is_bot:
            basic_rows += info_row(i_clock, 'Status', status_text)
            basic_rows += info_row(i_users, 'Common Groups', common_groups_count)
        if is_channel or is_group:
            basic_rows += info_row(i_users, 'Members', f"{members_count:,}" if members_count else '0')
            if online_count > 0:
                basic_rows += info_row(i_users, 'Online', f"{online_count:,}")
            basic_rows += info_row(i_calendar, 'Created at', creation_date)
            basic_rows += info_row(i_link, 'Linked Chat', linked_chat, copyable=True)
            basic_rows += info_row(i_timer, 'Slowmode', slowmode)

        html = f"""<!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
            <title>Info - {name}</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #f0f2f5; margin: 0; padding: 0; color: #333; }}
                .copy-hover:hover {{ fill: #2481cc !important; opacity: 1; transition: fill 0.2s; }}
                .action-bar {{
                    position: sticky; top: 0; z-index: 100; height: 56px;
                    background: #2481cc;
                    display: flex; align-items: center; padding: 0 10px; gap: 10px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.2);
                    box-sizing: border-box; width: 100%;
                }}
                .back-btn {{
                    background: rgba(255,255,255,0.15); border: none; color: white; width: 34px; height: 34px;
                    border-radius: 50%; display: flex; align-items: center; justify-content: center;
                    cursor: pointer; transition: background 0.15s; outline: none; flex-shrink: 0; padding: 0;
                }}
                .back-btn:hover {{ background: rgba(255,255,255,0.25); }}
                .back-btn svg {{ width: 18px; height: 18px; }}
                .bar-avatar {{ width: 38px; height: 38px; border-radius: 50%; object-fit: cover; background: #eee; flex-shrink: 0; border: 1.5px solid rgba(255,255,255,0.5); }}
                .bar-avatar-fallback {{ width: 38px; height: 38px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 16px; font-weight: 700; color: white; background: rgba(255,255,255,0.2); flex-shrink: 0; border: 1.5px solid rgba(255,255,255,0.5); }}
                .bar-info {{ flex: 1; min-width: 0; display: flex; flex-direction: column; justify-content: center; }}
                .bar-name {{ font-size: 15px; font-weight: 600; color: white; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 1.2; }}
                .bar-type {{ font-size: 12px; color: rgba(255,255,255,0.75); line-height: 1.2; margin-top: 1px; }}

                .photo-viewer {{
                    position: relative; width: 100%; background: #000; overflow: hidden;
                    aspect-ratio: 1 / 1; max-height: 70vh;
                    max-width: 600px; margin: 0 auto;
                }}
                .photo-viewer img {{
                    width: 100%; height: 100%; object-fit: contain; display: block;
                    transition: opacity 0.25s ease;
                }}
                .photo-counter {{
                    position: absolute; top: 10px; left: 10px; padding: 4px 10px;
                    background: rgba(0,0,0,0.5); color: white; border-radius: 12px;
                    font-size: 13px; font-weight: 600; z-index: 10;
                }}
                .photo-download {{
                    position: absolute; bottom: 10px; right: 10px;
                    background: rgba(0,0,0,0.5); border: none; color: white; width: 34px; height: 34px;
                    border-radius: 50%; display: flex; align-items: center; justify-content: center;
                    cursor: pointer; z-index: 10; transition: background 0.15s; padding: 0;
                }}
                .photo-download:hover {{ background: rgba(0,0,0,0.7); }}
                .photo-download svg {{ width: 18px; height: 18px; }}
                .photo-date {{
                    position: absolute; bottom: 10px; left: 10px; padding: 4px 10px;
                    background: rgba(0,0,0,0.5); color: white; border-radius: 12px;
                    font-size: 12px; font-weight: 500; z-index: 10;
                }}
                .photo-nav {{
                    position: absolute; top: 50%; transform: translateY(-50%);
                    background: rgba(0,0,0,0.4); border: none; color: white; width: 34px; height: 34px;
                    border-radius: 50%; display: flex; align-items: center; justify-content: center;
                    cursor: pointer; z-index: 10; transition: background 0.15s; padding: 0;
                }}
                .photo-nav:hover {{ background: rgba(0,0,0,0.6); }}
                .photo-nav svg {{ width: 18px; height: 18px; }}
                .photo-nav.left {{ left: 10px; }}
                .photo-nav.right {{ right: 10px; }}
                .photo-loading {{
                    position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
                    color: rgba(255,255,255,0.7); font-size: 14px;
                }}
                .photo-no {{
                    display: flex; align-items: center; justify-content: center;
                    width: 100%; height: 100%; color: rgba(255,255,255,0.5); font-size: 14px;
                    position: absolute; top: 0; left: 0;
                }}

                .info-container {{ padding: 15px; max-width: 600px; margin: 0 auto; }}
                .info-section {{ margin-bottom: 15px; }}
                .section-header {{ color: #2481cc; font-weight: 500; margin-bottom: 8px; font-size: 14px; margin-left: 12px; }}
                .info-card-box {{ background: white; border-radius: 12px; overflow: hidden; }}
                .info-item {{ padding: 10px 16px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #f0f2f5; min-height: 36px; }}
                .info-item:last-child {{ border-bottom: none; }}
                .info-left {{ display: flex; align-items: center; gap: 14px; flex-shrink: 0; }}
                .info-icon {{ width: 22px; height: 22px; color: #707579; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }}
                .info-label {{ font-size: 14px; color: #333; font-weight: 400; white-space: nowrap; }}
                .info-value {{ font-size: 14px; text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
                .flags {{ margin-top: 8px; display: flex; gap: 6px; flex-wrap: wrap; justify-content: center; }}

                @media (max-width: 600px) {{
                    .info-container {{ padding: 10px; }}
                }}
            </style>
        </head>
        <body>
            <div class="action-bar">
                <button class="back-btn" onclick="window.close(); if(window.history.length>1) window.history.back();" title="Close">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 19-7-7 7-7"/><path d="M19 12H5"/></svg>
                </button>
                <img src="/avatar/{user_id}/{peer_id}" class="bar-avatar" onerror="this.outerHTML='<div class=\\'bar-avatar-fallback\\'>{name_initial}</div>'">
                <div class="bar-info">
                    <div class="bar-name">{name}</div>
                    <div class="bar-type">{type_badge}</div>
                </div>
            </div>

            <div class="photo-viewer" id="photoViewer">
                <div class="photo-loading" id="photoLoading">Loading photos...</div>
                <img id="photoImg" src="" style="display:none;" alt="Profile Photo">
                <div class="photo-no" id="photoNo" style="display:none;">No profile photo</div>
                <div class="photo-counter" id="photoCounter" style="display:none;">1/1</div>
                <button class="photo-download" id="photoDownload" style="display:none;" onclick="downloadCurrentPhoto()" title="Download">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 17V3"/><path d="m6 11 6 6 6-6"/><path d="M19 21H5"/></svg>
                </button>
                <button class="photo-nav left" id="navLeft" style="display:none;" onclick="prevPhoto()">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>
                </button>
                <button class="photo-nav right" id="navRight" style="display:none;" onclick="nextPhoto()">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg>
                </button>
                <div class="photo-date" id="photoDate" style="display:none;"></div>
            </div>

            <div class="info-container">
                <div class="flags" style="margin-bottom: 10px; justify-content: center;">{flags_html}</div>
                <div class="info-section">
                    <div class="info-card-box">
                        {basic_rows}
                    </div>
                </div>
            </div>

            <script>
                const userId = '{user_id}';
                const peerId = '{peer_id}';
                let photos = [];
                let currentIdx = 0;

                async function loadPhotos() {{
                    try {{
                        const res = await fetch(`/api/user/${{userId}}/info/${{peerId}}/photos`);
                        const data = await res.json();
                        document.getElementById('photoLoading').style.display = 'none';
                        if (data.success && data.count > 0) {{
                            photos = data.photos;
                            currentIdx = 0;
                            showPhoto(0);
                        }} else {{
                            document.getElementById('photoNo').style.display = 'flex';
                        }}
                    }} catch(e) {{
                        document.getElementById('photoLoading').textContent = 'Failed to load';
                    }}
                }}

                let loadGen = 0;

                function showPhoto(idx) {{
                    if (photos.length === 0) return;
                    currentIdx = idx;
                    loadGen++;
                    const gen = loadGen;
                    const img = document.getElementById('photoImg');
                    img.style.opacity = '0.3';

                    // Preload in a separate Image to avoid race conditions
                    const preload = new Image();
                    const url = `/api/user/${{userId}}/info/${{peerId}}/photo/${{photos[idx].id}}`;
                    preload.onload = () => {{
                        if (gen !== loadGen) return; // stale, ignore
                        img.src = url;
                        img.style.opacity = '1';
                        img.style.display = 'block';
                    }};
                    preload.onerror = () => {{
                        if (gen !== loadGen) return;
                        img.style.display = 'none';
                    }};
                    preload.src = url;

                    document.getElementById('photoCounter').textContent = `${{idx + 1}}/${{photos.length}}`;
                    document.getElementById('photoCounter').style.display = photos.length > 1 ? 'block' : 'none';
                    document.getElementById('photoDownload').style.display = 'flex';

                    const dateEl = document.getElementById('photoDate');
                    if (photos[idx].date) {{
                        dateEl.textContent = photos[idx].date;
                        dateEl.style.display = 'block';
                    }} else {{
                        dateEl.style.display = 'none';
                    }}

                    if (photos.length > 1) {{
                        document.getElementById('navLeft').style.display = 'flex';
                        document.getElementById('navRight').style.display = 'flex';
                    }}
                }}

                function prevPhoto() {{ if (photos.length > 1) showPhoto(currentIdx > 0 ? currentIdx - 1 : photos.length - 1); }}
                function nextPhoto() {{ if (photos.length > 1) showPhoto(currentIdx < photos.length - 1 ? currentIdx + 1 : 0); }}

                function downloadCurrentPhoto() {{
                    if (photos.length === 0) return;
                    const a = document.createElement('a');
                    a.href = `/api/user/${{userId}}/info/${{peerId}}/photo/${{photos[currentIdx].id}}?download=1`;
                    a.download = `photo_${{currentIdx + 1}}.jpg`;
                    a.click();
                }}

                // Swipe support
                let touchStartX = 0;
                document.getElementById('photoViewer').addEventListener('touchstart', e => {{ touchStartX = e.touches[0].clientX; }});
                document.getElementById('photoViewer').addEventListener('touchend', e => {{
                    const diff = touchStartX - e.changedTouches[0].clientX;
                    if (Math.abs(diff) > 50) {{
                        if (diff > 0) nextPhoto(); else prevPhoto();
                    }}
                }});

                loadPhotos();
            </script>
            <script>
                function copyText(text) {{
                    navigator.clipboard.writeText(text).catch(() => {{
                        const ta = document.createElement('textarea');
                        ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
                        document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove();
                    }});
                }}
            </script>
        </body>
        </html>"""

        return web.Response(text=html, content_type='text/html')

    except Exception as e:
        logger.error(f'Error rendering peer info: {e}', exc_info=True)
        return web.Response(text=f'Error: {e}', status=500)

async def handle_peer_photos_api(request):
    """API to list all profile photos of a peer."""
    try:
        user_id = int(request.match_info.get('user_id'))
        peer_id_str = request.match_info.get('peer_id')
        peer_id = int(peer_id_str) if peer_id_str.lstrip('-').isdigit() else peer_id_str

        active_sessions = request.app['active_sessions']
        session = active_sessions.get(user_id)
        if not session or not session.client or not session.client.is_connected():
            return web.json_response({'success': False, 'error': 'Session not found'})

        client = session.client
        entity = await client.get_entity(peer_id)

        # get_profile_photos works for users, channels, and groups
        all_photos = await client.get_profile_photos(entity, limit=100)

        photos_list = []
        for i, photo in enumerate(all_photos):
            pdate = ''
            if hasattr(photo, 'date') and photo.date:
                ist_dt = photo.date + timedelta(hours=5, minutes=30)
                pdate = ist_dt.strftime('%I:%M %p %d/%m/%Y').lstrip('0')
            photos_list.append({'id': str(photo.id), 'index': i, 'date': pdate})

        # If no photos found via get_profile_photos, try fallback
        if not photos_list and getattr(entity, 'photo', None):
            photos_list.append({'id': '0', 'index': 0, 'date': ''})

        return web.json_response({'success': True, 'count': len(photos_list), 'photos': photos_list})

    except Exception as e:
        logger.error(f'Error listing peer photos: {e}')
        return web.json_response({'success': False, 'error': str(e)})

async def handle_peer_photo_download(request):
    """API to download a specific profile photo by photo_id."""
    try:
        user_id = int(request.match_info.get('user_id'))
        peer_id_str = request.match_info.get('peer_id')
        peer_id = int(peer_id_str) if peer_id_str.lstrip('-').isdigit() else peer_id_str
        photo_id = request.match_info.get('photo_id')

        active_sessions = request.app['active_sessions']
        session = active_sessions.get(user_id)
        if not session or not session.client or not session.client.is_connected():
            return web.Response(status=404)

        client = session.client
        entity = await client.get_entity(peer_id)

        import io
        out = io.BytesIO()

        if photo_id == '0':
            # Fallback: download current profile photo
            await client.download_profile_photo(entity, out, download_big=True)
        else:
            # Get all photos and find by ID
            all_photos = await client.get_profile_photos(entity, limit=100)
            target_photo = None
            for p in all_photos:
                if str(p.id) == photo_id:
                    target_photo = p
                    break
            if target_photo:
                await client.download_media(target_photo, out)
            else:
                # Fallback to current profile photo
                await client.download_profile_photo(entity, out, download_big=True)

        out.seek(0)
        data = out.read()
        if not data:
            return web.Response(status=404)

        is_download = request.query.get('download') == '1'
        headers = {}
        if is_download:
            headers['Content-Disposition'] = f'attachment; filename="photo.jpg"'

        return web.Response(body=data, content_type='image/jpeg', headers=headers)

    except Exception as e:
        logger.error(f'Error downloading peer photo: {e}')
        return web.Response(status=500)

def register_chat_routes(app):
    from vc_viewer import handle_vc_page
    app.router.add_get('/user/{user_id}/vc/{peer_id}', handle_vc_page)
    app.router.add_get('/user/{user_id}/info/{peer_id}', handle_peer_info_page)
    app.router.add_get('/api/user/{user_id}/info/{peer_id}/photos', handle_peer_photos_api)
    app.router.add_get('/api/user/{user_id}/info/{peer_id}/photo/{photo_id}', handle_peer_photo_download)
    app.router.add_get('/user/{user_id}/chat/{peer_id}', handle_chat_page)
    app.router.add_get('/api/user/{user_id}/chat/{peer_id}/messages', handle_chat_messages_api)
    app.router.add_get('/api/user/{user_id}/chat/{peer_id}/media/{message_id}', handle_chat_media_api)
    app.router.add_get('/api/user/{user_id}/sticker_link', handle_sticker_link_api)
