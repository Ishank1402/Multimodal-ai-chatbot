# pyrefly: ignore [missing-import]
import httpx
import asyncio

async def test():
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            'http://127.0.0.1:8000/chat/audio', 
            data={'session_id': 'test'}, 
            files={'audio': ('test.ogg', b'dummy audio data', 'audio/ogg')}
        )
        print(resp.text)

asyncio.run(test())
