from highrise import BaseBot, User, Position
from highrise.models import SessionMetadata
import asyncio
import aiohttp
import os
from typing import Dict, List, Optional
from datetime import datetime

class MusicBot(BaseBot):
    def __init__(self):
        super().__init__()
        self.backend_url = os.getenv('MUSIC_API_URL', 'http://localhost:5000')
        self.admins: List[str] = []
        self.session: Optional[aiohttp.ClientSession] = None

    async def on_start(self, session_metadata: SessionMetadata) -> None:
        print("🎵 Music Bot is now online!")
        self.session = aiohttp.ClientSession()
        await asyncio.sleep(2)
        await self.send_welcome()

    async def send_welcome(self):
        welcome = """
╔════════════════════════════╗
║  🎵 LIVE MUSIC RADIO ROOM 🎵  ║
╚════════════════════════════╝

🎶 LISTEN TO LIVE MUSIC 24/7!
📻 Everyone hears the same song
🎧 Join anytime - never miss a beat
⭐ Type /help to get started

Welcome to the radio!
        """
        await self.highrise.chat(welcome)

    async def on_user_join(self, user: User, position: Position) -> None:
        await asyncio.sleep(1)
        await self.highrise.chat(f"🎵 Welcome {user.username} to the music room!")

        try:
            async with self.session.get(f"{self.backend_url}/api/nowplaying") as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('playing'):
                        track = data['track']
                        await self.highrise.chat(f"🎵 Now Playing: {track['title']}")
                        await self.highrise.chat(f"🎧 Listen at: {self.backend_url}/api/stream")
        except:
            pass

    async def on_chat(self, user: User, message: str) -> None:
        msg = message.lower().strip()

        if msg == "/help" or msg == "/commands":
            await self.show_help()

        elif msg == "/nowplaying" or msg == "/np":
            await self.show_now_playing()

        elif msg == "/queue":
            await self.show_queue()

        elif msg == "/stream" or msg == "/listen":
            await self.show_stream_url()

        elif msg.startswith("/request "):
            query = message[9:].strip()
            await self.request_song(user, query)

        elif msg == "/skip" and self.is_admin(user):
            await self.skip_song()

        elif msg == "/pause" and self.is_admin(user):
            await self.pause_playback()

        elif (msg == "/resume" or msg == "/next") and self.is_admin(user):
            await self.resume_playback()

    def is_admin(self, user: User) -> bool:
        return user.username in self.admins

    async def show_help(self):
        help_text = """
🎵 MUSIC BOT COMMANDS 🎵

🎧 LISTENING:
/nowplaying or /np - Current song
/queue - Upcoming songs
/stream - Get stream URL to listen

🎶 REQUESTS:
/request <song name or URL>
  - Request a YouTube song
  - Examples:
    /request Despacito
    /request https://youtube.com/watch?v=...

🎛️ ADMIN CONTROLS:
/skip - Skip to next song
/pause - Pause broadcast
/resume or /next - Resume playback

Stream URL: {backend}/api/stream
        """.format(backend=self.backend_url)
        await self.highrise.chat(help_text)

    async def show_now_playing(self):
        try:
            async with self.session.get(f"{self.backend_url}/api/nowplaying") as response:
                if response.status == 200:
                    data = await response.json()

                    if data.get('playing'):
                        track = data['track']
                        paused = data.get('paused', False)
                        listeners = data.get('listeners', 0)
                        queue_size = data.get('queue_size', 0)

                        status = "⏸️ PAUSED" if paused else "▶️ NOW PLAYING"

                        now_playing_text = f"""
{status}

🎵 {track['title']}
👤 {track['artist']}
👂 {listeners} listeners
📋 {queue_size} songs in queue

🎧 Stream: {self.backend_url}/api/stream
                        """
                        await self.highrise.chat(now_playing_text)
                    else:
                        await self.highrise.chat("⏸️ Nothing playing right now. Request a song!")
                else:
                    await self.highrise.chat("❌ Could not get current track info")
        except Exception as e:
            await self.highrise.chat(f"❌ Error: {str(e)}")

    async def show_queue(self):
        try:
            async with self.session.get(f"{self.backend_url}/api/queue") as response:
                if response.status == 200:
                    data = await response.json()

                    current = data.get('current')
                    queue = data.get('queue', [])

                    queue_text = "📋 MUSIC QUEUE 📋\n\n"

                    if current:
                        queue_text += f"▶️ NOW: {current['title']}\n\n"

                    if queue:
                        queue_text += "NEXT UP:\n"
                        for i, track in enumerate(queue[:5], 1):
                            queue_text += f"{i}. {track['title']}\n"

                        if len(queue) > 5:
                            queue_text += f"\n...and {len(queue) - 5} more songs"
                    else:
                        queue_text += "Queue is empty! Request songs!"

                    await self.highrise.chat(queue_text)
                else:
                    await self.highrise.chat("❌ Could not get queue")
        except Exception as e:
            await self.highrise.chat(f"❌ Error: {str(e)}")

    async def show_stream_url(self):
        stream_text = f"""
🎧 LIVE STREAM URL 🎧

{self.backend_url}/api/stream

Copy this URL and paste it into:
• Your web browser
• Media player (VLC, etc.)
• Music apps that support streaming

Everyone hears the same song!
        """
        await self.highrise.chat(stream_text)

    async def request_song(self, user: User, query: str):
        try:
            await self.highrise.chat(f"🔍 Searching for: {query}...")

            async with self.session.post(
                f"{self.backend_url}/api/request",
                data={'query': query}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    track = data['track']
                    position = data['position']

                    success_text = f"""
✅ SONG REQUESTED!

🎵 {track['title']}
👤 {track['artist']}
📍 Position #{position} in queue

Requested by: {user.username}
                    """
                    await self.highrise.chat(success_text)
                else:
                    error_data = await response.json()
                    await self.highrise.chat(f"❌ {error_data.get('detail', 'Failed to add song')}")
        except Exception as e:
            await self.highrise.chat(f"❌ Error requesting song: {str(e)}")

    async def skip_song(self):
        try:
            async with self.session.post(f"{self.backend_url}/api/skip") as response:
                if response.status == 200:
                    data = await response.json()
                    skipped = data.get('skipped_track', 'Unknown')

                    await self.highrise.chat(f"⏭️ Skipped: {skipped}")
                    await self.highrise.chat(f"▶️ Playing next song...")
                else:
                    error_data = await response.json()
                    await self.highrise.chat(f"❌ {error_data.get('detail', 'Could not skip')}")
        except Exception as e:
            await self.highrise.chat(f"❌ Error: {str(e)}")

    async def pause_playback(self):
        try:
            async with self.session.post(f"{self.backend_url}/api/pause") as response:
                if response.status == 200:
                    await self.highrise.chat("⏸️ Broadcast paused")
                else:
                    error_data = await response.json()
                    await self.highrise.chat(f"❌ {error_data.get('detail', 'Could not pause')}")
        except Exception as e:
            await self.highrise.chat(f"❌ Error: {str(e)}")

    async def resume_playback(self):
        try:
            async with self.session.post(f"{self.backend_url}/api/resume") as response:
                if response.status == 200:
                    await self.highrise.chat("▶️ Broadcast resumed!")
                else:
                    error_data = await response.json()
                    await self.highrise.chat(f"❌ {error_data.get('detail', 'Could not resume')}")
        except Exception as e:
            await self.highrise.chat(f"❌ Error: {str(e)}")


if __name__ == "__main__":
    from highrise import __main__
    from highrise.__main__ import BotDefinition

    bot_token = os.getenv("HIGHRISE_API_TOKEN", "YOUR_BOT_TOKEN_HERE")
    room_id = os.getenv("HIGHRISE_ROOM_ID", "YOUR_ROOM_ID_HERE")

    bot = MusicBot()
    bot.admins = os.getenv("ADMINS", "Saittam_Virus").split(",") if os.getenv("ADMINS") else []

    bot_definition = BotDefinition(bot, room_id, bot_token)

    try:
        asyncio.run(__main__.main([bot_definition]))
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"💥 Bot crashed: {e}")
