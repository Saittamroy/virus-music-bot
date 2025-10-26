import os
import aiohttp
from highrise import BaseBot, User, SessionMetadata

class HighriseRadioBot(BaseBot):
    def __init__(self):
        super().__init__()
        self.api_base = os.getenv('MUSIC_API_URL')
        if not self.api_base:
            raise ValueError("MUSIC_API_URL environment variable is required")
        
    async def on_start(self, session_metadata: SessionMetadata) -> None:
        print("🎵 Highrise Radio Bot Started!")
        await self.highrise.chat("📻 Radio Bot Online! Type !help for commands")
    
    async def on_chat(self, user: User, message: str) -> None:
        try:
            if message.startswith('!'):
                command_parts = message[1:].split(' ', 1)
                command = command_parts[0].lower()
                args = command_parts[1] if len(command_parts) > 1 else ""
                
                if command == 'play' and args:
                    await self.handle_play(user, args)
                elif command == 'stop':
                    await self.handle_stop(user)
                elif command == 'url':
                    await self.handle_stream_url(user)
                elif command == 'np':
                    await self.handle_now_playing(user)
                elif command == 'help':
                    await self.handle_help(user)
                elif command == 'status':
                    await self.handle_status(user)
                    
        except Exception as e:
            print(f"Error handling command: {e}")
            await self.highrise.chat("❌ Error processing command")
    
    async def handle_play(self, user: User, query: str):
        """Handle !play [song] command"""
        await self.highrise.chat(f"🔍 @{user.username} searching for: {query}")
        
        async with aiohttp.ClientSession() as session:
            try:
                # Search for music
                async with session.get(f"{self.api_base}/api/search?q={query}") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('results'):
                            first_result = data['results'][0]
                            
                            # Start streaming
                            async with session.post(
                                f"{self.api_base}/api/play",
                                data={'video_url': first_result['url']}
                            ) as play_resp:
                                if play_resp.status == 200:
                                    result = await play_resp.json()
                                    
                                    await self.highrise.chat(
                                        f"🎵 NOW PLAYING: {first_result['title']}\n"
                                        f"🎤 Artist: {first_result.get('uploader', 'Unknown')}\n"
                                        f"🎧 Requested by: @{user.username}"
                                    )
                                else:
                                    await self.highrise.chat("❌ Failed to start stream")
                        else:
                            await self.highrise.chat("❌ No results found for your search")
                    else:
                        await self.highrise.chat("❌ Search service unavailable")
                        
            except Exception as e:
                print(f"Play error: {e}")
                await self.highrise.chat("❌ Cannot connect to music service")
    
    async def handle_stop(self, user: User):
        """Handle !stop command"""
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.api_base}/api/stop") as resp:
                if resp.status == 200:
                    await self.highrise.chat(f"⏹️ Radio stopped by @{user.username}")
                else:
                    await self.highrise.chat("❌ Already stopped or service unavailable")
    
    async def handle_stream_url(self, user: User):
        """Handle !url command"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.api_base}/api/radio/url") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    radio_url = data.get('radio_url')
                    
                    await self.highrise.chat(
                        f"📻 RADIO STREAM URL:\n"
                        f"{radio_url}\n"
                        f"📍 Add this to Highrise room music settings!"
                    )
                else:
                    await self.highrise.chat("❌ Could not get stream URL")
    
    async def handle_now_playing(self, user: User):
        """Handle !np command"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.api_base}/api/status") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    current_track = data.get('current_track')
                    status = data.get('status')
                    
                    if status == "playing" and current_track:
                        await self.highrise.chat(
                            f"🎧 NOW PLAYING:\n"
                            f"📀 {current_track['title']}\n"
                            f"🎤 {current_track['artist']}"
                        )
                    else:
                        await self.highrise.chat("📻 No music currently playing")
                else:
                    await self.highrise.chat("❌ Could not get player status")
    
    async def handle_status(self, user: User):
        """Handle !status command"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.api_base}/api/status") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    status = data.get('status', 'unknown')
                    stream_active = data.get('stream_active', False)
                    
                    status_emoji = "🟢" if stream_active else "🔴"
                    await self.highrise.chat(
                        f"{status_emoji} Radio Status: {status.upper()}\n"
                        f"📡 Stream: {'ACTIVE' if stream_active else 'INACTIVE'}"
                    )
                else:
                    await self.highrise.chat("❌ Service unavailable")
    
    async def handle_help(self, user: User):
        """Handle !help command"""
        help_text = """
🎵 RADIO BOT COMMANDS:
!play [song] - Play music from YouTube
!stop - Stop current playback
!url - Get radio stream URL for room
!np - Now playing information  
!status - Radio stream status
!help - This help message

Add the stream URL to your Highrise room music settings once!
        """.strip()
        
        await self.highrise.chat(help_text)

bot = HighriseRadioBot()