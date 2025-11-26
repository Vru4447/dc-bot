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

# ⚠️ REMOVE THIS TOKEN AND USE ENVIRONMENT VARIABLE INSTEAD!
TOKEN = os.environ['MTQzOTk2Nzc3Nzk4NDM0ODI5MA.GQIJ6Q.FPXu9iWNLW09S4CWLunIVn8207Fd5_DrsLs0B4']
# Flask web server for uptime
app = Flask('')

@app.route('/')
def home():
    return "🤖 Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    server = Thread(target=run)
    server.start()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.reactions = True

bot = commands.Bot(command_prefix=",,", intents=intents)
bot.remove_command("help")

# ---------------------------------------------------------
LOG_CHANNEL_ID = 1418106413640581191


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
# Ready event
# ---------------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        try:
            await log_channel.send("✅ **Bot is now Ready!** 😎")
        except Exception as e:
            print(f"Failed to send ready message to log channel: {e}")


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
ALLOWED_ROLES = ["Owner", "moderator", "giveaway host", "staff", "manager"]


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


@bot.command(name='gwcreate')
async def gwcreate(ctx, *, args: str = None):
    """Create a giveaway"""
    has_permission = False
    for role in ctx.author.roles:
        if role.name.lower() in [r.lower() for r in ALLOWED_ROLES]:
            has_permission = True
            break

    if not has_permission and not ctx.author.guild_permissions.administrator:
        role_names = ", ".join(ALLOWED_ROLES)
        await ctx.send(f"❌ You don't have permission to use this command!\n**Required roles:** {role_names}")
        return

    if args is None:
        await ctx.send(
            '❌ Usage: `,,gwcreate "Prize Name" duration winners host(@user)`\nExample: `,,gwcreate "100 ROBUX" 10m 1 host(@user)`')
        return

    try:
        parts = args.split()
        if len(parts) < 2:
            await ctx.send(
                '❌ Usage: `,,gwcreate "Prize Name" duration winners host(@user)`\nExample: `,,gwcreate "100 ROBUX" 10m 1 host(@user)`')
            return

        prize = ""
        duration = ""
        winners = 1
        host = ctx.author

        if args.startswith('"'):
            end_quote_index = args.find('"', 1)
            if end_quote_index == -1:
                await ctx.send("❌ Invalid format! Make sure to close the quotes around the prize name.")
                return
            prize = args[1:end_quote_index]
            remaining_args = args[end_quote_index + 1:].strip()
        else:
            first_space = args.find(' ')
            if first_space == -1:
                await ctx.send("❌ Please provide a duration!")
                return
            prize = args[:first_space]
            remaining_args = args[first_space + 1:].strip()

        host_match = re.search(r'host\s*\(<@!?(\d+)>\)', remaining_args, re.IGNORECASE)
        if host_match:
            host_id = int(host_match.group(1))
            try:
                host = await bot.fetch_user(host_id)
                remaining_args = re.sub(r'host\s*\(<@!?\d+>\)', '', remaining_args, flags=re.IGNORECASE).strip()
            except:
                await ctx.send("❌ Invalid user mentioned for host!")
                return

        remaining_parts = remaining_args.split()
        if remaining_parts:
            duration = remaining_parts[0]
            if len(remaining_parts) > 1:
                try:
                    winners = int(remaining_parts[1])
                except ValueError:
                    if 'host' in remaining_parts[1].lower():
                        await ctx.send("❌ Invalid host format! Use `host(@user)`")
                        return
                    await ctx.send("❌ Winners must be a number!")
                    return

        if not prize:
            await ctx.send("❌ Please provide a prize name!")
            return
        if not duration:
            await ctx.send("❌ Please provide a duration!")
            return
        if winners < 1:
            await ctx.send("❌ Winners must be at least 1!")
            return

        duration_seconds = parse_duration(duration)
        if duration_seconds <= 0:
            await ctx.send("❌ Please provide a valid duration (e.g., 1h, 30m, 1d, 10s)")
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

        image_url = None
        if ctx.message.attachments:
            for attachment in ctx.message.attachments:
                if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                    image_url = attachment.url
                    embed.set_image(url=image_url)
                    break

        giveaway_msg = await ctx.send(embed=embed)
        await giveaway_msg.add_reaction("🎉")

        active_giveaways[giveaway_id] = {
            'message_id': giveaway_msg.id,
            'channel_id': ctx.channel.id,
            'prize': prize,
            'winners': winners,
            'end_time': end_time,
            'host_id': host.id,
            'participants': [],
            'ended': False,
            'image_url': image_url
        }

        success_msg = f"✅ Giveaway created successfully! ID: `{giveaway_id}`\n**Host:** {host.mention}"
        if image_url:
            success_msg += "\n**Image attached:** ✅"

        log_channel = bot.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            log_embed = discord.Embed(
                title="🎉 Giveaway Created",
                description=f"**Prize:** {prize}\n"
                            f"**Winners:** {winners}\n"
                            f"**Duration:** {duration}\n"
                            f"**Ends:** <t:{int(end_time.timestamp())}:F>\n"
                            f"**Host:** {host.mention}\n"
                            f"**Created by:** {ctx.author.mention}\n"
                            f"**Channel:** {ctx.channel.mention}\n"
                            f"**Giveaway ID:** {giveaway_id}",
                color=0x00ff00,
                timestamp=datetime.now(timezone.utc))
            if image_url:
                log_embed.set_image(url=image_url)
            await log_channel.send(embed=log_embed)

        await ctx.send(success_msg)
        await asyncio.sleep(duration_seconds)
        await end_giveaway(giveaway_id)

    except Exception as e:
        await ctx.send(f"❌ Error creating giveaway: {str(e)}")


@bot.command(name='gwend')
async def gwend(ctx, giveaway_id: int = None):
    """End a giveaway early"""
    has_permission = False
    for role in ctx.author.roles:
        if role.name.lower() in [r.lower() for r in ALLOWED_ROLES]:
            has_permission = True
            break

    if not has_permission and not ctx.author.guild_permissions.administrator:
        role_names = ", ".join(ALLOWED_ROLES)
        await ctx.send(f"❌ You don't have permission to use this command!\n**Required roles:** {role_names}")
        return

    if giveaway_id is None:
        await ctx.send("❌ Please provide a giveaway ID. Use `,,gwlist` to see active giveaways.")
        return

    if giveaway_id not in active_giveaways:
        await ctx.send("❌ Giveaway not found or already ended.")
        return

    giveaway = active_giveaways[giveaway_id]
    if giveaway['host_id'] != ctx.author.id and not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ You can only end giveaways that you hosted!")
        return

    await end_giveaway(giveaway_id)
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        log_embed = discord.Embed(
            title="🎉 Giveaway Ended Manually",
            description=f"**Prize:** {giveaway['prize']}\n"
                        f"**Host:** <@{giveaway['host_id']}>\n"
                        f"**Giveaway ID:** {giveaway_id}\n"
                        f"**Ended by:** {ctx.author.mention}\n"
                        f"⏰ **Ended early** by command",
            color=0xffa500,
            timestamp=datetime.now(timezone.utc))
        if giveaway.get('image_url'):
            log_embed.set_image(url=giveaway['image_url'])
        await log_channel.send(embed=log_embed)

    await ctx.send(f"✅ Giveaway `{giveaway_id}` ended successfully!")


@bot.command(name='gwlist')
async def gwlist(ctx):
    """List all active giveaways"""
    if not active_giveaways:
        await ctx.send("📝 No active giveaways!")
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
    await ctx.send(embed=embed)


@bot.command(name='gwreroll')
async def gwreroll(ctx, giveaway_id: int, winners: int = 1):
    """Reroll winners for an ended giveaway"""
    has_permission = False
    for role in ctx.author.roles:
        if role.name.lower() in [r.lower() for r in ALLOWED_ROLES]:
            has_permission = True
            break

    if not has_permission and not ctx.author.guild_permissions.administrator:
        role_names = ", ".join(ALLOWED_ROLES)
        await ctx.send(f"❌ You don't have permission to use this command!\n**Required roles:** {role_names}")
        return

    if giveaway_id not in active_giveaways:
        await ctx.send("❌ Giveaway not found!")
        return

    giveaway = active_giveaways[giveaway_id]
    if not giveaway['ended']:
        await ctx.send("❌ Giveaway hasn't ended yet!")
        return

    if not giveaway['participants']:
        await ctx.send("❌ No participants to reroll from!")
        return

    winners_count = min(len(giveaway['participants']), winners)
    new_winners = random.sample(giveaway['participants'], winners_count)
    winners_mentions = ', '.join([f"<@{winner_id}>" for winner_id in new_winners])

    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        log_embed = discord.Embed(
            title="🎉 Giveaway Winners Rerolled",
            description=f"**Prize:** {giveaway['prize']}\n"
                        f"**Host:** <@{giveaway['host_id']}>\n"
                        f"**Giveaway ID:** {giveaway_id}\n"
                        f"**Rerolled by:** {ctx.author.mention}\n"
                        f"**New Winners:** {winners_mentions}",
            color=0xffff00,
            timestamp=datetime.now(timezone.utc))
        if giveaway.get('image_url'):
            log_embed.set_image(url=giveaway['image_url'])
        await log_channel.send(embed=log_embed)

    await ctx.send(
        f"🎉 **Rerolled Winners for** `{giveaway['prize']}`\n\nNew winners: {winners_mentions}\n**Host:** <@{giveaway['host_id']}>")


@bot.command(name='gwsethost')
async def gwsethost(ctx, giveaway_id: int, new_host: discord.Member):
    """Change the host of a giveaway"""
    has_permission = False
    for role in ctx.author.roles:
        if role.name.lower() in [r.lower() for r in ALLOWED_ROLES]:
            has_permission = True
            break

    if not has_permission and not ctx.author.guild_permissions.administrator:
        role_names = ", ".join(ALLOWED_ROLES)
        await ctx.send(f"❌ You don't have permission to use this command!\n**Required roles:** {role_names}")
        return

    if giveaway_id not in active_giveaways:
        await ctx.send("❌ Giveaway not found!")
        return

    giveaway = active_giveaways[giveaway_id]
    if giveaway['host_id'] != ctx.author.id and not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ You can only change host for giveaways that you currently host!")
        return

    old_host_id = giveaway['host_id']
    giveaway['host_id'] = new_host.id

    try:
        channel = bot.get_channel(giveaway['channel_id'])
        if channel:
            message = await channel.fetch_message(giveaway['message_id'])
            embed = message.embeds[0]
            embed.description = re.sub(r'\*\*Hosted by:\*\* <@!?\d+>', f'**Hosted by:** {new_host.mention}',
                                       embed.description)
            await message.edit(embed=embed)
    except:
        pass

    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        log_embed = discord.Embed(
            title="🎉 Giveaway Host Changed",
            description=f"**Prize:** {giveaway['prize']}\n"
                        f"**Giveaway ID:** {giveaway_id}\n"
                        f"**Changed by:** {ctx.author.mention}\n"
                        f"**Old Host:** <@{old_host_id}>\n"
                        f"**New Host:** {new_host.mention}",
            color=0x00ffff,
            timestamp=datetime.now(timezone.utc))
        if giveaway.get('image_url'):
            log_embed.set_image(url=giveaway['image_url'])
        await log_channel.send(embed=log_embed)

    await ctx.send(f"✅ Host changed from <@{old_host_id}> to {new_host.mention} for giveaway `{giveaway_id}`")


@bot.event
async def on_raw_reaction_add(payload):
    """Handle reaction adds for giveaways"""
    if payload.user_id == bot.user.id:
        return

    for giveaway_id, giveaway in active_giveaways.items():
        if (payload.message_id == giveaway['message_id'] and
                str(payload.emoji) == "🎉" and
                not giveaway['ended']):
            if payload.user_id not in giveaway['participants']:
                giveaway['participants'].append(payload.user_id)


# ============================================================
#                    TICKET SYSTEM
# ============================================================
TICKET_CATEGORY_NAME = "tickets"
SUPPORT_ROLE_NAMES = ["Owner", "moderator", "support"]
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
            await existing_message.edit(embed=embed, view=view)
            return existing_message
        else:
            message = await channel.send(embed=embed, view=view)
            return message

    async def create_ticket(self, interaction: discord.Interaction, ticket_type: str, ticket_name: str):
        user = interaction.user
        guild = interaction.guild

        for channel_id, data in self.ticket_data.items():
            if data['user_id'] == user.id and not data['closed']:
                channel = guild.get_channel(channel_id)
                if channel:
                    await interaction.followup.send(f"You already have an open ticket: {channel.mention}",
                                                    ephemeral=True)
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

        for role_name in SUPPORT_ROLE_NAMES:
            role = discord.utils.get(guild.roles, name=role_name)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True,
                                                               manage_messages=True)

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


@bot.command(name='ticketsetup')
async def ticketsetup(ctx, channel: discord.TextChannel = None):
    """Setup the ticket system in a channel"""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ You need administrator permissions to setup tickets.")
        return

    target_channel = channel or ctx.channel
    ticket_system = bot.get_cog('TicketSystem')
    if not ticket_system:
        ticket_system = TicketSystem(bot)
        await bot.add_cog(ticket_system)

    await ticket_system.create_ticket_panel(target_channel.id)
    await ctx.send(f"✅ Ticket panel created/updated in {target_channel.mention}")


@bot.command(name='ticketclose')
async def ticketclose(ctx):
    """Close the current ticket (for staff)"""
    ticket_system = bot.get_cog('TicketSystem')
    if ticket_system:
        await ticket_system.close_ticket(ctx, ctx.channel.id)
    else:
        await ctx.send("❌ Ticket system not loaded.")


@bot.command(name='ticketmessage')
async def ticketmessage(ctx, ticket_type: str, *, message: str):
    """Customize ticket welcome messages"""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ You need administrator permissions to customize messages.")
        return

    if ticket_type not in ["support", "invite", "giveaway"]:
        await ctx.send("❌ Invalid ticket type. Use: support, invite, or giveaway")
        return

    TICKET_WELCOME_MESSAGES[ticket_type] = message
    await ctx.send(f"✅ {ticket_type.title()} ticket message updated!")


# ============================================================
#                    OTHER COMMANDS
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


@bot.command(name="help")
async def help(ctx):
    await ctx.message.delete()
    embed = discord.Embed(title="✨ MANAGEMENT PANEL", description="A quick reference for admin commands.",
                          color=0x2F3136)
    divider = "───────────────────────────────"
    embed.add_field(name=f"{divider}\n🔐 ADMIN COMMANDS\n{divider}", value="\u200b", inline=False)
    embed.add_field(name="💰 ,,payout <text>",
                    value="Sends a payout message. Attach image in same message or reply to the bot's prompt with an image.",
                    inline=False)
    embed.add_field(name="🌐 ,,ps vru", value="Send vru's private server link.", inline=False)
    embed.add_field(name="🎭 ,,giverole @user @role1 @role2 ...",
                    value="Give mentioned roles to a user. Roles must be mentioned.", inline=False)
    embed.add_field(name="🗑️ ,,removerole @user @role1 @role2 ...", value="Remove mentioned roles from a user.",
                    inline=False)
    embed.add_field(name="✏️ ,,changenick @user NewNickname", value="Change someone's nickname (including bots).",
                    inline=False)
    embed.add_field(name="🔨 ,,ban @user [reason]", value="Ban a user from the server.", inline=False)
    embed.add_field(name="⛔ ,,kick @user [reason]", value="Kick a user from the server.", inline=False)
    embed.add_field(name="⏳ ,,timeout @user <duration> [reason]",
                    value="Apply Discord moderation timeout (duration format: 30s, 10m, 2h, 1d).", inline=False)
    embed.add_field(name="⏱️ ,,timer <duration> [message]",
                    value="Start a normal timer (not Discord timeout). When it ends, bot will post the message and ping the requester.",
                    inline=False)
    embed.add_field(name="⏹️ ,,endtimer", value="Stops your active timer early.", inline=False)
    embed.add_field(name="💤 ,,afk <reason>", value="Set yourself as AFK with an optional reason.", inline=False)
    embed.add_field(name="🎁 ,,gwcreate <prize> <time> <winners> host(<to change the host>) ", value="Make a giveaway.",
                    inline=False)
    embed.add_field(name="🎁 ,,gwreroll <giveawayid> ", value="Reroll a Giveaway / To Change the Winner", inline=False)
    embed.set_footer(text="All commands listed above require Administrator.")
    await ctx.send(embed=embed)


@bot.command(name="timer")
async def timer(ctx, duration: str, *, message: str = None):
    await ctx.message.delete()
    seconds = parse_duration_to_seconds(duration)
    if seconds is None:
        return await ctx.send("❌ Invalid duration format. Use: 30s, 10m, 2h, 1d")

    await ctx.send(f"⏱️ Timer started for **{duration}** — I'll remind you when it's done, {ctx.author.mention}.")

    async def run_timer():
        try:
            await asyncio.sleep(seconds)
            if message:
                await ctx.send(f"⏰ **Timer finished** ({duration}) — {ctx.author.mention}\n{message}")
            else:
                await ctx.send(f"⏰ **Timer finished** ({duration}) — {ctx.author.mention}")
        except asyncio.CancelledError:
            pass
        finally:
            active_timers.pop(ctx.author.id, None)

    task = bot.loop.create_task(run_timer())
    active_timers[ctx.author.id] = task


@bot.command(name="endtimer")
async def endtimer(ctx):
    await ctx.message.delete()
    user_id = ctx.author.id
    task = active_timers.get(user_id)
    if task and not task.done():
        task.cancel()
        await ctx.send(f"⏹️ Timer stopped, {ctx.author.mention}")
        del active_timers[user_id]
    else:
        await ctx.send("❌ You don't have an active timer.")


@bot.command(name="giverole")
@commands.has_permissions(administrator=True)
async def giverole(ctx):
    await ctx.message.delete()
    user_mentions = ctx.message.mentions
    role_mentions = ctx.message.role_mentions

    if len(user_mentions) < 1 or len(role_mentions) < 1:
        return await ctx.send(
            "❌ **Incorrect usage!**\nCorrect format:\n`,,giverole @user @role1 @role2 ...`\nMake sure you mention roles (use @role).")

    target_user = user_mentions[0]
    roles_added = []

    for role in role_mentions:
        try:
            await target_user.add_roles(role)
            roles_added.append(role.name)
        except Exception:
            pass

    if not roles_added:
        return await ctx.send("⚠️ No roles could be added (check bot permissions and role hierarchy).")

    await ctx.send(f"✅ **Roles Added!**\n👤 User: {target_user.mention}\n🎭 Roles: {', '.join(roles_added)}")
    await send_log(
        f"🛠️ **Roles Added**\nAdmin: {ctx.author.mention}\nUser: {target_user.mention}\nRoles: {', '.join(roles_added)}")


@bot.command(name="removerole")
@commands.has_permissions(administrator=True)
async def removerole(ctx):
    await ctx.message.delete()
    user_mentions = ctx.message.mentions
    role_mentions = ctx.message.role_mentions

    if len(user_mentions) < 1 or len(role_mentions) < 1:
        return await ctx.send("❌ **Incorrect usage!**\nCorrect format:\n`,,removerole @user @role1 @role2 ...`")

    target_user = user_mentions[0]
    roles_removed = []

    for role in role_mentions:
        try:
            await target_user.remove_roles(role)
            roles_removed.append(role.name)
        except Exception:
            pass

    if not roles_removed:
        return await ctx.send("⚠️ None of the roles could be removed (check permissions).")

    await ctx.send(f"🗑️ **Roles Removed!**\n👤 User: {target_user.mention}\n🎭 Removed: {', '.join(roles_removed)}")
    await send_log(
        f"🗑️ **Roles Removed**\nAdmin: {ctx.author.mention}\nUser: {target_user.mention}\nRemoved: {', '.join(roles_removed)}")


@bot.command(name="changenick")
@commands.has_permissions(administrator=True)
async def changenick(ctx, user: discord.Member, *, newnick=None):
    await ctx.message.delete()
    if newnick is None:
        return await ctx.send("❌ Example:\n`,,changenick @user NewNickname`")

    try:
        await user.edit(nick=newnick)
        await ctx.send(f"✏️ Nickname changed for {user.mention} → **{newnick}**")
        await send_log(
            f"✏️ **Nickname Changed**\nAdmin: {ctx.author.mention}\nUser: {user.mention}\nNew Nickname: **{newnick}**")
    except Exception:
        await ctx.send("❌ I don't have permission to change that nickname.")


@bot.command(name="ban")
@commands.has_permissions(administrator=True)
async def ban(ctx, user: discord.Member, *, reason: str = None):
    await ctx.message.delete()
    try:
        await ctx.guild.ban(user, reason=reason)
        await ctx.send(f"🔨 Banned {user.mention}.")
        await send_log(f"🔨 **Banned** {user.mention} by {ctx.author.mention} — Reason: {reason}")
    except Exception as e:
        await ctx.send("❌ Could not ban that member (missing permissions / role hierarchy).")
        print(f"Ban error: {e}")


@bot.command(name="kick")
@commands.has_permissions(administrator=True)
async def kick(ctx, user: discord.Member, *, reason: str = None):
    await ctx.message.delete()
    try:
        await ctx.guild.kick(user, reason=reason)
        await ctx.send(f"⛔ Kicked {user.mention}.")
        await send_log(f"⛔ **Kicked** {user.mention} by {ctx.author.mention} — Reason: {reason}")
    except Exception as e:
        await ctx.send("❌ Could not kick that member (missing permissions / role hierarchy).")
        print(f"Kick error: {e}")


@bot.command(name="timeout")
@commands.has_permissions(administrator=True)
async def timeout(ctx, user: discord.Member, duration: str, *, reason: str = None):
    await ctx.message.delete()
    seconds = parse_duration_to_seconds(duration)
    if seconds is None:
        return await ctx.send("❌ Invalid duration format. Use examples: 30s, 10m, 2h, 1d")

    until = datetime.now(timezone.utc) + timedelta(seconds=seconds)

    try:
        await user.edit(timed_out_until=until)
        await ctx.send(f"⏳ {user.mention} timed out for {duration}.")
        await send_log(f"⏳ **Timeout** {user.mention} by {ctx.author.mention} for {duration} — Reason: {reason}")
    except Exception as e:
        await ctx.send("❌ Could not apply timeout (bot missing permission or role hierarchy).")
        print(f"Timeout error: {e}")


@bot.command(name="afk")
async def afk(ctx, *, reason: str = "AFK"):
    await ctx.message.delete()
    afk_users[ctx.author.id] = {
        "since": datetime.now(timezone.utc),
        "reason": reason,
        "channel": ctx.channel.id,
        "pinged_by": []
    }
    await ctx.send(f"💤 {ctx.author.mention} is now AFK: {reason}")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("❌ Invalid command")


# Add the cog when bot starts
async def setup_hook():
    await bot.add_cog(TicketSystem(bot))


bot.setup_hook = setup_hook

# Start the web server
keep_alive()

# ⚠️ IMPORTANT: Use environment variable for token!
bot.run(TOKEN)