import logging
import asyncio
from aiohttp import web
from telethon import utils
import os
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

IST_OFFSET = timedelta(hours=5, minutes=30)

def to_ist(dt_or_ts):
    """Convert UTC datetime/timestamp to IST datetime"""
    if isinstance(dt_or_ts, datetime):
        return dt_or_ts + IST_OFFSET
    return datetime.utcfromtimestamp(dt_or_ts) + IST_OFFSET

def format_full_date(ts):
    """Format timestamp to full date like PHP's formatFullDate"""
    if not ts:
        return "Never"
    try:
        return to_ist(ts).strftime('%I:%M:%S %p %d/%m/%Y')
    except:
        return "Never"

async def handle_vc_page(request):
    try:
        user_id = int(request.match_info.get('user_id'))
        peer_id_str = request.match_info.get('peer_id')
        peer_id = int(peer_id_str) if peer_id_str.lstrip('-').isdigit() else peer_id_str
        
        active_sessions = request.app['active_sessions']
        session = active_sessions.get(user_id)
        
        if not session or not session.client or not session.client.is_connected():
            return web.Response(text='Session not found or disconnected', status=404)
        
        is_ajax = request.query.get('ajax') == '1'
        
        try:
            entity = await session.client.get_entity(peer_id)
            title = utils.get_display_name(entity) or 'Unknown'
            name = title
            name_initial = name[0].upper() if name else '?'
            
            # Fetch full info to get call object
            if getattr(entity, 'broadcast', False) or getattr(entity, 'megagroup', False):
                from telethon.tl.functions.channels import GetFullChannelRequest
                full = await session.client(GetFullChannelRequest(entity))
            else:
                from telethon.tl.functions.messages import GetFullChatRequest
                full = await session.client(GetFullChatRequest(peer_id))
                
            call_object = full.full_chat.call
            total_count = 0
            
            content_html = ''
            
            if call_object:
                from telethon.tl.functions.phone import GetGroupCallRequest
                call_data = await session.client(GetGroupCallRequest(call=call_object, limit=100))
                
                participants = call_data.participants
                users = call_data.users
                chats = call_data.chats
                
                total_count = len(participants)
                
                user_map = {u.id: u for u in users}
                for c in chats:
                    user_map[c.id] = c
                
                active_list = []
                invited_list = []
                
                for p in participants:
                    if getattr(p, 'left', False):
                        invited_list.append(p)
                    else:
                        active_list.append(p)
                
                final_queue = []
                for p in active_list: final_queue.append({'data': p, 'type': 'active'})
                for p in invited_list: final_queue.append({'data': p, 'type': 'invited'})
                
                has_invited_header_shown = False
                
                if not final_queue:
                    content_html += "<p style='text-align:center; padding:20px; color:#888'>No Active Speakers.</p>"
                else:
                    for index, item in enumerate(final_queue):
                        p = item['data']
                        is_active_section = item['type'] == 'active'
                        
                        if not is_active_section and not has_invited_header_shown:
                            content_html += "<div class='section-title'>Invited / Recently Left</div>"
                            has_invited_header_shown = True
                            
                        # Try to get id
                        pid = None
                        peer = getattr(p, 'peer', None)
                        if peer:
                            pid = utils.get_peer_id(peer)
                        
                        if not pid and hasattr(p, 'user_id'):
                            pid = p.user_id
                        
                        user = user_map.get(pid, None)
                        if user:
                            first = getattr(user, 'first_name', getattr(user, 'title', 'User')) or 'User'
                            last = getattr(user, 'last_name', '') or ''
                        else:
                            first = 'User'
                            last = ''
                        p_name = f'{first} {last}'.strip() or f'Unknown ({pid})'
                        username = getattr(user, 'username', '') if user else ''
                        if username: username = f'@{username}'
                        
                        active_date = getattr(p, 'active_date', None)
                        is_speaking = False
                        last_spoke_short = '-'
                        last_spoke_full = 'Never'
                        if active_date:
                            try:
                                ist_dt = to_ist(active_date)
                                last_spoke_short = ist_dt.strftime('%I:%M:%S %p')
                                last_spoke_full = format_full_date(active_date)
                                ts = active_date.timestamp() if isinstance(active_date, datetime) else int(active_date)
                                is_speaking = ts > time.time() - 3
                            except:
                                pass
                        
                        is_muted = getattr(p, 'muted', False)
                        hand_raised = getattr(p, 'raised_hand', False)
                        can_self_unmute = getattr(p, 'can_self_unmute', False)
                        has_video = getattr(p, 'video', False)
                        is_screen_sharing = getattr(p, 'presentation', False)
                        
                        is_invited = not is_active_section
                        
                        join_date = getattr(p, 'date', None)
                        join_time_short = '-'
                        join_time_full = 'Unknown'
                        if join_date:
                            try:
                                ist_jdt = to_ist(join_date)
                                join_time_short = ist_jdt.strftime('%I:%M:%S %p')
                                join_time_full = format_full_date(join_date)
                            except:
                                pass
                        volume = f"{p.volume/100}%" if getattr(p, 'volume', None) else '100%'
                        cam_status = 'ON' if has_video else 'OFF'
                        sc_status = 'ON' if is_screen_sharing else 'OFF'
                        hand_status = 'Raised' if hand_raised else 'Down'
                        
                        # Mic status text
                        mute_text = "Mic Open"
                        if is_muted:
                            if can_self_unmute:
                                mute_text = "Self Muted"
                            else:
                                mute_text = "Force Muted by Admin"
                        
                        # About
                        about = getattr(user, 'about', '-') if user else '-'
                        if not about: about = '-'
                        
                        initial = p_name[0].upper() if p_name else '?'
                        colors = ['#FF5722', '#E91E63', '#9C27B0', '#673AB7', '#3F51B5', '#2196F3', '#00BCD4', '#009688', '#4CAF50', '#8BC34A', '#FFFA00', '#FFC107', '#FF9800', '#FF5722', '#795548', '#607D8B']
                        color_index = abs(pid or 0) % len(colors)
                        bg = colors[color_index]
                        txt_color = '#333' if bg in ['#FFFA00', '#8BC34A', '#FFC107'] else '#fff'
                        
                        photo_html = f"<div class='user-pic' style='display:inline-flex; align-items:center; justify-content:center; background:{bg}; color:{txt_color}; font-size:18px; font-weight:bold; border-radius:50%; width:40px; height:40px; flex-shrink:0'>{initial}</div>"
                        if user:
                            photo_html = f"<img src='/avatar/{user_id}/{pid}' class='user-pic' onerror=\"this.outerHTML='<div class=\\'user-pic\\' style=\\'display:inline-flex; align-items:center; justify-content:center; background:{bg}; color:{txt_color}; font-size:18px; font-weight:bold; border-radius:50%; width:40px; height:40px; flex-shrink:0\\'>{initial}</div>'\">"
                        
                        # Icons - exact from PHP
                        icon_invited = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-user-round-plus"><path d="M2 21a8 8 0 0 1 13.292-6"/><circle cx="10" cy="8" r="5"/><path d="M19 16v6"/><path d="M22 19h-6"/></svg>'
                        icon_mic_on = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19v3"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><rect x="9" y="2" width="6" height="13" rx="3"/></svg>'
                        icon_mic_off = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19v3"/><path d="M15 9.34V5a3 3 0 0 0-5.68-1.33"/><path d="M16.95 16.95A7 7 0 0 1 5 12v-2"/><path d="M18.89 13.23A7 7 0 0 0 19 12v-2"/><path d="m2 2 20 20"/><path d="M9 9v3a3 3 0 0 0 5.12 2.12"/></svg>'
                        icon_speaking = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4.702a.705.705 0 0 0-1.203-.498L6.413 7.587A1.4 1.4 0 0 1 5.416 8H3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2.416a1.4 1.4 0 0 1 .997.413l3.383 3.384A.705.705 0 0 0 11 19.298z"/><path d="M16 9a5 5 0 0 1 0 6"/><path d="M19.364 18.364a9 9 0 0 0 0-12.728"/></svg>'
                        icon_hand = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 11V6a2 2 0 0 0-2-2v0a2 2 0 0 0-2 2v0"/><path d="M14 10V4a2 2 0 0 0-2-2v0a2 2 0 0 0-2 2v2"/><path d="M10 10.5V6a2 2 0 0 0-2-2v0a2 2 0 0 0-2 2v8"/><path d="M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15"/></svg>'
                        
                        mi_join = '<svg class="mini-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 21a8 8 0 0 1 13.292-6"/><circle cx="10" cy="8" r="5"/><path d="M19 16v6"/><path d="M22 19h-6"/></svg>'
                        mi_spoke = '<svg class="mini-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4.702a.705.705 0 0 0-1.203-.498L6.413 7.587A1.4 1.4 0 0 1 5.416 8H3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2.416a1.4 1.4 0 0 1 .997.413l3.383 3.384A.705.705 0 0 0 11 19.298z"/><path d="M16 9a5 5 0 0 1 0 6"/><path d="M19.364 18.364a9 9 0 0 0 0-12.728"/></svg>'
                        mi_vol = '<svg class="mini-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4.702a.705.705 0 0 0-1.203-.498L6.413 7.587A1.4 1.4 0 0 1 5.416 8H3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2.416a1.4 1.4 0 0 1 .997.413l3.383 3.384A.705.705 0 0 0 11 19.298z"/><path d="M16 9a5 5 0 0 1 0 6"/><path d="M19.364 18.364a9 9 0 0 0 0-12.728"/></svg>'
                        mi_cam = '<svg class="mini-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m16 13 5.223 3.482a.5.5 0 0 0 .777-.416V7.87a.5.5 0 0 0-.752-.432L16 10.5"/><rect x="2" y="6" width="14" height="12" rx="2"/></svg>'
                        mi_screen = '<svg class="mini-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15.033 9.44a.647.647 0 0 1 0 1.12l-4.065 2.352a.645.645 0 0 1-.968-.56V7.648a.645.645 0 0 1 .967-.56z"/><path d="M12 17v4"/><path d="M8 21h8"/><rect x="2" y="3" width="20" height="14" rx="2"/></svg>'
                        btn_icon = '<svg class="mini-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 5h8"/><path d="M3 12h8"/><path d="M3 19h8"/><path d="m15 8 3-3 3 3"/><path d="m15 16 3 3 3-3"/></svg>'
                        
                        if is_invited:
                            status_icon = icon_invited
                            status_class = 'c-grey'
                        else:
                            if is_speaking:
                                status_icon = icon_speaking
                                status_class = 'c-green wave-anim'
                            elif hand_raised:
                                status_icon = icon_hand
                                status_class = 'c-purple'
                            elif is_muted:
                                status_icon = icon_mic_off
                                status_class = 'c-grey' if can_self_unmute else 'c-red'
                            else:
                                status_icon = icon_mic_on
                                status_class = 'c-green'
                                
                        row_id = f'p-{index}'
                        
                        # About section
                        about_html = ''
                        if about and about != '-':
                            about_html = f"<span style='color:#000; display:block; margin-bottom:10px; border-bottom:1px solid #e0e0e0; padding-bottom:5px;'>{about}</span>"
                        
                        # Build RAW DATA section
                        skip_keys = ['peer', 'date', 'active_date', 'volume', 'source', 'about', 'muted', 'can_self_unmute', 'video', 'presentation', 'raised_hand']
                        raw_lines = ''
                        try:
                            for attr_name in dir(p):
                                if attr_name.startswith('_') or attr_name in skip_keys:
                                    continue
                                try:
                                    val = getattr(p, attr_name, None)
                                    if callable(val):
                                        continue
                                    if isinstance(val, bool):
                                        val = 'True' if val else 'False'
                                    elif isinstance(val, (list, dict, tuple)):
                                        import json
                                        val = json.dumps(val, default=str)
                                    elif val is None:
                                        continue
                                    raw_lines += f"<span class='k'>{attr_name}:</span> <span class='v'>{val}</span>\n"
                                except:
                                    pass
                        except:
                            pass
                        
                        raw_data_html = ''
                        if raw_lines:
                            raw_data_html = f"""<div style='border-top:1px dashed #ccc; margin:8px 0;'></div><span style='color:#777; font-weight:bold; display:block; margin-bottom:5px;'>RAW DATA:</span>{raw_lines}"""
                        
                        content_html += f"""<div class='user-wrap'>
                            <div class='user-row'>
                                {photo_html}
                                <div class='info'>
                                    <div class='line-1'><div class='name'>{p_name}</div></div>
                                    <div class='line-2'>{pid} {(' | ' + username) if username else ''}</div>
                                    <div class='stats-grid'>
                                        <span class='stat-pill'>{mi_join} {join_time_short}</span>
                                        <span class='stat-pill'>{mi_cam} {cam_status}</span>     
                                        <span class='stat-pill'>{mi_screen} {sc_status}</span>   
                                        <span class='stat-pill'>{mi_spoke} {last_spoke_short}</span>      
                                        <span class='stat-pill'>{mi_vol} {volume}</span>            
                                        <button id='btn-{row_id}' class='more-toggle' onclick='toggleDetails("{row_id}")'>{btn_icon} More</button> 
                                    </div>
                                </div>
                                <div class='status-icon {status_class}'>{status_icon}</div>
                            </div>
                            <div id='details-{row_id}' class='details-box'>{about_html}<span class='k'>Volume:</span> <span class='v-hl'>{volume}</span>
<span class='k'>Joined At:</span> <span class='v'>{join_time_full}</span>
<span class='k'>Last Spoke:</span> <span class='v'>{last_spoke_full}</span>
<span class='k'>Mic Status:</span> <span class='v'>{mute_text}</span>
<span class='k'>Camera:</span> <span class='v'>{cam_status}</span>
<span class='k'>Screen Share:</span> <span class='v'>{sc_status}</span>
<span class='k'>Hand Raised:</span> <span class='v'>{hand_status}</span>
<span class='k'>Source ID:</span> <span class='v'>{getattr(p, 'source', '-')}</span>
{raw_data_html}</div>
                        </div>"""
            else:
                 content_html += "<div style='text-align:center; padding:20px; color:red'>No Active Voice Chat.</div>"
                 
            status_text = f"{total_count} members"
                 
            if is_ajax:
                return web.Response(text=content_html + f"<script>if(document.getElementById('header-text-span')) document.getElementById('header-text-span').innerText = '{total_count} members';</script>", content_type='text/html')
                
            i_chat = '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>'
            i_play = '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>'
            
            html = f"""<!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
                <title>VC - {name}</title>
                <link rel="preconnect" href="https://fonts.googleapis.com">
                <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
                <link href="https://fonts.googleapis.com/css2?family=PT+Serif:wght@400;700&display=swap" rel="stylesheet">
                <style>
                    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #f0f2f5; margin: 0; padding: 0; color: #333; }}
                    #live-content {{ max-width: 800px; margin: 0 auto; }}
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
                    .header-actions {{ display: flex; align-items: center; gap: 6px; }}
                    .refresh-badge {{
                        width: 34px; height: 34px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
                        font-size: 14px; font-weight: 700; color: #fff; cursor: pointer; transition: background 0.2s; flex-shrink: 0;
                        font-family: -apple-system, sans-serif; border: none; padding: 0;
                    }}
                    .toggle-btn {{
                        width: 34px; height: 34px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
                        cursor: pointer; transition: background 0.2s; flex-shrink: 0; border: none; padding: 0;
                    }}
                    .toggle-btn svg {{ width: 22px; height: 22px; stroke: #fff; }}
                    .refresh-on {{ background: rgb(76, 217, 100); }}
                    .refresh-off {{ background: rgb(204, 204, 204); }}

                    .section-title {{ padding: 0px 15px 5px 15px; font-size: 12px; font-weight: 700; color: #666; letter-spacing: 0.5px; }}
                    .user-wrap {{ border-bottom: 1px solid #e0e0e0; margin: 0; }}
                    .user-row {{ display: flex; background: #fff; padding: 5px 15px; align-items: center; transition: background 0.2s; min-height: 50px; }}
                    .user-row:active {{ background: #f5f5f5; }}
                    .info {{ flex-grow: 1; min-width: 0; }}
                    .line-1 {{ display: flex; align-items: center; width: 100%; }}
                    .name {{ font-weight: 600; font-size: 15px; color: #222; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; text-overflow: ellipsis; line-height: 1.3; word-break: break-word; }}
                    .line-2 {{ font-size: 11px; color: #888; margin-bottom: 2px; font-family: monospace; }}
                    .stats-grid {{ display: grid; grid-template-columns: auto auto auto; column-gap: 20px; row-gap: 2px; margin-top: 2px; justify-content: start; }}
                    .stat-pill {{ display: flex; align-items: center; color: #555; white-space: nowrap; font-size: 11px; }}
                    .user-pic {{ width: 40px; height: 40px; border-radius: 50%; object-fit: cover; margin-right: 12px; background: #eee; flex-shrink: 0; }}
                    .mini-icon {{ width: 14px; height: 14px; stroke: #999; margin-right: 4px; }}
                    .more-toggle {{ background: none; border: none; color: #3390ec; cursor: pointer; padding: 0; display: flex; align-items: center; font-size: 11px; font-weight: 500; gap: 2px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; justify-self: start; }}
                    .details-box {{ display: none; background: #fff; padding: 10px; border-radius: 0; font-size: 12px; color: #333; font-family: monospace; border-top: 1px solid #e0e0e0; white-space: pre-wrap; word-wrap: break-word; text-align: left; }}
                    .k {{ color: #666; font-weight: bold; }} .v {{ color: #333; }} .v-hl {{ color: #007bff; font-weight: bold; }} 
                    .status-icon {{ margin-left: 10px; display: flex; align-items: center; justify-content: center; width: 34px; height: 34px; border-radius: 50%; flex-shrink: 0; position: relative; }}
                    .c-green {{ color: #28a745; background: #e8f5e9; }}
                    .c-grey {{ color: #9e9e9e; background: #f5f5f5; border: 1px solid #eee; }}
                    .c-red {{ color: #d32f2f; background: #ffebee; }}
                    .c-purple {{ color: #9c27b0; background: #f3e5f5; }}
                    .wave-anim {{ z-index: 1; }}
                    .wave-anim::after {{ content: ''; position: absolute; top: -5px; left: -5px; right: -5px; bottom: -5px; border-radius: 50%; border: 2px solid #28a745; z-index: -1; opacity: 0; animation: ripple 1.5s infinite ease-out; }}
                    @keyframes ripple {{ 0% {{ transform: scale(0.8); opacity: 0.8; }} 50% {{ opacity: 0.5; }} 100% {{ transform: scale(1.4); opacity: 0; }} }}
                    .lucide {{ width: 18px; height: 18px; }}
                </style>
                <script>
                    function toggleDetails(id) {{
                        var el = document.getElementById('details-' + id);
                        var btn = document.getElementById('btn-' + id);
                        var iconUp = '<svg class="mini-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 5h8"/><path d="M3 12h8"/><path d="M3 19h8"/><path d="m15 8 3-3 3 3"/><path d="m15 16 3 3 3-3"/></svg>';
                        var iconDown = '<svg class="mini-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 5h8"/><path d="M3 12h8"/><path d="M3 19h8"/><path d="m15 5 3 3 3-3"/><path d="m15 19 3-3 3 3"/></svg>';
                        if (el.style.display === 'block') {{ el.style.display = 'none'; btn.innerHTML = iconUp + ' More'; }} 
                        else {{ el.style.display = 'block'; btn.innerHTML = iconDown + ' Less'; }}
                    }}

                    document.addEventListener("DOMContentLoaded", function() {{
                        const counterBadge = document.getElementById('counterBadge');
                        const toggleBtn = document.getElementById('toggleBtn');
                        const contentArea = document.getElementById('live-content');

                        var iconToggleOff = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="12" r="3"/><rect width="20" height="14" x="2" y="5" rx="7"/></svg>';
                        var iconToggleOn = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="15" cy="12" r="3"/><rect width="20" height="14" x="2" y="5" rx="7"/></svg>';

                        let isPlaying = true;
                        let countdownTimer = null;
                        let currentCount = 3;

                        function fetchData() {{
                            const url = new URL(window.location.href);
                            url.searchParams.set('ajax', '1');
                            fetch(url)
                                .then(response => response.text())
                                .then(html => {{
                                    contentArea.innerHTML = "";
                                    contentArea.innerHTML = html;
                                    const scripts = contentArea.querySelectorAll('script');
                                    scripts.forEach(script => {{
                                        try {{ eval(script.innerText); }} catch(e) {{}}
                                    }});
                                }})
                                .catch(err => console.error('Refresh Error:', err));
                        }}

                        function startCountdown() {{
                            stopCountdown();
                            currentCount = 3;
                            counterBadge.textContent = currentCount;
                            countdownTimer = setInterval(function() {{
                                currentCount--;
                                counterBadge.textContent = currentCount;
                                if (currentCount <= 0) {{
                                    fetchData();
                                    currentCount = 3;
                                    counterBadge.textContent = currentCount;
                                }}
                            }}, 1000);
                        }}

                        function stopCountdown() {{
                            if (countdownTimer) {{
                                clearInterval(countdownTimer);
                                countdownTimer = null;
                            }}
                        }}

                        function updateUI() {{
                            if (isPlaying) {{
                                counterBadge.className = 'refresh-badge refresh-on';
                                toggleBtn.className = 'toggle-btn refresh-on';
                                toggleBtn.innerHTML = iconToggleOn;
                                startCountdown();
                            }} else {{
                                counterBadge.className = 'refresh-badge refresh-off';
                                counterBadge.textContent = 'Off';
                                toggleBtn.className = 'toggle-btn refresh-off';
                                toggleBtn.innerHTML = iconToggleOff;
                                stopCountdown();
                            }}
                        }}

                        window.togglePlay = function() {{ 
                            isPlaying = !isPlaying; 
                            updateUI(); 
                        }};
                        updateUI();
                    }});
                </script>
            </head>
            <body>
            <div class="action-bar">
                <button class="back-btn" onclick="if(window.history.length>1)window.history.back();else window.close();" title="Back">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 19-7-7 7-7"/><path d="M19 12H5"/></svg>
                </button>
                <img src="/avatar/{user_id}/{peer_id}" class="avatar" onerror="this.outerHTML='<div class=\\'avatar\\' style=\\'background: rgba(255,255,255,0.2); display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; font-size: 18px; width:42px; height:42px; border-radius:50%; flex-shrink:0; border: 1.5px solid rgba(255,255,255,0.5);\\' >{name_initial}</div>'">
                <div class="user-info">
                    <div class="user-title">{name}</div>
                    <div class="user-status" id="header-text-span">{status_text}</div>
                </div>
                <div class="header-actions">
                    <div class="refresh-badge refresh-on" id="counterBadge">3</div>
                    <button class="toggle-btn refresh-on" id="toggleBtn" onclick="togglePlay()"></button>
                </div>
            </div>
            <div id="live-content">
                {content_html}
            </div>
            </body>
            </html>"""
            
            return web.Response(text=html, content_type='text/html')
            
        except Exception as e:
            logger.error(f'Error rendering VC: {e}')
            return web.Response(text=f'Error rendering VC: {e}', status=500)
    except Exception as e:
        logger.error(f'Outer VC error: {e}')
        return web.Response(text=f'Server Error: {e}', status=500)
