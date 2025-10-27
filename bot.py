import os
import asyncio
import aiohttp
from highrise import BaseBot
from highrise.models import SessionMetadata, User, Position
from highrise.__main__ import *

class AzuraCastBot(BaseBot):
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
        print("📻 AzuraCast Radio Bot Started!")
        
        await self.highrise.chat("🎧 Radio Bot Online! Type !help for commands")
        asyncio.create_task(self.roam_continuously())

    async def on_user_join(self, user: User, position: Position) -> None:
        """Welcome new users"""
        await self.highrise.chat(f"👋 Welcome {user.username}! Type !help for radio commands")

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
            'search': self.cmd_search,
            'skip': self.cmd_skip,
        }

        if command in commands:
            await commands[command](user, args)
        else:
            await self.highrise.send_whisper(user.id, "❌ Unknown command. Use !help")

    async def cmd_play(self, user: User, args: str) -> None:
        """Handle !play [song] - Play music on radio"""
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
                            # Get the first result
                            first_result = data['results'][0]
                            
                            # Start radio stream
                            async with session.post(
                                f"{self.api_base}/api/play",
                                data={'video_url': first_result['url']}
                            ) as play_resp:
                                if play_resp.status == 200:
                                    result = await play_resp.json()
                                    radio_url = result.get('radio_url')
                                    
                                    await self.highrise.chat(
                                        f"🎵 NOW PLAYING: {first_result['title']}\n"
                                        f"🎤 Artist: {first_result.get('uploader', 'Unknown')}\n"
                                        f"🎧 Requested by: @{user.username}\n"
                                        f"📻 Radio stream started!"
                                    )
                                    
                                    # Send radio URL via whisper
                                    if radio_url:
                                        await self.highrise.send_whisper(
                                            user.id,
                                            f"📻 RADIO STREAM URL:\n{radio_url}\n\n"
                                            f"📍 Add this to Highrise room music settings!\n"
                                            f"🎵 Music will play automatically!"
                                        )
                                else:
                                    error_text = await play_resp.text()
                                    print(f"Play API error: {error_text}")
                                    await self.highrise.chat("❌ Failed to start radio stream")
                        else:
                            await self.highrise.chat("❌ No results found for your search")
                    else:
                        await self.highrise.chat("❌ Search service unavailable")
                        
            except Exception as e:
                print(f"Play error: {e}")
                await self.highrise.chat("❌ Cannot connect to radio service")

    async def cmd_search(self, user: User, args: str) -> None:
        """Handle !search [query] - Search for music without playing"""
        if not args:
            await self.highrise.send_whisper(user.id, "Usage: !search [song name]\nExample: !search despacito")
            return

        await self.highrise.chat(f"🔍 {user.username} searching for: {args}")
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{self.api_base}/api/search?q={args}") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('results'):
                            results = data['results'][:3]  # Show top 3 results
                            
                            results_text = "🎵 Search Results:\n"
                            for i, track in enumerate(results, 1):
                                results_text += f"{i}. {track['title']} - {track.get('uploader', 'Unknown')}\n"
                            
                            results_text += f"\n💡 Use: !play \"{results[0]['title']}\""
                            
                            await self.highrise.send_whisper(user.id, results_text)
                        else:
                            await self.highrise.send_whisper(user.id, "❌ No results found")
                    else:
                        await self.highrise.send_whisper(user.id, "❌ Search service unavailable")
                        
            except Exception as e:
                print(f"Search error: {e}")
                await self.highrise.send_whisper(user.id, "❌ Cannot connect to search service")

    async def cmd_stop(self, user: User, args: str) -> None:
        """Handle !stop - Stop radio stream"""
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.api_base}/api/stop") as resp:
                if resp.status == 200:
                    await self.highrise.chat(f"⏹️ Radio stopped by @{user.username}")
                else:
                    await self.highrise.chat("❌ Radio already stopped or service unavailable")

    async def cmd_skip(self, user: User, args: str) -> None:
        """Handle !skip - Skip current song (alias for stop)"""
        await self.cmd_stop(user, args)

    async def cmd_url(self, user: User, args: str) -> None:
        """Handle !url - Get radio stream URL"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.api_base}/api/radio/url") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    radio_url = data.get('radio_url')
                    status = data.get('status')
                    
                    if radio_url:
                        message = f"📻 RADIO STREAM URL:\n{radio_url}\n\n📍 Add this to Highrise room music settings!"
                        
                        if status == "playing":
                            current_track = data.get('current_track', 'Unknown')
                            message += f"\n🎵 Currently playing: {current_track}"
                        else:
                            message += f"\n💡 Use !play [song] to start music"
                        
                        await self.highrise.send_whisper(user.id, message)
                        await self.highrise.chat(f"📻 @{user.username} check your DMs for the radio URL!")
                    else:
                        await self.highrise.send_whisper(user.id, "❌ Could not get radio URL")
                else:
                    await self.highrise.send_whisper(user.id, "❌ Service unavailable")

    async def cmd_now_playing(self, user: User, args: str) -> None:
        """Handle !np - Show now playing information"""
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
                            f"⏱️ {self.format_duration(current_track.get('duration', 0))}"
                        )
                    else:
                        await self.highrise.chat("📻 No music currently playing")
                else:
                    await self.highrise.chat("❌ Could not get player status")

    async def cmd_status(self, user: User, args: str) -> None:
        """Handle !status - Show radio status"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.api_base}/api/status") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    status = data.get('status', 'unknown')
                    stream_active = data.get('stream_active', False)
                    current_track = data.get('current_track')
                    
                    status_emoji = "🟢" if stream_active else "🔴"
                    status_text = f"{status_emoji} Radio Status: {status.upper()}\n📡 Stream: {'ACTIVE' if stream_active else 'INACTIVE'}"
                    
                    if current_track:
                        status_text += f"\n🎵 Now Playing: {current_track['title']}"
                    
                    await self.highrise.chat(status_text)
                else:
                    await self.highrise.chat("❌ Service unavailable")

    async def cmd_help(self, user: User, args: str) -> None:
        """Handle !help - Show help menu"""
        help_text = (
            "📻 RADIO BOT COMMANDS:\n\n"
            "🎵 Music Control:\n"
            "!play [song] - Play music on radio\n"
            "!stop - Stop current playback\n"
            "!skip - Skip current song\n"
            "!search [song] - Search without playing\n\n"
            "📡 Radio Info:\n"
            "!url - Get radio stream URL for room\n"
            "!np - Now playing information\n"
            "!status - Radio stream status\n"
            "!help - This help message\n\n"
            "💡 TIP: Add the radio URL to room settings once, then control with commands!"
        )
        
        await self.highrise.send_whisper(user.id, help_text)

    def format_duration(self, seconds: int) -> str:
        """Format seconds into MM:SS"""
        if seconds <= 0:
            return "Live"
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes}:{seconds:02d}"

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

# FIXED BOT RUNNER - Use the new Highrise SDK method
if __name__ == "__main__":
    import sys
    
    # Get environment variables
    api_token = os.getenv("HIGHRISE_API_TOKEN")
    room_id = os.getenv("HIGHRISE_ROOM_ID")
    
    if not api_token or not room_id:
        print("❌ Error: Set HIGHRISE_API_TOKEN and HIGHRISE_ROOM_ID environment variables")
        sys.exit(1)
    
    # Create bot definition using the new SDK format
    bot = AzuraCastBot()
    
    try:
        # Run the bot using the new SDK method
        asyncio.run(main([BotDefinition(bot, room_id, api_token)]))
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"💥 Bot crashed: {e}")