import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from datetime import datetime, timedelta
import io
import flask
app = flask.Flask(__name__)



intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

AUTHORIZED_FILE = "authorized_roles.json"
TRANSCRIPT_FILE = "transcript_channels.json"
CLAIMED_FILE = "claimed_tickets.json"



def load_json(file):
    if not os.path.exists(file):
        with open(file, 'w') as f:
            json.dump({}, f)
    with open(file, 'r') as f:
        return json.load(f)

def save_json(file, data):
    with open(file, 'w') as f:
        json.dump(data, f, indent=4)

authorized_roles = load_json(AUTHORIZED_FILE)
transcript_channels = load_json(TRANSCRIPT_FILE)
claimed_tickets = load_json(CLAIMED_FILE)

@bot.command()
@commands.has_permissions(administrator=True)
async def setroles(ctx, *roles: discord.Role):
    guild_id = str(ctx.guild.id)
    authorized_roles[guild_id] = [role.id for role in roles]
    save_json(AUTHORIZED_FILE, authorized_roles)
    await ctx.send("✅ Ruoli autorizzati aggiornati.")

@bot.command()
@commands.has_permissions(administrator=True)
async def settranscript(ctx, channel: discord.TextChannel):
    guild_id = str(ctx.guild.id)
    transcript_channels[guild_id] = channel.id
    save_json(TRANSCRIPT_FILE, transcript_channels)
    await ctx.send(f"✅ Canale transcript impostato su {channel.mention}.")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def ticketbutton(ctx, titolo: str, descrizione: str, colore: str, categoria_id: int, *, bottoni: str):
        button_labels = [label.strip() for label in bottoni.split("|") if label.strip()]
        categoria = ctx.guild.get_channel(categoria_id)

        if not isinstance(categoria, discord.CategoryChannel):
            return await ctx.send("❌ L'ID fornito non corrisponde a una categoria valida.")

        class TicketButton(discord.ui.Button):
            def __init__(self, label):
                super().__init__(label=label, style=discord.ButtonStyle.secondary, custom_id=f"open_ticket_{label.lower().replace(' ', '_')}")
                self.label_text = label

            async def callback(self, interaction: discord.Interaction):
                await interaction.response.defer()
                guild_id = str(interaction.guild.id)
                member = interaction.user

                role_ids = authorized_roles.get(guild_id, [])
                overwrites = {
                    interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    member: discord.PermissionOverwrite(view_channel=True, send_messages=True)
                }
                for role_id in role_ids:
                    role = interaction.guild.get_role(role_id)
                    if role:
                        overwrites[role] = discord.PermissionOverwrite(view_channel=True)

                channel_name = f"ticket-{member.name.lower()}-{self.label_text.lower().replace(' ', '-')}"
                ticket_channel = await interaction.guild.create_text_channel(
                    name=channel_name,
                    overwrites=overwrites,
                    category=categoria,
                    topic=f"{self.label_text} | Ticket aperto da {member.display_name}"
                )

                await ticket_channel.send(
                    f"{member.mention} ha aperto un ticket ({self.label_text}). Esegui !delete per chiudere il ticket (cancellarlo)."
                )

                await interaction.followup.send(
                    content=f"✉️ Il tuo ticket è stato creato: {ticket_channel.mention}",
                    ephemeral=True
                )

        class TicketButtonView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=None)
                for label in button_labels:
                    self.add_item(TicketButton(label))

        embed = discord.Embed(title=titolo, description=descrizione, color=int(colore.strip('#'), 16))
        await ctx.send(embed=embed, view=TicketButtonView())




@bot.command()
@commands.has_permissions(manage_channels=True)
async def transcript(ctx):
    if not isinstance(ctx.channel, discord.TextChannel):
        return await ctx.send("❌ Questo comando può essere usato solo nei canali testuali.")

    if not ctx.channel.name.startswith("ticket-"):
        return await ctx.send("❌ Questo comando può essere usato solo nei canali ticket.")

    guild_id = str(ctx.guild.id)
    transcript_channel_id = transcript_channels.get(guild_id)
    if not transcript_channel_id:
        return await ctx.send("❌ Nessun canale transcript impostato per questo server.")

    transcript_channel = ctx.guild.get_channel(transcript_channel_id)
    if not transcript_channel:
        return await ctx.send("❌ Canale transcript non trovato.")

    messages = [message async for message in ctx.channel.history(limit=100)]
    content = "\n".join([f"[{m.created_at.strftime('%Y-%m-%d %H:%M')}] {m.author.display_name}: {m.content}" for m in reversed(messages)])

    if not content:
        return await ctx.send("❌ Nessun messaggio da trascrivere.")

    transcript_file = discord.File(fp=io.BytesIO(content.encode("utf-8")), filename=f"transcript-{ctx.channel.name}.txt")

    await transcript_channel.send(f"📄 Transcript di {ctx.channel.mention}", file=transcript_file)
    await ctx.send("✅ Transcript inviato.")

@bot.command()
async def delete(ctx):
    if not isinstance(ctx.channel, discord.TextChannel):
        return await ctx.send("❌ Questo comando può essere usato solo nei canali testuali.")

    if not ctx.channel.name.startswith("ticket-"):
        return await ctx.send("❌ Questo comando può essere usato solo nei canali ticket.")

    await ctx.send("🗑️ Questo ticket verrà eliminato tra 5 secondi...")
    await discord.utils.sleep_until(datetime.utcnow() + timedelta(seconds=5))
    await ctx.channel.delete()
@bot.command()
@commands.has_permissions(administrator=True)
async def removeroles(ctx, *roles: discord.Role):
    guild_id = str(ctx.guild.id)
    current_roles = authorized_roles.get(guild_id, [])

    removed = 0
    for role in roles:
        if role.id in current_roles:
            current_roles.remove(role.id)
            removed += 1

    authorized_roles[guild_id] = current_roles
    save_json(AUTHORIZED_FILE, authorized_roles)

    if removed > 0:
        await ctx.send(f"✅ {removed} ruolo(i) rimosso(i) dai ruoli autorizzati.")
    else:
        await ctx.send("ℹ️ Nessuno dei ruoli indicati era tra quelli autorizzati.")

@bot.command()
@commands.has_permissions(administrator=True)
async def rolelist(ctx):
    guild_id = str(ctx.guild.id)
    role_ids = authorized_roles.get(guild_id, [])
    if not role_ids:
        return await ctx.send("ℹ️ Nessun ruolo autorizzato impostato per questo server.")

    role_mentions = []
    for role_id in role_ids:
        role = ctx.guild.get_role(role_id)
        if role:
            role_mentions.append(role.mention)
        else:
            role_mentions.append(f"(ID sconosciuto: {role_id})")

    await ctx.send("🎫 Ruoli autorizzati per i ticket:\n" + ", ".join(role_mentions))

@bot.command()
async def claim(ctx):
    if not ctx.channel.name.startswith("ticket-"):
        return await ctx.send("❌ Questo comando può essere usato solo nei canali ticket.")

    guild_id = str(ctx.guild.id)
    channel_id = str(ctx.channel.id)

    # Controllo se l'autore ha almeno un ruolo autorizzato
    user_roles = [role.id for role in ctx.author.roles]
    allowed_roles = authorized_roles.get(guild_id, [])

    if not any(role_id in allowed_roles for role_id in user_roles):
        return await ctx.send("❌ Solo gli utenti con almeno un ruolo autorizzato possono rivendicare un ticket.")

    claimed_tickets[channel_id] = True
    save_json(CLAIMED_FILE, claimed_tickets)
    await ctx.send("🔒 Questo ticket è stato rivendicato. Solo utenti con ruoli autorizzati potranno chiuderlo.")

CONFIG_FILE = 'bot_config.json'

def load_config():
    """Carica la configurazione dal file JSON"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_config(config):
    """Salva la configurazione nel file JSON"""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

# Carica configurazione all'avvio
config = load_config()

@bot.event
async def on_ready():
    print(f'{bot.user} è online!')
    print(f'Bot connesso come {bot.user.name} (ID: {bot.user.id})')

@bot.command(name='benvenuto')
@commands.has_permissions(manage_guild=True)
async def set_welcome_channel(ctx):
    """Imposta il canale corrente per i messaggi di benvenuto"""
    guild_id = str(ctx.guild.id)
    channel_id = ctx.channel.id

    if guild_id not in config:
        config[guild_id] = {}

    config[guild_id]['welcome_channel'] = channel_id
    save_config(config)

    await ctx.send(f'✅ Canale di benvenuto impostato su {ctx.channel.mention}')

@bot.command(name='addio')
@commands.has_permissions(manage_guild=True)
async def set_goodbye_channel(ctx):
    """Imposta il canale corrente per i messaggi di addio"""
    guild_id = str(ctx.guild.id)
    channel_id = ctx.channel.id

    if guild_id not in config:
        config[guild_id] = {}

    config[guild_id]['goodbye_channel'] = channel_id
    save_config(config)

    await ctx.send(f'✅ Canale di addio impostato su {ctx.channel.mention}')

@bot.command(name='benvenutor')
@commands.has_permissions(manage_guild=True)
async def remove_welcome_channel(ctx):
    """Rimuove l'impostazione del canale di benvenuto"""
    guild_id = str(ctx.guild.id)

    if guild_id in config and 'welcome_channel' in config[guild_id]:
        del config[guild_id]['welcome_channel']
        save_config(config)
        await ctx.send('✅ Impostazione canale di benvenuto rimossa')
    else:
        await ctx.send('❌ Nessun canale di benvenuto era impostato')

@bot.command(name='addior')
@commands.has_permissions(manage_guild=True)
async def remove_goodbye_channel(ctx):
    """Rimuove l'impostazione del canale di addio"""
    guild_id = str(ctx.guild.id)

    if guild_id in config and 'goodbye_channel' in config[guild_id]:
        del config[guild_id]['goodbye_channel']
        save_config(config)
        await ctx.send('✅ Impostazione canale di addio rimossa')
    else:
        await ctx.send('❌ Nessun canale di addio era impostato')

@bot.event
async def on_member_join(member):
    """Evento quando un membro entra nel server"""
    guild_id = str(member.guild.id)

    if guild_id in config and 'welcome_channel' in config[guild_id]:
        channel_id = config[guild_id]['welcome_channel']
        channel = bot.get_channel(channel_id)

        if channel:
            member_count = member.guild.member_count

            embed = discord.Embed(
                title="🎉 Benvenuto!",
                description=f"Ciao {member.mention}! Benvenuto/a in **{member.guild.name}**!",
                color=0x00ff00
            )
            embed.add_field(
                name="👥 Membri totali", 
                value=f"Ora siamo **{member_count}** membri!", 
                inline=False
            )
            embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
            embed.set_footer(text=f"Entrato il {member.joined_at.strftime('%d/%m/%Y alle %H:%M')}")

            await channel.send(embed=embed)

@bot.event
async def on_member_remove(member):
    """Evento quando un membro esce dal server"""
    guild_id = str(member.guild.id)

    if guild_id in config and 'goodbye_channel' in config[guild_id]:
        channel_id = config[guild_id]['goodbye_channel']
        channel = bot.get_channel(channel_id)

        if channel:
            member_count = member.guild.member_count

            embed = discord.Embed(
                title="👋 Addio!",
                description=f"**{member.display_name}** ha lasciato il server.",
                color=0xff0000
            )
            embed.add_field(
                name="👥 Membri rimasti", 
                value=f"Ora siamo **{member_count}** membri.", 
                inline=False
            )
            embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)

            await channel.send(embed=embed)

@bot.command(name='info')
async def bot_info(ctx):
    """Mostra informazioni sui canali configurati"""
    guild_id = str(ctx.guild.id)

    embed = discord.Embed(
        title="ℹ️ Configurazione Bot",
        color=0x0099ff
    )

    if guild_id in config:
        welcome_channel_id = config[guild_id].get('welcome_channel')
        goodbye_channel_id = config[guild_id].get('goodbye_channel')

        if welcome_channel_id:
            welcome_channel = bot.get_channel(welcome_channel_id)
            embed.add_field(
                name="🎉 Canale Benvenuto", 
                value=welcome_channel.mention if welcome_channel else "Canale non trovato", 
                inline=False
            )
        else:
            embed.add_field(name="🎉 Canale Benvenuto", value="Non impostato", inline=False)

        if goodbye_channel_id:
            goodbye_channel = bot.get_channel(goodbye_channel_id)
            embed.add_field(
                name="👋 Canale Addio", 
                value=goodbye_channel.mention if goodbye_channel else "Canale non trovato", 
                inline=False
            )
        else:
            embed.add_field(name="👋 Canale Addio", value="Non impostato", inline=False)
    else:
        embed.add_field(name="Stato", value="Nessuna configurazione trovata", inline=False)

    embed.add_field(
        name="📝 Comandi disponibili",
        value="`!benvenuto` - Imposta canale benvenuto\n"
              "`!addio` - Imposta canale addio\n"
              "`!benvenutor` - Rimuovi canale benvenuto\n"
              "`!addior` - Rimuovi canale addio\n"
              "`!info` - Mostra questa informazione",
        inline=False
    )

    await ctx.send(embed=embed)

# Gestione errori per permessi
@set_welcome_channel.error
@set_goodbye_channel.error
@remove_welcome_channel.error
@remove_goodbye_channel.error
async def command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send('❌ Non hai i permessi necessari per usare questo comando (serve "Gestisci Server")')
@bot.command(name='purge')
@commands.has_permissions(manage_messages=True)
async def purge_messages(ctx, amount: int):
    """Cancella un numero specificato di messaggi (max 100, non più vecchi di 2 settimane)"""
    if amount <= 0:
        await ctx.send("❌ Il numero deve essere maggiore di 0!")
        return

    if amount > 100:
        await ctx.send("❌ Puoi cancellare massimo 100 messaggi alla volta!")
        return

    try:
        # Discord non permette di cancellare messaggi più vecchi di 14 giorni
        deleted = await ctx.channel.purge(limit=amount + 1)  # +1 per includere il comando stesso

        # Crea messaggio di conferma che si auto-cancella
        confirmation = await ctx.send(f"🗑️ **{len(deleted)} messaggi** sono stati cancellati!")

        # Cancella il messaggio di conferma dopo 5 secondi
        await confirmation.delete(delay=5)

    except discord.Forbidden:
        await ctx.send("❌ Non ho i permessi per cancellare i messaggi!")
    except discord.HTTPException as e:
        if "too old" in str(e).lower():
            await ctx.send("❌ Alcuni messaggi sono troppo vecchi per essere cancellati (più di 2 settimane)!")
        else:
            await ctx.send(f"❌ Errore durante la cancellazione: {e}")

@bot.command(name='kick')
@commands.has_permissions(kick_members=True)
async def kick_member(ctx, member: discord.Member, *, reason=None):
    """Espelle un membro dal server"""
    if member == ctx.author:
        await ctx.send("❌ Non puoi espellere te stesso!")
        return

    if member.top_role >= ctx.author.top_role:
        await ctx.send("❌ Non puoi espellere questo utente (ruolo uguale o superiore)!")
        return

    if member.top_role >= ctx.guild.me.top_role:
        await ctx.send("❌ Non posso espellere questo utente (il suo ruolo è troppo alto)!")
        return

    try:
        # Invia messaggio privato al membro (se possibile)
        try:
            dm_embed = discord.Embed(
                title="🦵 Sei stato espulso",
                description=f"Sei stato espulso da **{ctx.guild.name}**",
                color=0xff9900
            )
            if reason:
                dm_embed.add_field(name="Motivo", value=reason, inline=False)
            dm_embed.add_field(name="Moderatore", value=ctx.author.mention, inline=False)

            await member.send(embed=dm_embed)
        except:
            pass  # Ignore se non si può inviare DM

        await member.kick(reason=f"Espulso da {ctx.author} | Motivo: {reason or 'Nessun motivo specificato'}")

        embed = discord.Embed(
            title="🦵 Membro Espulso",
            description=f"**{member}** è stato espulso dal server",
            color=0xff9900
        )
        if reason:
            embed.add_field(name="Motivo", value=reason, inline=False)
        embed.add_field(name="Moderatore", value=ctx.author.mention, inline=False)

        await ctx.send(embed=embed)

    except discord.Forbidden:
        await ctx.send("❌ Non ho i permessi per espellere questo utente!")
    except Exception as e:
        await ctx.send(f"❌ Errore durante l'espulsione: {e}")

@bot.command(name='ban')
@commands.has_permissions(ban_members=True)
async def ban_member(ctx, member: discord.Member, *, reason=None):
    """Banna un membro dal server"""
    if member == ctx.author:
        await ctx.send("❌ Non puoi bannare te stesso!")
        return

    if member.top_role >= ctx.author.top_role:
        await ctx.send("❌ Non puoi bannare questo utente (ruolo uguale o superiore)!")
        return

    if member.top_role >= ctx.guild.me.top_role:
        await ctx.send("❌ Non posso bannare questo utente (il suo ruolo è troppo alto)!")
        return

    try:
        # Invia messaggio privato al membro (se possibile)
        try:
            dm_embed = discord.Embed(
                title="🔨 Sei stato bannato",
                description=f"Sei stato bannato da **{ctx.guild.name}**",
                color=0xff0000
            )
            if reason:
                dm_embed.add_field(name="Motivo", value=reason, inline=False)
            dm_embed.add_field(name="Moderatore", value=ctx.author.mention, inline=False)

            await member.send(embed=dm_embed)
        except:
            pass  # Ignore se non si può inviare DM

        await member.ban(reason=f"Bannato da {ctx.author} | Motivo: {reason or 'Nessun motivo specificato'}")

        embed = discord.Embed(
            title="🔨 Membro Bannato",
            description=f"**{member}** è stato bannato dal server",
            color=0xff0000
        )
        if reason:
            embed.add_field(name="Motivo", value=reason, inline=False)
        embed.add_field(name="Moderatore", value=ctx.author.mention, inline=False)

        await ctx.send(embed=embed)

    except discord.Forbidden:
        await ctx.send("❌ Non ho i permessi per bannare questo utente!")
    except Exception as e:
        await ctx.send(f"❌ Errore durante il ban: {e}")

@bot.command(name='unban')
@commands.has_permissions(ban_members=True)
async def unban_member(ctx, user_id: int, *, reason=None):
    """Rimuove il ban da un utente usando il suo ID"""
    try:
        user = await bot.fetch_user(user_id)
        await ctx.guild.unban(user, reason=f"Unbannato da {ctx.author} | Motivo: {reason or 'Nessun motivo specificato'}")

        embed = discord.Embed(
            title="✅ Ban Rimosso",
            description=f"**{user}** è stato sbannato",
            color=0x00ff00
        )
        if reason:
            embed.add_field(name="Motivo", value=reason, inline=False)
        embed.add_field(name="Moderatore", value=ctx.author.mention, inline=False)

        await ctx.send(embed=embed)

    except discord.NotFound:
        await ctx.send("❌ Utente non trovato o non bannato!")
    except discord.Forbidden:
        await ctx.send("❌ Non ho i permessi per rimuovere ban!")
    except Exception as e:
        await ctx.send(f"❌ Errore durante l'unban: {e}")

@bot.command(name='timeout')
@commands.has_permissions(moderate_members=True)
async def timeout_member(ctx, member: discord.Member, duration: int, unit: str = "m", *, reason=None):
    """
    Mette un membro in timeout
    Unità: s (secondi), m (minuti), h (ore), d (giorni)
    Esempio: !timeout @utente 10 m Spam
    """
    if member == ctx.author:
        await ctx.send("❌ Non puoi mettere in timeout te stesso!")
        return

    if member.top_role >= ctx.author.top_role:
        await ctx.send("❌ Non puoi mettere in timeout questo utente (ruolo uguale o superiore)!")
        return

    if member.top_role >= ctx.guild.me.top_role:
        await ctx.send("❌ Non posso mettere in timeout questo utente (il suo ruolo è troppo alto)!")
        return

    # Conversione unità di tempo
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if unit not in multipliers:
        await ctx.send("❌ Unità non valida! Usa: s (secondi), m (minuti), h (ore), d (giorni)")
        return

    seconds = duration * multipliers[unit]

    # Discord ha un limite massimo di 28 giorni per il timeout
    if seconds > 2419200:  # 28 giorni in secondi
        await ctx.send("❌ Il timeout non può superare i 28 giorni!")
        return

    try:
        timeout_until = discord.utils.utcnow() + discord.timedelta(seconds=seconds)
        await member.edit(timed_out_until=timeout_until, reason=f"Timeout da {ctx.author} | Motivo: {reason or 'Nessun motivo specificato'}")

        # Converti durata in formato leggibile
        time_str = f"{duration} {{\"s\":\"secondo/i\", \"m\":\"minuto/i\", \"h\":\"ora/e\", \"d\":\"giorno/i\"}}[unit]"

        embed = discord.Embed(
            title="⏰ Timeout Applicato",
            description=f"**{member}** è stato messo in timeout per **{time_str}**",
            color=0xffaa00
        )
        if reason:
            embed.add_field(name="Motivo", value=reason, inline=False)
        embed.add_field(name="Moderatore", value=ctx.author.mention, inline=False)
        embed.add_field(name="Scade il", value=f"<t:{int(timeout_until.timestamp())}:F>", inline=False)

        await ctx.send(embed=embed)

    except discord.Forbidden:
        await ctx.send("❌ Non ho i permessi per mettere in timeout questo utente!")
    except Exception as e:
        await ctx.send(f"❌ Errore durante il timeout: {e}")

@bot.command(name='untimeout')
@commands.has_permissions(moderate_members=True)
async def remove_timeout(ctx, member: discord.Member, *, reason=None):
    """Rimuove il timeout da un membro"""
    if not member.is_timed_out():
        await ctx.send("❌ Questo utente non è in timeout!")
        return

    try:
        await member.edit(timed_out_until=None, reason=f"Timeout rimosso da {ctx.author} | Motivo: {reason or 'Nessun motivo specificato'}")

        embed = discord.Embed(
            title="✅ Timeout Rimosso",
            description=f"Il timeout di **{member}** è stato rimosso",
            color=0x00ff00
        )
        if reason:
            embed.add_field(name="Motivo", value=reason, inline=False)
        embed.add_field(name="Moderatore", value=ctx.author.mention, inline=False)

        await ctx.send(embed=embed)

    except discord.Forbidden:
        await ctx.send("❌ Non ho i permessi per rimuovere il timeout!")
    except Exception as e:
        await ctx.send(f"❌ Errore durante la rimozione del timeout: {e}")

@bot.command(name='info_command')
async def info_command(ctx):
    # Your info command logic
    """Mostra informazioni sui canali configurati e comandi disponibili"""
    guild_id = str(ctx.guild.id)

    embed = discord.Embed(
        title="ℹ️ Configurazione Bot",
        color=0x0099ff
    )

    if guild_id in config:
        welcome_channel_id = config[guild_id].get('welcome_channel')
        goodbye_channel_id = config[guild_id].get('goodbye_channel')

        if welcome_channel_id:
            welcome_channel = bot.get_channel(welcome_channel_id)
            embed.add_field(
                name="🎉 Canale Benvenuto", 
                value=welcome_channel.mention if welcome_channel else "Canale non trovato", 
                inline=False
            )
        else:
            embed.add_field(name="🎉 Canale Benvenuto", value="Non impostato", inline=False)

        if goodbye_channel_id:
            goodbye_channel = bot.get_channel(goodbye_channel_id)
            embed.add_field(
                name="👋 Canale Addio", 
                value=goodbye_channel.mention if goodbye_channel else "Canale non trovato", 
                inline=False
            )
        else:
            embed.add_field(name="👋 Canale Addio", value="Non impostato", inline=False)
    else:
        embed.add_field(name="Stato", value="Nessuna configurazione trovata", inline=False)

    embed.add_field(
        name="📝 Comandi di Configurazione",
        value="`!benvenuto` - Imposta canale benvenuto\n"
              "`!addio` - Imposta canale addio\n"
              "`!benvenutor` - Rimuovi canale benvenuto\n"
              "`!addior` - Rimuovi canale addio\n"
              "`!info` - Mostra questa informazione",
        inline=False
    )

    embed.add_field(
        name="🛡️ Comandi di Moderazione",
        value="`!purge <numero>` - Cancella messaggi\n"
              "`!kick <utente> [motivo]` - Espelli utente\n"
              "`!ban <utente> [motivo]` - Banna utente\n"
              "`!unban <user_id> [motivo]` - Rimuovi ban\n"
              "`!timeout <utente> <durata> <unità> [motivo]` - Timeout\n"
              "`!untimeout <utente> [motivo]` - Rimuovi timeout",
        inline=False
    )

    await ctx.send(embed=embed)

# Gestione errori per tutti i comandi di moderazione
@purge_messages.error
@kick_member.error
@ban_member.error
@unban_member.error
@timeout_member.error
@remove_timeout.error
@set_welcome_channel.error
@set_goodbye_channel.error
@remove_welcome_channel.error
@remove_goodbye_channel.error
async def command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        perms_map = {
            'manage_messages': 'Gestisci Messaggi',
            'kick_members': 'Espelli Membri',
            'ban_members': 'Banna Membri',
            'moderate_members': 'Modera Membri',
            'manage_guild': 'Gestisci Server'
        }

        missing_perms = [perms_map.get(perm, perm) for perm in error.missing_permissions]
        await ctx.send(f'❌ Non hai i permessi necessari: **{", ".join(missing_perms)}**')
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send('❌ Utente non trovato! Assicurati di aver menzionato correttamente l\'utente.')
    elif isinstance(error, commands.BadArgument):
        await ctx.send('❌ Argomento non valido! Controlla la sintassi del comando.')
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f'❌ Argomento mancante: `{error.param.name}`')
    else:
        await ctx.send(f'❌ Si è verificato un errore: {error}')

def run_web():
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    run_web()



TOKEN = os.environ["TOKEN"]

bot.run(TOKEN)
