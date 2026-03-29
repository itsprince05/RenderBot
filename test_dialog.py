import asyncio
from telethon import TelegramClient
from telethon.tl.functions.messages import GetPeerDialogsRequest
from session_helper import SessionManager

async def main():
    sm = SessionManager()
    sessions = sm.get_all_sessions()
    cl = sm.get_client(sessions[0].phone)
    await cl.connect()
    
    async for d in cl.iter_dialogs(limit=1):
        peer = d.entity
        print("Peer:", peer.id)
        pi = await cl.get_input_entity(peer)
        print("Input Peer:", pi)
        res = await cl(GetPeerDialogsRequest(peers=[pi]))
        print(res.dialogs[0])
        print("read outbox max id:", res.dialogs[0].read_outbox_max_id)
        break
    await cl.disconnect()

asyncio.run(main())
