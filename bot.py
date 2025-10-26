import os
import asyncio
import aiohttp
from highrise import BaseBot
from highrise.models import SessionMetadata, User, Position
import time

class MusicBot(BaseBot):
    def __init__(self):
        super().__init__()
        self.api_base = os.getenv('MUSIC_API_URL')
        if not self.api_base:
            raise ValueError("MUSIC_API_URL environment variable is required")
        
        self.bot_user_id = None
        
        # Bot roaming positions
        self.roaming_positions = [
            Position(13.5, 0.25, 14.0, "FrontRight"),
            Position(15.5, 0.25, 19.5, "FrontLeft"),
            Position(6.5, 0.25, 17.0, "BackRight"),
            Position(11.0, 0.25, 23.5, "BackLeft"),
            Position(3.0, 0.25, 15.5, "FrontRight"),
        ]
        self.current_roam_index = 0

    async def on_start(self, session_metadata: SessionMetadata) -> None:
        self.bot_user_id = session_metadata.user_id
        print("🎵 Music Bot Started!")
        
        await self.highrise.chat("🎧 Music Bot Online! Type !help for commands")
        asyncio.create_task(self.roam_continuously())

    async def on_user_join(self, user: User, position: Position) -> None:
        """Welcome new users"""
        await self.highrise.chat(f"👋 Welcome {user.username}! Type !help for music commands")
        await self.highrise.send_whisper(user.id, "🎵 Use !play [song] to play music, !url to get stream URL for room")

    async def on_chat(self, user: User, message: str) -> None:
        try:
            message = message.strip()

            if message.startswith('!'):
                await self.handle_command(user, message)

        except Exception as e:
            print(f"Error: {e}")
            await self.highrise.send_whisper(user.id, "❌ Error processing command")

    async def handle_command(self, user: User, message: str) -> None:
        """Handle all commands"""
        command_parts = message[1:].split(' ', 1)
        command = command_parts[0].lower()
        args = command_parts[1] if len(command_parts) > 1 else ""

        commands = {
            'play': self.cmd_play,
            'stop': self.cmd_stop,
            'url': self.cmd_url,
            'np': self.cmd_now_playing,
            'help': self.cmd_help,
            'status': self.cmd_status,
        }

        if command in commands:
            await commands[command](user, args)
        else:
            await self.highrise.send_whisper(user.id, "❌ Unknown command. Use !help")

    async def cmd_play(self, user: User, args: str) -> None:
        """Handle !play [song] command"""
        if not args:
            await self.highrise.send_whisper(user.id, "Usage: !play [song name]\nExample: !play despacito")
            return

        await self.highrise.chat(f"🔍 {user.username} searching for: {args}")
        
        async with aiohttp.ClientSession() as session:
            try:
                # Search for music
                async with session.get(f"{self.api_base}/api/search?q={args}") as resp:
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
                                        f"🎧 Requested by: @{user.username}\n"
                                        f"🔗 Use !url to get stream URL for room"
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

    async def cmd_stop(self, user: User, args: str) -> None:
        """Handle !stop command"""
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.api_base}/api/stop") as resp:
                if resp.status == 200:
                    await self.highrise.chat(f"⏹️ Music stopped by @{user.username}")
                else:
                    await self.highrise.chat("❌ Already stopped or service unavailable")

    async def cmd_url(self, user: User, args: str) -> None:
        """Handle !url command - get radio stream URL"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.api_base}/api/radio/url") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    radio_url = data.get('radio_url')
                    
                    if radio_url:
                        await self.highrise.send_whisper(
                            user.id,
                            f"📻 RADIO STREAM URL:\n"
                            f"{radio_url}\n\n"
                            f"📍 Add this to Highrise room music settings!\n"
                            f"🎵 Music will automatically play when you use !play"
                        )
                        await self.highrise.chat(f"📻 @{user.username} check your DMs for the stream URL!")
                    else:
                        await self.highrise.send_whisper(
                            user.id,
                            "❌ No active stream. Use !play [song] first, then get the URL"
                        )
                else:
                    await self.highrise.send_whisper(user.id, "❌ Could not get stream URL")

    async def cmd_now_playing(self, user: User, args: str) -> None:
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
                            f"🎤 {current_track['artist']}\n"
                            f"🎵 Request !play [song] for more music"
                        )
                    else:
                        await self.highrise.chat("📻 No music currently playing")
                else:
                    await self.highrise.chat("❌ Could not get player status")

    async def cmd_status(self, user: User, args: str) -> None:
        """Handle !status command"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.api_base}/api/status") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    status = data.get('status', 'unknown')
                    stream_active = data.get('stream_active', False)
                    
                    status_emoji = "🟢" if stream_active else "🔴"
                    await self.highrise.chat(
                        f"{status_emoji} Music Status: {status.upper()}\n"
                        f"📡 Stream: {'ACTIVE' if stream_active else 'INACTIVE'}"
                    )
                else:
                    await self.highrise.chat("❌ Service unavailable")

    async def cmd_help(self, user: User, args: str) -> None:
        """Handle !help command"""
        help_text = (
            "🎵 MUSIC BOT COMMANDS:\n"
            "!play [song] - Play music from YouTube\n"
            "!stop - Stop current playback\n"
            "!url - Get radio stream URL for room\n"
            "!np - Now playing information\n"
            "!status - Stream status\n"
            "!help - This help message\n\n"
            "💡 TIP: Add the stream URL to room music settings once, then control with !play"
        )
        
        await self.highrise.send_whisper(user.id, help_text)

    async def roam_continuously(self) -> None:
        """Make bot roam around the room automatically"""
        while True:
            try:
                next_pos = self.roaming_positions[self.current_roam_index]
                await self.highrise.walk_to(next_pos)
                self.current_roam_index = (self.current_roam_index + 1) % len(self.roaming_positions)
                await asyncio.sleep(45)
            except Exception as e:
                print(f"Roaming error: {e}")
                await asyncio.sleep(10)

if __name__ == "__main__":
    from highrise import __main__
    from highrise.__main__ import BotDefinition

    API_TOKEN = os.environ.get("HIGHRISE_API_TOKEN")
    ROOM_ID = os.environ.get("HIGHRISE_ROOM_ID")

    if not API_TOKEN or not ROOM_ID:
        print("❌ Set HIGHRISE_API_TOKEN and HIGHRISE_ROOM_ID environment variables")
        exit(1)

    bot = MusicBot()
    bot_definition = BotDefinition(bot, ROOM_ID, API_TOKEN)

    try:
        asyncio.run(__main__.main([bot_definition]))
    except KeyboardInterrupt:
        print("\n🛑 Music Bot stopped by user")
    except Exception as e:
        print(f"💥 Music Bot crashed: {e}")