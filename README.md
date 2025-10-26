# 🤖 Virus Music Bot

Highrise bot for controlling music streaming from YouTube.

## Features
- 🎵 Control music with chat commands
- 🔍 Search and play YouTube music
- 📻 Get radio stream URL for Highrise
- 🎧 Now playing information

## Deployment

### Railway Deployment
1. Fork this repository
2. contact owner
4. Select your forked repository

### Environment Variables
Set these in Railway dashboard:
- `MUSIC_API_URL`: Your backend API URL (from virus-music-backend)
- `ROOM_ID`: Your Highrise room ID
- `BOT_TOKEN`: Your Highrise bot token

## Bot Commands
- `!play [song]` - Play music from YouTube
- `!stop` - Stop current playback
- `!url` - Get radio stream URL
- `!np` - Now playing information
- `!status` - Stream status
- `!help` - Show all commands

## Setup Steps
1. Deploy the backend first
2. Deploy this bot with environment variables
3. In Highrise, type `!url` to get stream URL
4. Add URL to Highrise room music settings
5. Use `!play songname` to play music!