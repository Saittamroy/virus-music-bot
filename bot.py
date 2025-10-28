import os
import asyncio
import aiohttp
from typing import Optional, List, Dict
from dataclasses import dataclass
from datetime import datetime
from highrise import BaseBot
from highrise.models import SessionMetadata, User, Position, AnchorPosition
from highrise.__main__ import *

@dataclass
class SongRequest:
    """Track song request metadata"""
    title: str
    url: str
    requested_by: str
    requested_at: datetime

class MusicBotConfig:
    """Bot configuration constants"""
    MAX_RETRIES = 3
    RETRY_DELAY = 2
    API_TIMEOUT = 15
    ROAM_INTERVAL = 45
    ROAM_SPEED = 1.5
    
    # Admin usernames (configure these)
    ADMINS = ["your_admin_username", "another_admin"]
    
    # Cooldown settings
    COMMAND_COOLDOWN = 3  # seconds between commands per user
    SKIP_COOLDOWN = 10    # seconds between skip commands

class AzuraCastMusicBot(BaseBot):
    def __init__(self):
        super().__init__()
        self.api_base = os.getenv('MUSIC_API_URL')
        if not self.api_base:
            raise ValueError("MUSIC_API_URL environment variable is required")
        
        self.bot_user_id: Optional[str] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.is_connected = False
        
        # Song queue
        self.song_queue: List[SongRequest] = []
        self.current_song: Optional[SongRequest] = None
        self.radio_url: Optional[str] = None
        
        # Cooldown tracking
        self.user_cooldowns: Dict[str, datetime] = {}
        self.last_skip_time: Optional[datetime] = None
        
        # Bot movement
        self.roaming_positions = [
            Position(13.5, 0.25, 14.0, "FrontRight"),
            Position(15.5, 0.25, 19.5, "FrontLeft"),
            Position(6.5, 0.25, 17.0, "BackRight"),
            Position(11.0, 0.25, 23.5, "BackLeft"),
            Position(3.0, 0.25, 15.5, "FrontRight"),
            Position(8.0, 0.25, 20.0, "BackLeft"),
        ]
        self.current_roam_index = 0
        self.roaming_task: Optional[asyncio.Task] = None
        
        # Statistics
        self.songs_played = 0
        self.start_time: Optional[datetime] = None

    async def on_start(self, session_metadata: SessionMetadata) -> None:
        """Initialize bot when it starts"""
        self.bot_user_id = session_metadata.user_id
        self.start_time = datetime.now()
        self.is_connected = True
        
        # Create HTTP session
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=MusicBotConfig.API_TIMEOUT)
        )
        
        print("=" * 50)
        print("🎵 MUSIC BOT INITIALIZED")
        print(f"📍 Room: {session_metadata.room_info.room_name if hasattr(session_metadata.room_info, 'room_name') else 'Unknown'}")
        print(f"🤖 Bot User ID: {self.bot_user_id}")
        print(f"🌐 API Base: {self.api_base}")
        print("=" * 50)
        
        # Fetch radio URL on startup
        await self.fetch_radio_url()
        
        # Welcome message
        await self.highrise.chat(
            "🎧 Music Radio Bot is now ONLINE!\n"
            "Type !help to see all commands"
        )
        
        # Start background tasks
        self.roaming_task = asyncio.create_task(self.roam_continuously())

    async def on_stop(self) -> None:
        """Cleanup when bot stops"""
        self.is_connected = False
        
        # Cancel roaming task
        if self.roaming_task:
            self.roaming_task.cancel()
            try:
                await self.roaming_task
            except asyncio.CancelledError:
                pass
        
        # Close HTTP session
        if self.session and not self.session.closed:
            await self.session.close()
        
        print("🛑 Bot stopped gracefully")

    async def on_user_join(self, user: User, position: Position) -> None:
        """Welcome new users with helpful info"""
        welcome_msg = (
            f"👋 Welcome {user.username}!\n"
            f"🎵 Type !help for music commands\n"
        )
        
        if self.current_song:
            welcome_msg += f"🎧 Now playing: {self.current_song.title}"
        
        await self.highrise.chat(welcome_msg)

    async def on_chat(self, user: User, message: str) -> None:
        """Handle all chat messages"""
        try:
            message = message.strip()

            # Ignore bot's own messages
            if user.id == self.bot_user_id:
                return

            # Handle commands
            if message.startswith('!'):
                # Check cooldown
                if not self.is_admin(user) and not self.check_cooldown(user):
                    return
                
                await self.handle_command(user, message)

        except Exception as e:
            print(f"❌ Chat error: {e}")
            await self.send_error(user, "Error processing your message")

    async def handle_command(self, user: User, message: str) -> None:
        """Route commands to appropriate handlers"""
        command_parts = message[1:].split(' ', 1)
        command = command_parts[0].lower()
        args = command_parts[1] if len(command_parts) > 1 else ""

        commands = {
            'play': self.cmd_play,
            'stop': self.cmd_stop,
            'skip': self.cmd_skip,
            'np': self.cmd_now_playing,
            'queue': self.cmd_queue,
            'search': self.cmd_search,
            'url': self.cmd_get_url,
            'status': self.cmd_status,
            'help': self.cmd_help,
            'stats': self.cmd_stats,
            'clear': self.cmd_clear_queue,
        }

        if command in commands:
            try:
                await commands[command](user, args)
            except Exception as e:
                print(f"❌ Command error ({command}): {e}")
                await self.send_error(user, f"Failed to execute !{command}")
        else:
            await self.highrise.send_whisper(
                user.id,
                f"❌ Unknown command: !{command}\nType !help for available commands"
            )

    async def cmd_play(self, user: User, args: str) -> None:
        """Play a song or add to queue"""
        if not args:
            await self.highrise.send_whisper(
                user.id,
                "Usage: !play [song name]\nExample: !play imagine dragons believer"
            )
            return

        await self.highrise.chat(f"🔍 Searching for: {args}...")
        
        try:
            # Search for the song
            search_results = await self.api_search(args)
            
            if not search_results:
                await self.highrise.chat("❌ No results found. Try a different search term.")
                return
            
            # Get first result
            track = search_results[0]
            
            # Create song request
            song_request = SongRequest(
                title=track['title'],
                url=track['url'],
                requested_by=user.username,
                requested_at=datetime.now()
            )
            
            # If nothing is playing, play immediately
            if not self.current_song:
                await self.play_song(song_request)
            else:
                # Add to queue
                self.song_queue.append(song_request)
                await self.highrise.chat(
                    f"➕ Added to queue (#{len(self.song_queue)}): {track['title']}\n"
                    f"🎤 Artist: {track.get('artist', 'Unknown')}\n"
                    f"👤 Requested by: @{user.username}"
                )
                
        except Exception as e:
            print(f"❌ Play command error: {e}")
            await self.highrise.chat("❌ Failed to play song. Please try again.")

    async def play_song(self, song: SongRequest) -> None:
        """Actually play a song through the API"""
        try:
            # Send play request to backend
            result = await self.api_play(song.url)
            
            if result:
                self.current_song = song
                self.songs_played += 1
                
                await self.highrise.chat(
                    f"🎵 NOW PLAYING:\n"
                    f"📀 {song.title}\n"
                    f"👤 Requested by: @{song.requested_by}\n"
                    f"📻 Radio streaming now!"
                )
                
                # Send radio URL reminder if available
                if self.radio_url:
                    await self.highrise.send_whisper(
                        song.requested_by,
                        f"📻 Radio URL (add to room music):\n{self.radio_url}"
                    )
            else:
                await self.highrise.chat("❌ Failed to start playback")
                # Try next in queue
                await self.play_next_in_queue()
                
        except Exception as e:
            print(f"❌ Playback error: {e}")
            await self.highrise.chat("❌ Playback error occurred")

    async def play_next_in_queue(self) -> None:
        """Play next song in queue"""
        if self.song_queue:
            next_song = self.song_queue.pop(0)
            await self.play_song(next_song)
        else:
            self.current_song = None
            await self.highrise.chat("✅ Queue finished. Use !play to add more songs!")

    async def cmd_skip(self, user: User, args: str) -> None:
        """Skip current song"""
        # Check skip cooldown
        if not self.is_admin(user):
            if self.last_skip_time:
                time_since_skip = (datetime.now() - self.last_skip_time).total_seconds()
                if time_since_skip < MusicBotConfig.SKIP_COOLDOWN:
                    remaining = int(MusicBotConfig.SKIP_COOLDOWN - time_since_skip)
                    await self.highrise.send_whisper(
                        user.id,
                        f"⏳ Skip cooldown: {remaining}s remaining"
                    )
                    return
        
        if not self.current_song:
            await self.highrise.chat("❌ Nothing is playing")
            return
        
        self.last_skip_time = datetime.now()
        skipped_title = self.current_song.title
        
        # Stop current song
        await self.api_stop()
        
        await self.highrise.chat(f"⏭️ Skipped: {skipped_title}")
        
        # Play next in queue
        await asyncio.sleep(1)
        await self.play_next_in_queue()

    async def cmd_stop(self, user: User, args: str) -> None:
        """Stop playback and clear queue"""
        if not self.is_admin(user):
            await self.highrise.send_whisper(user.id, "❌ Only admins can stop playback")
            return
        
        await self.api_stop()
        self.current_song = None
        self.song_queue.clear()
        
        await self.highrise.chat(f"⏹️ Playback stopped and queue cleared by @{user.username}")

    async def cmd_queue(self, user: User, args: str) -> None:
        """Show current queue"""
        if not self.song_queue:
            msg = "📋 Queue is empty"
            if self.current_song:
                msg += f"\n🎵 Currently playing: {self.current_song.title}"
            await self.highrise.send_whisper(user.id, msg)
            return
        
        queue_text = f"📋 SONG QUEUE ({len(self.song_queue)} songs):\n\n"
        
        if self.current_song:
            queue_text += f"▶️ Now: {self.current_song.title}\n   by @{self.current_song.requested_by}\n\n"
        
        for i, song in enumerate(self.song_queue[:5], 1):
            queue_text += f"{i}. {song.title}\n   by @{song.requested_by}\n"
        
        if len(self.song_queue) > 5:
            queue_text += f"\n... and {len(self.song_queue) - 5} more"
        
        await self.highrise.send_whisper(user.id, queue_text)

    async def cmd_search(self, user: User, args: str) -> None:
        """Search for songs without playing"""
        if not args:
            await self.highrise.send_whisper(
                user.id,
                "Usage: !search [song name]\nExample: !search coldplay"
            )
            return
        
        await self.highrise.chat(f"🔍 {user.username} is searching...")
        
        try:
            results = await self.api_search(args, limit=5)
            
            if not results:
                await self.highrise.send_whisper(user.id, "❌ No results found")
                return
            
            search_text = f"🎵 Search results for '{args}':\n\n"
            for i, track in enumerate(results, 1):
                search_text += f"{i}. {track['title']}\n"
                search_text += f"   🎤 {track.get('artist', 'Unknown')}\n"
            
            search_text += f"\n💡 Use: !play {results[0]['title']}"
            
            await self.highrise.send_whisper(user.id, search_text)
            
        except Exception as e:
            print(f"❌ Search error: {e}")
            await self.send_error(user, "Search failed")

    async def cmd_now_playing(self, user: User, args: str) -> None:
        """Show what's currently playing"""
        if not self.current_song:
            await self.highrise.chat("📻 Nothing is currently playing")
            return
        
        status = await self.api_status()
        
        msg = (
            f"🎧 NOW PLAYING:\n"
            f"📀 {self.current_song.title}\n"
            f"👤 Requested by: @{self.current_song.requested_by}\n"
        )
        
        if status and status.get('current_track'):
            track = status['current_track']
            if track.get('duration'):
                msg += f"⏱️ Duration: {self.format_duration(track['duration'])}\n"
        
        if self.song_queue:
            msg += f"📋 Queue: {len(self.song_queue)} song(s)"
        
        await self.highrise.chat(msg)

    async def cmd_status(self, user: User, args: str) -> None:
        """Show bot and radio status"""
        try:
            status = await self.api_status()
            
            if status:
                stream_status = "🟢 ACTIVE" if status.get('stream_active') else "🔴 INACTIVE"
                player_status = status.get('status', 'unknown').upper()
                
                msg = (
                    f"📡 RADIO STATUS:\n"
                    f"🎵 Player: {player_status}\n"
                    f"📻 Stream: {stream_status}\n"
                )
                
                if self.current_song:
                    msg += f"🎧 Playing: {self.current_song.title}\n"
                
                msg += f"📋 Queue: {len(self.song_queue)} song(s)"
                
                await self.highrise.chat(msg)
            else:
                await self.highrise.chat("❌ Could not fetch status")
                
        except Exception as e:
            print(f"❌ Status error: {e}")
            await self.highrise.chat("❌ Status check failed")

    async def cmd_get_url(self, user: User, args: str) -> None:
        """Get radio stream URL"""
        if not self.radio_url:
            await self.fetch_radio_url()
        
        if self.radio_url:
            msg = (
                f"📻 RADIO STREAM URL:\n"
                f"{self.radio_url}\n\n"
                f"📍 How to use:\n"
                f"1. Copy the URL above\n"
                f"2. Go to room settings\n"
                f"3. Paste in 'Room Music' section\n"
                f"4. Use !play commands to control music!"
            )
            
            if self.current_song:
                msg += f"\n\n🎵 Now playing: {self.current_song.title}"
            
            await self.highrise.send_whisper(user.id, msg)
            await self.highrise.chat(f"📻 @{user.username} check your DMs for the radio URL!")
        else:
            await self.highrise.send_whisper(user.id, "❌ Could not fetch radio URL")

    async def cmd_stats(self, user: User, args: str) -> None:
        """Show bot statistics"""
        if not self.start_time:
            await self.highrise.chat("❌ Stats not available")
            return
        
        uptime = datetime.now() - self.start_time
        hours = uptime.seconds // 3600
        minutes = (uptime.seconds % 3600) // 60
        
        stats = (
            f"📊 BOT STATISTICS:\n"
            f"⏰ Uptime: {uptime.days}d {hours}h {minutes}m\n"
            f"🎵 Songs played: {self.songs_played}\n"
            f"📋 Queue size: {len(self.song_queue)}\n"
            f"🎧 Currently playing: {'Yes' if self.current_song else 'No'}"
        )
        
        await self.highrise.chat(stats)

    async def cmd_clear_queue(self, user: User, args: str) -> None:
        """Clear the song queue (admin only)"""
        if not self.is_admin(user):
            await self.highrise.send_whisper(user.id, "❌ Only admins can clear the queue")
            return
        
        queue_size = len(self.song_queue)
        self.song_queue.clear()
        
        await self.highrise.chat(f"🗑️ Queue cleared ({queue_size} songs removed) by @{user.username}")

    async def cmd_help(self, user: User, args: str) -> None:
        """Show help menu"""
        help_text = (
            "🎵 MUSIC BOT COMMANDS:\n\n"
            "🎧 Playback:\n"
            "!play [song] - Play/queue a song\n"
            "!skip - Skip current song\n"
            "!np - Now playing info\n"
            "!queue - View song queue\n\n"
            "🔍 Discovery:\n"
            "!search [query] - Search for songs\n\n"
            "📡 Radio:\n"
            "!url - Get radio stream URL\n"
            "!status - Check radio status\n"
            "!stats - Bot statistics\n\n"
            "🎛️ Admin Commands:\n"
            "!stop - Stop playback & clear queue\n"
            "!clear - Clear queue only\n\n"
            "💡 TIP: Add radio URL to room settings once,\n"
            "then control music with commands!"
        )
        
        await self.highrise.send_whisper(user.id, help_text)

    # ==================== API Methods ====================
    
    async def api_search(self, query: str, limit: int = 10) -> List[Dict]:
        """Search for music via API"""
        if not self.session or self.session.closed:
            print("❌ HTTP session not available")
            return []
        
        try:
            async with self.session.get(
                f"{self.api_base}/api/search",
                params={'q': query, 'limit': limit}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get('results', [])
                else:
                    print(f"❌ Search API returned status {resp.status}")
                return []
        except asyncio.TimeoutError:
            print(f"❌ API search timeout for query: {query}")
            return []
        except Exception as e:
            print(f"❌ API search error: {e}")
            return []

    async def api_play(self, video_url: str) -> Optional[Dict]:
        """Play a song via API"""
        if not self.session or self.session.closed:
            print("❌ HTTP session not available")
            return None
        
        try:
            async with self.session.post(
                f"{self.api_base}/api/play",
                data={'video_url': video_url}
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    print(f"❌ Play API returned status {resp.status}")
                return None
        except asyncio.TimeoutError:
            print(f"❌ API play timeout")
            return None
        except Exception as e:
            print(f"❌ API play error: {e}")
            return None

    async def api_stop(self) -> bool:
        """Stop playback via API"""
        if not self.session or self.session.closed:
            print("❌ HTTP session not available")
            return False
        
        try:
            async with self.session.post(f"{self.api_base}/api/stop") as resp:
                return resp.status == 200
        except asyncio.TimeoutError:
            print(f"❌ API stop timeout")
            return False
        except Exception as e:
            print(f"❌ API stop error: {e}")
            return False

    async def api_status(self) -> Optional[Dict]:
        """Get player status via API"""
        if not self.session or self.session.closed:
            print("❌ HTTP session not available")
            return None
        
        try:
            async with self.session.get(f"{self.api_base}/api/status") as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
        except asyncio.TimeoutError:
            print(f"❌ API status timeout")
            return None
        except Exception as e:
            print(f"❌ API status error: {e}")
            return None

    async def fetch_radio_url(self) -> None:
        """Fetch and cache radio URL"""
        if not self.session or self.session.closed:
            print("❌ HTTP session not available for fetching radio URL")
            return
        
        try:
            async with self.session.get(f"{self.api_base}/api/radio/url") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.radio_url = data.get('radio_url')
                    print(f"✅ Radio URL cached: {self.radio_url}")
                else:
                    print(f"❌ Failed to fetch radio URL: status {resp.status}")
        except asyncio.TimeoutError:
            print(f"❌ Radio URL fetch timeout")
        except Exception as e:
            print(f"❌ Failed to fetch radio URL: {e}")

    # ==================== Utility Methods ====================
    
    def is_admin(self, user: User) -> bool:
        """Check if user is an admin"""
        return user.username in MusicBotConfig.ADMINS

    def check_cooldown(self, user: User) -> bool:
        """Check if user is on cooldown"""
        now = datetime.now()
        if user.id in self.user_cooldowns:
            time_since = (now - self.user_cooldowns[user.id]).total_seconds()
            if time_since < MusicBotConfig.COMMAND_COOLDOWN:
                return False
        
        self.user_cooldowns[user.id] = now
        return True

    def format_duration(self, seconds: int) -> str:
        """Format seconds into MM:SS"""
        if seconds <= 0:
            return "Live"
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}:{secs:02d}"

    async def send_error(self, user: User, message: str) -> None:
        """Send error message to user"""
        await self.highrise.send_whisper(user.id, f"❌ {message}")

    async def roam_continuously(self) -> None:
        """Make bot roam around the room"""
        while self.is_connected:
            try:
                next_pos = self.roaming_positions[self.current_roam_index]
                await self.highrise.walk_to(next_pos)
                
                self.current_roam_index = (self.current_roam_index + 1) % len(self.roaming_positions)
                await asyncio.sleep(MusicBotConfig.ROAM_INTERVAL)
                
            except asyncio.CancelledError:
                print("🚶 Roaming task cancelled")
                break
            except Exception as e:
                print(f"❌ Roaming error: {e}")
                await asyncio.sleep(10)

# ==================== Bot Runner ====================

if __name__ == "__main__":
    import sys
    
    # Load environment variables
    api_token = os.getenv("HIGHRISE_API_TOKEN")
    room_id = os.getenv("HIGHRISE_ROOM_ID")
    
    if not api_token or not room_id:
        print("=" * 50)
        print("❌ CONFIGURATION ERROR")
        print("=" * 50)
        print("Missing required environment variables:")
        print("- HIGHRISE_API_TOKEN")
        print("- HIGHRISE_ROOM_ID")
        print("- MUSIC_API_URL")
        print("\nPlease set these in your .env file")
        print("=" * 50)
        sys.exit(1)
    
    print("=" * 50)
    print("🚀 STARTING MUSIC BOT")
    print("=" * 50)
    
    # Create and run bot
    bot = AzuraCastMusicBot()
    
    try:
        asyncio.run(main([BotDefinition(bot, room_id, api_token)]))
    except KeyboardInterrupt:
        print("\n" + "=" * 50)
        print("🛑 Bot stopped by user")
        print("=" * 50)
    except Exception as e:
        print("\n" + "=" * 50)
        print(f"💥 Bot crashed: {e}")
        print("=" * 50)
        import traceback
        traceback.print_exc()
