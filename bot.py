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
        
        await self.highrise.chat("🎧 24/7 Radio Bot Online! Music never stops! Type !help for commands")
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
            'url': self.cmd_url,
            'np': self.cmd_now_playing,
            'help': self.cmd_help,
            'status': self.cmd_status,
            'search': self.cmd_search,
            'skip': self.cmd_skip,
            'queue': self.cmd_queue,
        }

        if command in commands:
            await commands[command](user, args)
        else:
            await self.highrise.send_whisper(user.id, "❌ Unknown command. Use !help")

    async def cmd_play(self, user: User, args: str) -> None:
        """Handle !play [song] - Add song to queue"""
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
                            
                            # Add to queue with user info
                            async with session.post(
                                f"{self.api_base}/api/play",
                                data={'video_url': first_result['url'], 'requested_by': user.username}
                            ) as play_resp:
                                if play_resp.status == 200:
                                    result = await play_resp.json()
                                    
                                    if result.get('status') == 'queued':
                                        # Song was added to queue
                                        position = result.get('position', 0)
                                        await self.highrise.chat(
                                            f"🎵 ADDED TO QUEUE (#{position}): {first_result['title']}\n"
                                            f"🎤 Requested by: @{user.username}\n"
                                            f"⏳ Will play after current songs..."
                                        )
                                    else:
                                        # Song is playing now
                                        await self.highrise.chat(
                                            f"🎵 NOW PLAYING: {first_result['title']}\n"
                                            f"🎤 Artist: {first_result.get('artist', 'Unknown')}\n"
                                            f"🎧 Requested by: @{user.username}"
                                        )
                                else:
                                    error_text = await play_resp.text()
                                    print(f"Play API error: {error_text}")
                                    await self.highrise.chat("❌ Failed to add song to queue")
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
                                results_text += f"{i}. {track['title']} - {track.get('artist', 'Unknown')}\n"
                            
                            results_text += f"\n💡 Use: !play \"{results[0]['title']}\""
                            
                            await self.highrise.send_whisper(user.id, results_text)
                        else:
                            await self.highrise.send_whisper(user.id, "❌ No results found")
                    else:
                        await self.highrise.send_whisper(user.id, "❌ Search service unavailable")
                        
            except Exception as e:
                print(f"Search error: {e}")
                await self.highrise.send_whisper(user.id, "❌ Cannot connect to search service")

    async def cmd_skip(self, user: User, args: str) -> None:
        """Handle !skip - Skip current song"""
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.api_base}/api/skip") as resp:
                if resp.status == 200:
                    result = await resp.json()
                    message = result.get('message', 'Skipped')
                    
                    if "queue" in message.lower():
                        await self.highrise.chat(f"⏭️ @{user.username} skipped to next song in queue")
                    elif "random" in message.lower():
                        await self.highrise.chat(f"⏭️ @{user.username} skipped to next random song")
                    else:
                        await self.highrise.chat(f"⏭️ @{user.username} skipped current song")
                else:
                    await self.highrise.chat("❌ Skip failed")

    async def cmd_queue(self, user: User, args: str) -> None:
        """Handle !queue - Show current queue"""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{self.api_base}/api/queue") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        current_track = data.get('current_track')
                        queue = data.get('queue', [])
                        queue_length = data.get('queue_length', 0)
                        is_random = data.get('is_random_playing', False)
                        
                        queue_text = "📋 MUSIC QUEUE:\n"
                        
                        if current_track:
                            if is_random:
                                queue_text += f"🎲 NOW PLAYING (Auto DJ): {current_track.get('title', 'Unknown')}\n"
                            else:
                                requester = current_track.get('requested_by', 'Unknown')
                                queue_text += f"🎵 NOW PLAYING: {current_track.get('title', 'Unknown')} (by @{requester})\n"
                        else:
                            queue_text += "🎵 NOW PLAYING: Auto DJ - Bollywood Mix\n"
                        
                        if queue_length > 0:
                            queue_text += f"\n📜 Next in queue ({queue_length} songs):\n"
                            for i, track in enumerate(queue[:5], 1):
                                requester = track.get('requested_by', 'Unknown')
                                queue_text += f"{i}. {track.get('title', 'Unknown')} (by @{requester})\n"
                            
                            if queue_length > 5:
                                queue_text += f"... and {queue_length - 5} more\n"
                        else:
                            queue_text += "\n📜 Queue is empty - random Bollywood songs playing"
                        
                        await self.highrise.send_whisper(user.id, queue_text)
                    else:
                        await self.highrise.send_whisper(user.id, "❌ Could not get queue status")
                        
            except Exception as e:
                print(f"Queue error: {e}")
                await self.highrise.send_whisper(user.id, "❌ Cannot connect to queue service")

    async def cmd_url(self, user: User, args: str) -> None:
        """Handle !url - Get radio stream URL"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.api_base}/api/radio/url") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    radio_url = data.get('radio_url')
                    
                    if radio_url:
                        message = f"📻 LIVE RADIO STREAM URL:\n{radio_url}\n\n📍 Add this to Highrise room music settings!\n\n🎧 Features:\n• 24/7 Live Stream\n• Everyone hears same timeline\n• Request songs with !play\n• Skip with !skip\n• Auto Bollywood when queue empty"
                        
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
                    is_random = data.get('is_random_playing', False)
                    queue_length = data.get('queue_length', 0)
                    
                    if current_track:
                        requester = current_track.get('requested_by', 'Auto DJ')
                        if is_random:
                            await self.highrise.chat(
                                f"🎲 AUTO DJ PLAYING:\n"
                                f"📀 {current_track['title']}\n"
                                f"🎤 {current_track['artist']}\n"
                                f"📜 {queue_length} songs in queue"
                            )
                        else:
                            await self.highrise.chat(
                                f"🎧 NOW PLAYING:\n"
                                f"📀 {current_track['title']}\n"
                                f"🎤 {current_track['artist']}\n"
                                f"👤 Requested by: @{requester}\n"
                                f"📜 {queue_length} songs in queue"
                            )
                    else:
                        await self.highrise.chat("🎲 Auto DJ Playing: Bollywood Club Mix")
                else:
                    await self.highrise.chat("❌ Could not get player status")

    async def cmd_status(self, user: User, args: str) -> None:
        """Handle !status - Show radio status"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.api_base}/api/status") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    current_track = data.get('current_track')
                    queue_length = data.get('queue_length', 0)
                    is_random = data.get('is_random_playing', False)
                    
                    status_text = "🟢 LIVE RADIO STATUS:\n📡 Stream: ALWAYS ACTIVE\n"
                    status_text += f"📜 Queue: {queue_length} songs\n"
                    
                    if current_track:
                        if is_random:
                            status_text += f"🎲 Now Playing: {current_track['title']} (Auto DJ)"
                        else:
                            requester = current_track.get('requested_by', 'Unknown')
                            status_text += f"🎵 Now Playing: {current_track['title']} (by @{requester})"
                    else:
                        status_text += "🎲 Now Playing: Auto DJ - Bollywood Mix"
                    
                    await self.highrise.chat(status_text)
                else:
                    await self.highrise.chat("❌ Could not get radio status")

    async def cmd_help(self, user: User, args: str) -> None:
        """Handle !help - Show help menu"""
        help_text = (
            "📻 24/7 LIVE RADIO COMMANDS:\n\n"
            "🎵 Music Requests:\n"
            "!play [song] - Request song (adds to queue)\n"
            "!search [song] - Search without playing\n"
            "!skip - Vote to skip current song\n\n"
            "📋 Queue Info:\n"
            "!queue - Show current queue\n"
            "!np - Now playing information\n\n"
            "📡 Radio Info:\n"
            "!url - Get radio stream URL\n"
            "!status - Radio status\n"
            "!help - This help message\n\n"
            "💡 Features:\n"
            "• Music NEVER stops - 24/7 stream\n"
            "• Everyone hears the same timeline\n"
            "• Auto Bollywood when queue empty\n"
            "• Request songs with !play\n"
            "• Skip with !skip (no pause/stop)"
        )
        
        await self.highrise.send_whisper(user.id, help_text)
        await self.highrise.chat(f"📖 @{user.username} Check your DMs for help!")

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
