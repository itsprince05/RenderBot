import asyncio
from telethon import TelegramClient
from session_helper import SessionManager
from telethon.tl.functions.messages import GetPeerDialogsRequest

async def main():
    sm = SessionManager()
    sessions = sm.get_all_sessions()
    cl = sm.get_client(sessions[0].phone)
    await cl.connect()
    
    async for d in cl.iter_dialogs(limit=3):
        print(f"Dialog: {d.name}, read_outbox_max_id: {d.dialog.read_outbox_max_id}, last_msg_id: {d.message.id}")
        pi = await cl.get_input_entity(d.entity)
        res = await cl(GetPeerDialogsRequest(peers=[pi]))
        print(f"   API read_outbox_max_id: {res.dialogs[0].read_outbox_max_id}")
                
    await cl.disconnect()

asyncio.run(main())
