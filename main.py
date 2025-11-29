import discord
from discord.ext import commands
from discord import ui
import asyncio
import re
from datetime import datetime, timedelta, timezone
import random
from flask import Flask
from threading import Thread
import os

# Token handling for Replit
TOKEN = os.environ['BOTTOKEN']

if not TOKEN:
    print("❌ ERROR: DISCORD_BOT_TOKEN not found in environment variables!")
    print("💡 Please add DISCORD_BOT_TOKEN to your Replit Secrets")
    exit(1)

# Flask web server for uptime (keep this for Replit too)
app = Flask('')

@app.route('/')
def home():
    return "🤖 Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    server = Thread(target=run)
    server.start()

# Start the web server (important for Replit to keep bot alive)
keep_alive()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.reactions = True

bot = commands.Bot(command_prefix=",,", intents=intents)
bot.remove_command("help")

# ---------------------------------------------------------
LOG_CHANNEL_ID = 1418106413640581191

# ROLE IDS FOR COMMAND ACCESS
FULL_ADMIN_ROLE_IDS = [1417941498028101765, 1402332135536197773, 1376250853870010479]  # Full access to everything
TICKET_ADMIN_ROLE_IDS = FULL_ADMIN_ROLE_IDS + [1420001481322401893]  # Full admins + ticket admin
GIVEAWAY_ROLE_IDS = FULL_ADMIN_ROLE_IDS + [1435640529525149837]  # Full admins + giveaway role

# ---------------------------------------------------------

# ---------------------------
# Utility: parse durations
# ---------------------------
def parse_duration_to_seconds(s: str):
    s = s.strip().lower()
    pattern = r"^(\d+)\s*([smhd])$"
    m = re.match(pattern, s)
    if not m:
        return None
    val = int(m.group(1))
    unit = m.group(2)
    if unit == "s":
        return val
    if unit == "m":
        return val * 60
    if unit == "h":
        return val * 3600
    if unit == "d":
        return val * 86400
    return None

# ---------------------------
# Permission Check Functions
# ---------------------------
def has_full_admin_access():
    async def predicate(ctx):
        if ctx.author.guild_permissions.administrator:
            return True
        user_roles = [role.id for role in ctx.author.roles]
        return any(role_id in user_roles for role_id in FULL_ADMIN_ROLE_IDS)
    return commands.check(predicate)

def has_ticket_admin_access():
    async def predicate(ctx):
        if ctx.author.guild_permissions.administrator:
            return True
        user_roles = [role.id for role in ctx.author.roles]
        return any(role_id in user_roles for role_id in TICKET_ADMIN_ROLE_IDS)
    return commands.check(predicate)

def has_giveaway_access():
    async def predicate(ctx):
        if ctx.author.guild_permissions.administrator:
            return True
        user_roles = [role.id for role in ctx.author.roles]
        return any(role_id in user_roles for role_id in GIVEAWAY_ROLE_IDS)
    return commands.check(predicate)

def has_moderation_access():
    async def predicate(ctx):
        if ctx.author.guild_permissions.administrator:
            return True
        user_roles = [role.id for role in ctx.author.roles]
        return any(role_id in user_roles for role_id in FULL_ADMIN_ROLE_IDS)
    return commands.check(predicate)

# ---------------------------
# Ready event with proper command syncing
# ---------------------------
@bot.event
async def on_ready():
    print(f"✅ Bot is ready! Logged in as {bot.user}")

    # Sync slash commands with better error handling
    try:
        synced = await bot.tree.sync()
        print(f"✅ Successfully synced {len(synced)} slash command(s)")

        # Print all synced commands for debugging
        for command in synced:
            print(f"  - /{command.name}")

    except Exception as e:
        print(f"❌ Failed to sync slash commands: {e}")

    # Add ticket system cog
    try:
        await bot.add_cog(TicketSystem(bot))
        print("✅ TicketSystem cog loaded")
    except Exception as e:
        print(f"❌ Failed to load TicketSystem cog: {e}")

    # Send ready message to log channel
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        try:
            await log_channel.send("✅ **Bot is now Ready!** 😎")
        except Exception as e:
            print(f"Note: Couldn't send ready message to log channel: {e}")

# ---------------------------
# Small helper to send logs
# ---------------------------
async def send_log(content: str, file: discord.File = None):
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if not log_channel:
        return
    try:
        if file:
            await log_channel.send(content, file=file)
        else:
            await log_channel.send(content)
    except Exception as e:
        print(f"Failed to send log: {e}")

# ============================================================
#                       GIVEAWAY SYSTEM
# ============================================================
active_giveaways = {}
giveaway_id_counter = 1

def parse_duration(duration: str) -> int:
    """Parse duration string to seconds"""
    units = {
        's': 1, 'sec': 1, 'secs': 1, 'second': 1, 'seconds': 1,
        'm': 60, 'min': 60, 'mins': 60, 'minute': 60, 'minutes': 60,
        'h': 3600, 'hr': 3600, 'hrs': 3600, 'hour': 3600, 'hours': 3600,
        'd': 86400, 'day': 86400, 'days': 86400
    }

    duration = duration.lower().strip()
    total_seconds = 0
    parts = duration.split()

    for part in parts:
        num_str = ''
        unit_str = ''
        for char in part:
            if char.isdigit():
                num_str += char
            else:
                unit_str += char

        if not num_str:
            continue

        num = int(num_str)
        unit_str = unit_str.strip()

        if unit_str in units:
            total_seconds += num * units[unit_str]
        elif not unit_str:
            total_seconds += num * 60

    return total_seconds if total_seconds > 0 else 0

async def end_giveaway(giveaway_id: int):
    """End a giveaway and pick winners"""
    if giveaway_id not in active_giveaways:
        return

    giveaway = active_giveaways[giveaway_id]
    if giveaway['ended']:
        return

    giveaway['ended'] = True

    try:
        channel = bot.get_channel(giveaway['channel_id'])
        if not channel:
            return

        try:
            message = await channel.fetch_message(giveaway['message_id'])
        except discord.NotFound:
            return

        # Get reaction participants
        for reaction in message.reactions:
            if str(reaction.emoji) == "🎉":
                users = [user async for user in reaction.users() if not user.bot]
                giveaway['participants'] = [user.id for user in users]
                break

        participants = giveaway['participants']
        log_channel = bot.get_channel(LOG_CHANNEL_ID)

        if not participants:
            embed = discord.Embed(
                title=f"🎉 **{giveaway['prize']}** 🎉",
                description=f"**Winners:** No participants 😢\n"
                            f"**Hosted by:** <@{giveaway['host_id']}>\n\n"
                            f"Giveaway has ended with no participants.",
                color=0xff0000)
            if giveaway.get('image_url'):
                embed.set_image(url=giveaway['image_url'])
            await message.edit(embed=embed)

            if log_channel:
                log_embed = discord.Embed(
                    title="🎉 Giveaway Ended - No Participants",
                    description=f"**Prize:** {giveaway['prize']}\n"
                                f"**Host:** <@{giveaway['host_id']}>\n"
                                f"**Giveaway ID:** {giveaway_id}\n"
                                f"**Participants:** 0\n"
                                f"❌ **No winners** - No one entered the giveaway",
                    color=0xff0000,
                    timestamp=datetime.now(timezone.utc))
                if giveaway.get('image_url'):
                    log_embed.set_image(url=giveaway['image_url'])
                await log_channel.send(embed=log_embed)

            await channel.send(f"🎉 Giveaway for **{giveaway['prize']}** ended with no participants!")
            return

        # Pick winners
        winners_count = min(len(participants), giveaway['winners'])
        winners = random.sample(participants, winners_count)
        winners_mentions = ', '.join([f"<@{winner_id}>" for winner_id in winners])

        # Update embed
        embed = discord.Embed(
            title=f"🎉 **{giveaway['prize']}** 🎉",
            description=f"**Winners:** {winners_mentions}\n"
                        f"**Participants:** {len(participants)}\n"
                        f"**Hosted by:** <@{giveaway['host_id']}>\n\n"
                        f"Congratulations to the winners! 🎊",
            color=0xffa500)
        embed.set_footer(text=f"Giveaway ID: {giveaway_id} | Ended")

        if giveaway.get('image_url'):
            embed.set_image(url=giveaway['image_url'])

        await message.edit(embed=embed)
        winners_text = f"🎉 **Giveaway Ended!** 🎉\n\n**Prize:** {giveaway['prize']}\n**Winners:** {winners_mentions}\n**Host:** <@{giveaway['host_id']}>\nCongratulations! 🎊"
        await channel.send(winners_text)

        if log_channel:
            log_embed = discord.Embed(
                title="🎉 Giveaway Ended - Winners Selected",
                description=f"**Prize:** {giveaway['prize']}\n"
                            f"**Host:** <@{giveaway['host_id']}>\n"
                            f"**Giveaway ID:** {giveaway_id}\n"
                            f"**Participants:** {len(participants)}\n"
                            f"**Winners:** {winners_mentions}",
                color=0x00ff00,
                timestamp=datetime.now(timezone.utc))
            if giveaway.get('image_url'):
                log_embed.set_image(url=giveaway['image_url'])
            await log_channel.send(embed=log_embed)

    except Exception as e:
        print(f"Error ending giveaway {giveaway_id}: {e}")

# SLASH COMMAND FOR GIVEAWAY CREATE
@bot.tree.command(name="giveaway_create", description="Create a new giveaway")
async def giveaway_create(interaction: discord.Interaction, prize: str, duration: str, winners: int, host: discord.Member = None):
    """Create a giveaway using slash command"""
    # Check permissions
    user_roles = [role.id for role in interaction.user.roles]
    has_access = any(role_id in user_roles for role_id in GIVEAWAY_ROLE_IDS) or interaction.user.guild_permissions.administrator

    if not has_access:
        await interaction.response.send_message("❌ You don't have permission to create giveaways!", ephemeral=True)
        return

    if host is None:
        host = interaction.user

    if winners < 1:
        await interaction.response.send_message("❌ Winners must be at least 1!", ephemeral=True)
        return

    duration_seconds = parse_duration(duration)
    if duration_seconds <= 0:
        await interaction.response.send_message("❌ Please provide a valid duration (e.g., 1h, 30m, 1d, 10s)", ephemeral=True)
        return

    end_time = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)
    global giveaway_id_counter
    giveaway_id = giveaway_id_counter
    giveaway_id_counter += 1

    embed = discord.Embed(
        title=f"🎉 **{prize}** 🎉",
        description=f"**Winners:** {winners}\n"
                    f"**Ends:** <t:{int(end_time.timestamp())}:R> (<t:{int(end_time.timestamp())}:F>)\n"
                    f"**Hosted by:** {host.mention}\n\n"
                    f"Click the 🎉 button to enter!",
        color=0x00ff00,
        timestamp=end_time)
    embed.set_footer(text=f"Giveaway ID: {giveaway_id} | Ends at")

    await interaction.response.send_message(embed=embed)
    giveaway_msg = await interaction.original_response()
    await giveaway_msg.add_reaction("🎉")

    active_giveaways[giveaway_id] = {
        'message_id': giveaway_msg.id,
        'channel_id': interaction.channel.id,
        'prize': prize,
        'winners': winners,
        'end_time': end_time,
        'host_id': host.id,
        'participants': [],
        'ended': False,
        'image_url': None
    }

    success_msg = f"✅ Giveaway created successfully! ID: `{giveaway_id}`\n**Host:** {host.mention}"
    await interaction.followup.send(success_msg, ephemeral=True)

    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        log_embed = discord.Embed(
            title="🎉 Giveaway Created",
            description=f"**Prize:** {prize}\n"
                        f"**Winners:** {winners}\n"
                        f"**Duration:** {duration}\n"
                        f"**Ends:** <t:{int(end_time.timestamp())}:F>\n"
                        f"**Host:** {host.mention}\n"
                        f"**Created by:** {interaction.user.mention}\n"
                        f"**Channel:** {interaction.channel.mention}\n"
                        f"**Giveaway ID:** {giveaway_id}",
            color=0x00ff00,
            timestamp=datetime.now(timezone.utc))
        await log_channel.send(embed=log_embed)

    await asyncio.sleep(duration_seconds)
    await end_giveaway(giveaway_id)

# SLASH COMMAND FOR GIVEAWAY END
@bot.tree.command(name="giveaway_end", description="End a giveaway early")
async def giveaway_end(interaction: discord.Interaction, giveaway_id: int):
    """End a giveaway early using slash command"""
    # Check permissions
    user_roles = [role.id for role in interaction.user.roles]
    has_access = any(role_id in user_roles for role_id in GIVEAWAY_ROLE_IDS) or interaction.user.guild_permissions.administrator

    if not has_access:
        await interaction.response.send_message("❌ You don't have permission to end giveaways!", ephemeral=True)
        return

    if giveaway_id not in active_giveaways:
        await interaction.response.send_message("❌ Giveaway not found or already ended.", ephemeral=True)
        return

    giveaway = active_giveaways[giveaway_id]
    if giveaway['host_id'] != interaction.user.id and not any(role_id in [role.id for role in interaction.user.roles] for role_id in FULL_ADMIN_ROLE_IDS):
        await interaction.response.send_message("❌ You can only end giveaways that you hosted!", ephemeral=True)
        return

    await end_giveaway(giveaway_id)
    await interaction.response.send_message(f"✅ Giveaway `{giveaway_id}` ended successfully!")

# SLASH COMMAND FOR GIVEAWAY LIST
@bot.tree.command(name="giveaway_list", description="List all active giveaways")
async def giveaway_list(interaction: discord.Interaction):
    """List all active giveaways using slash command"""
    if not active_giveaways:
        await interaction.response.send_message("📝 No active giveaways!")
        return

    embed = discord.Embed(title="🎉 Active Giveaways", color=0x00ff00)
    for giveaway_id, giveaway in active_giveaways.items():
        if not giveaway['ended']:
            time_left = giveaway['end_time'] - datetime.now(timezone.utc)
            hours, remainder = divmod(int(time_left.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            embed.add_field(
                name=f"ID: {giveaway_id} - {giveaway['prize']}",
                value=f"Winners: {giveaway['winners']} | Ends in: {hours}h {minutes}m\nHosted by: <@{giveaway['host_id']}>",
                inline=False)
    await interaction.response.send_message(embed=embed)

# SLASH COMMAND FOR GIVEAWAY REROLL
@bot.tree.command(name="giveaway_reroll", description="Reroll winners for an ended giveaway")
async def giveaway_reroll(interaction: discord.Interaction, giveaway_id: int, winners: int = 1):
    """Reroll winners using slash command"""
    # Check permissions
    user_roles = [role.id for role in interaction.user.roles]
    has_access = any(role_id in user_roles for role_id in GIVEAWAY_ROLE_IDS) or interaction.user.guild_permissions.administrator

    if not has_access:
        await interaction.response.send_message("❌ You don't have permission to reroll giveaways!", ephemeral=True)
        return

    if giveaway_id not in active_giveaways:
        await interaction.response.send_message("❌ Giveaway not found!", ephemeral=True)
        return

    giveaway = active_giveaways[giveaway_id]
    if not giveaway['ended']:
        await interaction.response.send_message("❌ Giveaway hasn't ended yet!", ephemeral=True)
        return

    if not giveaway['participants']:
        await interaction.response.send_message("❌ No participants to reroll from!", ephemeral=True)
        return

    winners_count = min(len(giveaway['participants']), winners)
    new_winners = random.sample(giveaway['participants'], winners_count)
    winners_mentions = ', '.join([f"<@{winner_id}>" for winner_id in new_winners])

    await interaction.response.send_message(
        f"🎉 **Rerolled Winners for** `{giveaway['prize']}`\n\nNew winners: {winners_mentions}\n**Host:** <@{giveaway['host_id']}>")

# ============================================================
#                    MODERATION SLASH COMMANDS
# ============================================================

# SLASH COMMAND - TIMEOUT
@bot.tree.command(name="timeout", description="Timeout a user")
async def timeout_slash(interaction: discord.Interaction, user: discord.Member, duration: str, reason: str = None):
    """Timeout a user using slash command"""
    # Check permissions
    user_roles = [role.id for role in interaction.user.roles]
    has_access = any(role_id in user_roles for role_id in FULL_ADMIN_ROLE_IDS) or interaction.user.guild_permissions.administrator

    if not has_access:
        await interaction.response.send_message("❌ You don't have permission to timeout users!", ephemeral=True)
        return

    seconds = parse_duration_to_seconds(duration)
    if seconds is None:
        await interaction.response.send_message("❌ Invalid duration format. Use examples: 30s, 10m, 2h, 1d", ephemeral=True)
        return

    until = datetime.now(timezone.utc) + timedelta(seconds=seconds)

    try:
        await user.edit(timed_out_until=until)
        await interaction.response.send_message(f"⏳ {user.mention} timed out for {duration}.")
        await send_log(f"⏳ **Timeout** {user.mention} by {interaction.user.mention} for {duration} — Reason: {reason}")
    except Exception as e:
        await interaction.response.send_message("❌ Could not apply timeout (bot missing permission or role hierarchy).", ephemeral=True)

# SLASH COMMAND - BAN
@bot.tree.command(name="ban", description="Ban a user from the server")
async def ban_slash(interaction: discord.Interaction, user: discord.Member, reason: str = None):
    """Ban a user using slash command"""
    # Check permissions
    user_roles = [role.id for role in interaction.user.roles]
    has_access = any(role_id in user_roles for role_id in FULL_ADMIN_ROLE_IDS) or interaction.user.guild_permissions.administrator

    if not has_access:
        await interaction.response.send_message("❌ You don't have permission to ban users!", ephemeral=True)
        return

    try:
        await interaction.guild.ban(user, reason=reason)
        await interaction.response.send_message(f"🔨 Banned {user.mention}.")
        await send_log(f"🔨 **Banned** {user.mention} by {interaction.user.mention} — Reason: {reason}")
    except Exception as e:
        await interaction.response.send_message("❌ Could not ban that member (missing permissions / role hierarchy).", ephemeral=True)

# SLASH COMMAND - KICK
@bot.tree.command(name="kick", description="Kick a user from the server")
async def kick_slash(interaction: discord.Interaction, user: discord.Member, reason: str = None):
    """Kick a user using slash command"""
    # Check permissions
    user_roles = [role.id for role in interaction.user.roles]
    has_access = any(role_id in user_roles for role_id in FULL_ADMIN_ROLE_IDS) or interaction.user.guild_permissions.administrator

    if not has_access:
        await interaction.response.send_message("❌ You don't have permission to kick users!", ephemeral=True)
        return

    try:
        await interaction.guild.kick(user, reason=reason)
        await interaction.response.send_message(f"⛔ Kicked {user.mention}.")
        await send_log(f"⛔ **Kicked** {user.mention} by {interaction.user.mention} — Reason: {reason}")
    except Exception as e:
        await interaction.response.send_message("❌ Could not kick that member (missing permissions / role hierarchy).", ephemeral=True)

# SLASH COMMAND - GIVE ROLE
@bot.tree.command(name="give_role", description="Give roles to a user")
async def give_role_slash(interaction: discord.Interaction, user: discord.Member, role: discord.Role):
    """Give role to user using slash command"""
    # Check permissions
    user_roles = [role.id for role in interaction.user.roles]
    has_access = any(role_id in user_roles for role_id in FULL_ADMIN_ROLE_IDS) or interaction.user.guild_permissions.administrator

    if not has_access:
        await interaction.response.send_message("❌ You don't have permission to give roles!", ephemeral=True)
        return

    try:
        await user.add_roles(role)
        await interaction.response.send_message(f"✅ **Role Added!**\n👤 User: {user.mention}\n🎭 Role: {role.name}")
        await send_log(f"🛠️ **Role Added**\nAdmin: {interaction.user.mention}\nUser: {user.mention}\nRole: {role.name}")
    except Exception:
        await interaction.response.send_message("❌ Could not add role (check bot permissions and role hierarchy).", ephemeral=True)

# SLASH COMMAND - REMOVE ROLE
@bot.tree.command(name="remove_role", description="Remove roles from a user")
async def remove_role_slash(interaction: discord.Interaction, user: discord.Member, role: discord.Role):
    """Remove role from user using slash command"""
    # Check permissions
    user_roles = [role.id for role in interaction.user.roles]
    has_access = any(role_id in user_roles for role_id in FULL_ADMIN_ROLE_IDS) or interaction.user.guild_permissions.administrator

    if not has_access:
        await interaction.response.send_message("❌ You don't have permission to remove roles!", ephemeral=True)
        return

    try:
        await user.remove_roles(role)
        await interaction.response.send_message(f"🗑️ **Role Removed!**\n👤 User: {user.mention}\n🎭 Removed: {role.name}")
        await send_log(f"🗑️ **Role Removed**\nAdmin: {interaction.user.mention}\nUser: {user.mention}\nRemoved: {role.name}")
    except Exception:
        await interaction.response.send_message("❌ Could not remove role (check permissions).", ephemeral=True)

# SLASH COMMAND - CHANGE NICKNAME
@bot.tree.command(name="change_nickname", description="Change a user's nickname")
async def change_nickname_slash(interaction: discord.Interaction, user: discord.Member, nickname: str):
    """Change nickname using slash command"""
    # Check permissions
    user_roles = [role.id for role in interaction.user.roles]
    has_access = any(role_id in user_roles for role_id in FULL_ADMIN_ROLE_IDS) or interaction.user.guild_permissions.administrator

    if not has_access:
        await interaction.response.send_message("❌ You don't have permission to change nicknames!", ephemeral=True)
        return

    try:
        await user.edit(nick=nickname)
        await interaction.response.send_message(f"✏️ Nickname changed for {user.mention} → **{nickname}**")
        await send_log(f"✏️ **Nickname Changed**\nAdmin: {interaction.user.mention}\nUser: {user.mention}\nNew Nickname: **{nickname}**")
    except Exception:
        await interaction.response.send_message("❌ I don't have permission to change that nickname.", ephemeral=True)

# ============================================================
#                    UTILITY SLASH COMMANDS
# ============================================================

# SLASH COMMAND - TIMER
@bot.tree.command(name="timer", description="Start a timer")
async def timer_slash(interaction: discord.Interaction, duration: str, message: str = None):
    """Start a timer using slash command"""
    seconds = parse_duration_to_seconds(duration)
    if seconds is None:
        await interaction.response.send_message("❌ Invalid duration format. Use: 30s, 10m, 2h, 1d", ephemeral=True)
        return

    await interaction.response.send_message(f"⏱️ Timer started for **{duration}** — I'll remind you when it's done, {interaction.user.mention}.")

    async def run_timer():
        try:
            await asyncio.sleep(seconds)
            if message:
                await interaction.channel.send(f"⏰ **Timer finished** ({duration}) — {interaction.user.mention}\n{message}")
            else:
                await interaction.channel.send(f"⏰ **Timer finished** ({duration}) — {interaction.user.mention}")
        except asyncio.CancelledError:
            pass
        finally:
            active_timers.pop(interaction.user.id, None)

    task = bot.loop.create_task(run_timer())
    active_timers[interaction.user.id] = task

# SLASH COMMAND - END TIMER
@bot.tree.command(name="end_timer", description="Stop your active timer")
async def end_timer_slash(interaction: discord.Interaction):
    """End timer using slash command"""
    user_id = interaction.user.id
    task = active_timers.get(user_id)
    if task and not task.done():
        task.cancel()
        await interaction.response.send_message(f"⏹️ Timer stopped, {interaction.user.mention}")
        del active_timers[user_id]
    else:
        await interaction.response.send_message("❌ You don't have an active timer.", ephemeral=True)

# SLASH COMMAND - AFK
@bot.tree.command(name="afk", description="Set yourself as AFK")
async def afk_slash(interaction: discord.Interaction, reason: str = "AFK"):
    """Set AFK using slash command"""
    afk_users[interaction.user.id] = {
        "since": datetime.now(timezone.utc),
        "reason": reason,
        "channel": interaction.channel.id,
        "pinged_by": []
    }
    await interaction.response.send_message(f"💤 {interaction.user.mention} is now AFK: {reason}")

# SLASH COMMAND - HELP
@bot.tree.command(name="help", description="Show all available commands")
async def help_slash(interaction: discord.Interaction):
    """Show help using slash command"""
    embed = discord.Embed(title="✨ BOT COMMANDS PANEL", description="All available slash commands with role permissions", color=0x2F3136)

    divider = "───────────────────────────────"

    # Giveaway Commands
    embed.add_field(name=f"{divider}\n🎁 GIVEAWAY COMMANDS\n{divider}", value="\u200b", inline=False)
    embed.add_field(name="/giveaway_create", value="Create a new giveaway\n`prize`, `duration`, `winners`, `host`\n👑 Full Admins + 🎉 Giveaway Role", inline=True)
    embed.add_field(name="/giveaway_end", value="End a giveaway early\n`giveaway_id`\n👑 Full Admins + 🎉 Giveaway Role", inline=True)
    embed.add_field(name="/giveaway_list", value="List all active giveaways\n👥 Everyone", inline=True)
    embed.add_field(name="/giveaway_reroll", value="Reroll winners\n`giveaway_id`, `winners`\n👑 Full Admins + 🎉 Giveaway Role", inline=True)

    # Moderation Commands
    embed.add_field(name=f"{divider}\n🔐 MODERATION COMMANDS\n{divider}", value="\u200b", inline=False)
    embed.add_field(name="/timeout", value="Timeout a user\n`user`, `duration`, `reason`\n👑 Full Admins Only", inline=True)
    embed.add_field(name="/ban", value="Ban a user\n`user`, `reason`\n👑 Full Admins Only", inline=True)
    embed.add_field(name="/kick", value="Kick a user\n`user`, `reason`\n👑 Full Admins Only", inline=True)
    embed.add_field(name="/give_role", value="Give role to user\n`user`, `role`\n👑 Full Admins Only", inline=True)
    embed.add_field(name="/remove_role", value="Remove role from user\n`user`, `role`\n👑 Full Admins Only", inline=True)
    embed.add_field(name="/change_nickname", value="Change nickname\n`user`, `nickname`\n👑 Full Admins Only", inline=True)

    # Utility Commands
    embed.add_field(name=f"{divider}\n⚙️ UTILITY COMMANDS\n{divider}", value="\u200b", inline=False)
    embed.add_field(name="/timer", value="Start a timer\n`duration`, `message`\n👥 Everyone", inline=True)
    embed.add_field(name="/end_timer", value="Stop your timer\n👥 Everyone", inline=True)
    embed.add_field(name="/afk", value="Set yourself as AFK\n`reason`\n👥 Everyone", inline=True)
    embed.add_field(name="/help", value="Show this help menu\n👥 Everyone", inline=True)

    # Ticket Commands
    embed.add_field(name=f"{divider}\n🎫 TICKET COMMANDS\n{divider}", value="\u200b", inline=False)
    embed.add_field(name="/ticket_setup", value="Setup ticket system\n`channel`\n👑 Full Admins + 🎫 Ticket Admin", inline=True)
    embed.add_field(name="/ticket_close", value="Close current ticket\n👑 Full Admins + 🎫 Ticket Admin", inline=True)

    # Role Legend
    embed.add_field(name=f"{divider}\n🔑 ROLE PERMISSIONS\n{divider}", value="\u200b", inline=False)
    embed.add_field(name="👑 Full Admins", value="Can use ALL commands", inline=True)
    embed.add_field(name="🎫 Ticket Admin", value="Can only use ticket commands", inline=True)
    embed.add_field(name="🎉 Giveaway Role", value="Can only use giveaway commands", inline=True)

    embed.set_footer(text="💡 Use slash commands for better experience!")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ============================================================
#                    TICKET SYSTEM SLASH COMMANDS
# ============================================================

# SLASH COMMAND - TICKET SETUP
@bot.tree.command(name="ticket_setup", description="Setup the ticket system in a channel")
async def ticket_setup_slash(interaction: discord.Interaction, channel: discord.TextChannel = None):
    """Setup ticket system using slash command"""
    # Check permissions
    user_roles = [role.id for role in interaction.user.roles]
    has_access = any(role_id in user_roles for role_id in TICKET_ADMIN_ROLE_IDS) or interaction.user.guild_permissions.administrator

    if not has_access:
        await interaction.response.send_message("❌ You don't have permission to setup tickets!", ephemeral=True)
        return

    target_channel = channel or interaction.channel
    ticket_system = bot.get_cog('TicketSystem')
    if not ticket_system:
        ticket_system = TicketSystem(bot)
        await bot.add_cog(ticket_system)

    await ticket_system.create_ticket_panel(target_channel.id)
    await interaction.response.send_message(f"✅ Ticket panel created/updated in {target_channel.mention}", ephemeral=True)

# SLASH COMMAND - TICKET CLOSE
@bot.tree.command(name="ticket_close", description="Close the current ticket")
async def ticket_close_slash(interaction: discord.Interaction):
    """Close ticket using slash command"""
    # Check permissions
    user_roles = [role.id for role in interaction.user.roles]
    has_access = any(role_id in user_roles for role_id in TICKET_ADMIN_ROLE_IDS) or interaction.user.guild_permissions.administrator

    if not has_access:
        await interaction.response.send_message("❌ You don't have permission to close tickets!", ephemeral=True)
        return

    ticket_system = bot.get_cog('TicketSystem')
    if ticket_system:
        await ticket_system.close_ticket(interaction, interaction.channel.id)
    else:
        await interaction.response.send_message("❌ Ticket system not loaded.", ephemeral=True)

# ============================================================
#                    TICKET SYSTEM (UPDATED)
# ============================================================
TICKET_CATEGORY_NAME = "tickets"
# Updated support roles to include the specific role IDs
SUPPORT_ROLE_IDS = FULL_ADMIN_ROLE_IDS + [1420001481322401893]  # Full admins + ticket admin

TICKET_WELCOME_MESSAGES = {
    "support": "👋 **Welcome to Support Ticket!**\n\nPlease describe your issue in detail and our support team will assist you shortly.",
    "invite": "🎁 **Welcome to Invite Rewards!**\n\nPlease provide your invite details and we'll process your rewards.",
    "giveaway": "🎉 **Welcome to Giveaway Claim!**\n\nPlease provide the giveaway details and proof of winning."
}

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Support Ticket", style=discord.ButtonStyle.blurple, custom_id="support_ticket")
    async def support_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        ticket_system = bot.get_cog('TicketSystem')
        if ticket_system:
            await ticket_system.create_ticket(interaction, "support", "🛠️ Support Ticket")

    @discord.ui.button(label="Invite Rewards", style=discord.ButtonStyle.green, custom_id="invite_ticket")
    async def invite_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        ticket_system = bot.get_cog('TicketSystem')
        if ticket_system:
            await ticket_system.create_ticket(interaction, "invite", "🎁 Invite Rewards")

    @discord.ui.button(label="Giveaway Claim", style=discord.ButtonStyle.gray, custom_id="giveaway_ticket")
    async def giveaway_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        ticket_system = bot.get_cog('TicketSystem')
        if ticket_system:
            await ticket_system.create_ticket(interaction, "giveaway", "🎉 Giveaway Claim")

class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check if user has ticket admin access
        user_roles = [role.id for role in interaction.user.roles]
        has_access = any(role_id in user_roles for role_id in SUPPORT_ROLE_IDS) or interaction.user.guild_permissions.administrator

        if not has_access:
            await interaction.response.send_message("❌ You don't have permission to close tickets.", ephemeral=True)
            return

        await interaction.response.defer()
        ticket_system = bot.get_cog('TicketSystem')
        if ticket_system:
            await ticket_system.close_ticket(interaction)

class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ticket_data = {}

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(TicketView())
        self.bot.add_view(CloseTicketView())

    async def create_ticket_panel(self, channel_id):
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return

        existing_message = None
        async for message in channel.history(limit=100):
            if message.author == self.bot.user and message.embeds:
                embed = message.embeds[0]
                if "Ticket System" in embed.title:
                    existing_message = message
                    break

        embed = discord.Embed(
            title="🎫 Ticket System",
            description="**Support Ticket** - Get help from staff.\n"
                        "**Invite Rewards** - Claim rewards for invites.\n"
                        "**Giveaway Claim** - Claim giveaway prizes.\n\n"
                        "Click one of the buttons below to create a ticket.",
            color=0x3498db)
        embed.set_footer(text="PVB Bot - Ticket System")

        view = TicketView()

        if existing_message:
            # Update existing message silently (no new message)
            await existing_message.edit(embed=embed, view=view)
            return existing_message
        else:
            # Send new message only if no existing panel found
            message = await channel.send(embed=embed, view=view)
            return message

    async def create_ticket(self, interaction: discord.Interaction, ticket_type: str, ticket_name: str):
        user = interaction.user
        guild = interaction.guild

        for channel_id, data in self.ticket_data.items():
            if data['user_id'] == user.id and not data['closed']:
                channel = guild.get_channel(channel_id)
                if channel:
                    await interaction.followup.send(f"You already have an open ticket: {channel.mention}", ephemeral=True)
                    return

        category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)
        if not category:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True)
            }
            category = await guild.create_category(TICKET_CATEGORY_NAME, overwrites=overwrites)

        channel_name = f"{ticket_type}-{user.name}-{user.discriminator}".lower().replace(" ", "-")
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True)
        }

        # Add support role IDs instead of role names
        for role_id in SUPPORT_ROLE_IDS:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_messages=True)

        ticket_channel = await category.create_text_channel(
            name=channel_name,
            overwrites=overwrites,
            topic=f"{ticket_name} for {user.display_name} | Created at {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )

        self.ticket_data[ticket_channel.id] = {
            'user_id': user.id,
            'ticket_type': ticket_type,
            'created_at': datetime.now(),
            'closed': False
        }

        welcome_message = TICKET_WELCOME_MESSAGES.get(ticket_type, "Welcome to your ticket!")
        embed = discord.Embed(
            title=ticket_name,
            description=f"Hello {user.mention}!\n\n{welcome_message}\n\n"
                        f"**Ticket Type:** {ticket_name}\n"
                        f"**Created:** <t:{int(datetime.now().timestamp())}:F>\n"
                        f"**User:** {user.display_name}",
            color=0x3498db)

        if ticket_type == "support":
            embed.add_field(
                name="📝 Support Instructions",
                value="Please describe your issue in detail. Include:\n• What happened\n• When it occurred\n• Any error messages",
                inline=False)
        elif ticket_type == "invite":
            embed.add_field(
                name="🎁 Invite Rewards",
                value="Please provide:\n• Your invite code\n• Number of invites\n• Screenshots if available",
                inline=False)
        elif ticket_type == "giveaway":
            embed.add_field(
                name="🎉 Giveaway Claim",
                value="Please provide:\n• Giveaway ID or name\n• Your username\n• Proof of winning",
                inline=False)

        close_view = CloseTicketView()
        await ticket_channel.send(embed=embed, view=close_view)
        await interaction.followup.send(f"✅ Ticket created: {ticket_channel.mention}", ephemeral=True)

        log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            log_embed = discord.Embed(
                title="🎫 Ticket Created",
                description=f"**Type:** {ticket_name}\n"
                            f"**User:** {user.mention} ({user.id})\n"
                            f"**Channel:** {ticket_channel.mention}\n"
                            f"**Time:** <t:{int(datetime.now().timestamp())}:F>",
                color=0x00ff00)
            await log_channel.send(embed=log_embed)

    async def close_ticket(self, interaction: discord.Interaction, channel_id: int = None):
        channel = interaction.channel if not channel_id else self.bot.get_channel(channel_id)
        if not channel:
            await interaction.followup.send("❌ Channel not found.", ephemeral=True)
            return

        ticket_data = self.ticket_data.get(channel.id)
        if not ticket_data:
            await interaction.followup.send("❌ This channel is not a valid ticket.", ephemeral=True)
            return

        if ticket_data['closed']:
            await interaction.followup.send("❌ This ticket is already closed.", ephemeral=True)
            return

        ticket_data['closed'] = True
        user = interaction.guild.get_member(ticket_data['user_id'])

        countdown_msg = await channel.send("🔒 **Closing this ticket in 10 seconds...**")
        for i in range(9, 0, -1):
            await asyncio.sleep(1)
            await countdown_msg.edit(content=f"🔒 **Closing this ticket in {i} seconds...**")

        await countdown_msg.edit(content="🔒 **Closing now...**")

        log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            log_embed = discord.Embed(
                title="🎫 Ticket Closed",
                description=f"**Type:** {ticket_data['ticket_type'].title()} Ticket\n"
                            f"**User:** {user.mention if user else 'Unknown'} ({ticket_data['user_id']})\n"
                            f"**Channel:** #{channel.name}\n"
                            f"**Closed by:** {interaction.user.mention}\n"
                            f"**Duration:** {datetime.now() - ticket_data['created_at']}",
                color=0xff0000)
            await log_channel.send(embed=log_embed)

        try:
            if user:
                try:
                    user_embed = discord.Embed(
                        title="🎫 Ticket Closed",
                        description=f"Your {ticket_data['ticket_type']} ticket has been closed.\n"
                                    f"**Closed by:** {interaction.user.display_name}\n"
                                    f"**Channel:** #{channel.name}",
                        color=0xff0000)
                    await user.send(embed=user_embed)
                except:
                    pass
        except:
            pass

        await channel.delete()
        if channel.id in self.ticket_data:
            del self.ticket_data[channel.id]

# ORIGINAL TICKET COMMANDS (with updated permissions)
@bot.command(name='ticketsetup')
@has_ticket_admin_access()
async def ticketsetup(ctx, channel: discord.TextChannel = None):
    """Setup the ticket system in a channel"""
    target_channel = channel or ctx.channel
    ticket_system = bot.get_cog('TicketSystem')
    if not ticket_system:
        ticket_system = TicketSystem(bot)
        await bot.add_cog(ticket_system)

    await ticket_system.create_ticket_panel(target_channel.id)
    await ctx.send(f"✅ Ticket panel created/updated in {target_channel.mention}")

@bot.command(name='ticketclose')
@has_ticket_admin_access()
async def ticketclose(ctx):
    """Close the current ticket (for staff)"""
    ticket_system = bot.get_cog('TicketSystem')
    if ticket_system:
        await ticket_system.close_ticket(ctx, ctx.channel.id)
    else:
        await ctx.send("❌ Ticket system not loaded.")

@bot.command(name='ticketmessage')
@has_ticket_admin_access()
async def ticketmessage(ctx, ticket_type: str, *, message: str):
    """Customize ticket welcome messages"""
    if ticket_type not in ["support", "invite", "giveaway"]:
        await ctx.send("❌ Invalid ticket type. Use: support, invite, or giveaway")
        return

    TICKET_WELCOME_MESSAGES[ticket_type] = message
    await ctx.send(f"✅ {ticket_type.title()} ticket message updated!")

# ============================================================
#                    OTHER COMMANDS (KEEP EXISTING)
# ============================================================

# Active timers and AFK dictionaries
active_timers = {}
afk_users = {}

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # AFK check
    if message.author.id in afk_users:
        data = afk_users.pop(message.author.id)
        since = datetime.now(timezone.utc) - data["since"]
        seconds = int(since.total_seconds())
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        pinged_users = data.get("pinged_by", [])
        pinged_text = ""
        if pinged_users:
            mentions = [f"<@{uid}>" for uid in pinged_users]
            pinged_text = f"\n⚡ You were pinged by: {', '.join(mentions)} in <#{data['channel']}>"
        await message.channel.send(
            f"✅ Welcome back {message.author.mention}! You were AFK for {hours}h {minutes}m {seconds}s.{pinged_text}")

    # Mention check for AFK users
    for user in message.mentions:
        if user.id in afk_users:
            data = afk_users[user.id]
            data["pinged_by"].append(message.author.id)
            await message.channel.send(f"💤 {user.display_name} is AFK due to the following reason: {data['reason']}")

    # PS VRU command
    if message.content.lower().strip() == ",,ps vru":
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ You must be an **Administrator** to use this command.")
            return

        try:
            await message.delete()
        except Exception:
            pass

        await message.channel.send(
            "🌐 **Join vru's PVB Private Server!**\n"
            "👉 Click here: "
            "[Server Link](<https://www.roblox.com/share?code=a3f72c3d9218634dac40fdd73df44c6e&type=Server>)\n"
            "🔗 Or use the raw link:\n"
            "https://www.roblox.com/share?code=a3f72c3d9218634dac40fdd73df44c6e&type=Server"
        )

        await send_log(f"🌐 **PS VRU Command Used by** {message.author.mention}")
        return

    await bot.process_commands(message)

# Add manual sync command for debugging
@bot.command(name='sync')
@has_full_admin_access()
async def sync_commands(ctx):
    """Manually sync slash commands"""
    try:
        synced = await bot.tree.sync()
        await ctx.send(f"✅ Successfully synced {len(synced)} slash command(s)")
        for command in synced:
            await ctx.send(f"  - /{command.name}")
    except Exception as e:
        await ctx.send(f"❌ Failed to sync commands: {e}")

# Add the cog when bot starts
async def setup_hook():
    await bot.add_cog(TicketSystem(bot))

bot.setup_hook = setup_hook

# Run the bot
bot.run(TOKEN)
