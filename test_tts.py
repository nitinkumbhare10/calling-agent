import os
import asyncio
from dotenv import load_dotenv
load_dotenv(override=True)
import config
from livekit.plugins import cartesia

async def main():
    try:
        print('Testing Cartesia...')
        tts = cartesia.TTS(model=config.CARTESIA_MODEL, voice=config.CARTESIA_VOICE, language=config.CARTESIA_LANGUAGE)
        print('Cartesia TTS instantiated successfully.')
    except Exception as e:
        print('Cartesia error:', e)

asyncio.run(main())
