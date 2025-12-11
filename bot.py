# bot.py
import discord
from discord.ext import commands
import json
import os

# -------------- CONFIGURACIÓN BÁSICA -------------- #

import os
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("DISCORD_TOKEN")

INTENTS = discord.Intents.default()
INTENTS.message_content = True
INTENTS.guilds = True
INTENTS.members = True

bot = commands.Bot(command_prefix="!", intents=INTENTS)

DATA_FILE = "bot_data.json"

# Estados temporales para flujos interactivos
pending_agregar_obra = {}
pending_actualizacion = {}

# -------------- MANEJO DE DATOS (JSON) -------------- #

def load_data():
    if not os.path.exists(DATA_FILE):
        return {"servers": {}}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {"servers": {}}

def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

data = load_data()

def get_guild_data(guild: discord.Guild):
    gid = str(guild.id)
    if gid not in data["servers"]:
        data["servers"][gid] = {
            "roles": [],
            "channels": {"BL": None, "GL": None, "+15": None, "+18": None},
            "donacion": None,
            "works": {}
        }
        save_data()
    return data["servers"][gid]

def find_work_by_name_or_alias(guild: discord.Guild, name_or_alias: str):
    gd = get_guild_data(guild)
    works = gd["works"]
    if name_or_alias in works:
        return name_or_alias, works[name_or_alias]
    for nombre, info in works.items():
        if info.get("alias") == name_or_alias:
            return nombre, info
    return None, None

def is_authorized(ctx: commands.Context):
    gd = get_guild_data(ctx.guild)
    roles_permitidos = gd["roles"]
    if not roles_permitidos:
        return ctx.author.guild_permissions.administrator
    for rol in ctx.author.roles:
        if rol.id in roles_permitidos:
            return True
    if ctx.author.guild_permissions.administrator:
        return True
    return False

# -------------- EVENTO ON_READY -------------- #

@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")

# -------------- COMANDOS DE ROLES -------------- #

@bot.command()
@commands.has_permissions(administrator=True)
async def addrol(ctx, rol: discord.Role):
    gd = get_guild_data(ctx.guild)
    if rol.id not in gd["roles"]:
        gd["roles"].append(rol.id)
        save_data()
        await ctx.send(f"✅ Rol `{rol.name}` agregado como autorizado.")
    else:
        await ctx.send("⚠️ Ese rol ya estaba autorizado.")

@bot.command()
@commands.has_permissions(administrator=True)
async def delrol(ctx, rol: discord.Role):
    gd = get_guild_data(ctx.guild)
    if rol.id in gd["roles"]:
        gd["roles"].remove(rol.id)
        save_data()
        await ctx.send(f"✅ Rol `{rol.name}` eliminado.")
    else:
        await ctx.send("⚠️ Ese rol no estaba autorizado.")

@bot.command()
@commands.has_permissions(administrator=True)
async def verroles(ctx):
    gd = get_guild_data(ctx.guild)
    if not gd["roles"]:
        await ctx.send("ℹ️ No hay roles autorizados configurados.")
        return
    nombres = []
    for rid in gd["roles"]:
        rol = ctx.guild.get_role(rid)
        if rol:
            nombres.append(f"- {rol.name}")
    if not nombres:
        await ctx.send("ℹ️ Ningún rol válido encontrado.")
        return
    await ctx.send("🔐 Roles autorizados:\n" + "\n".join(nombres))

# -------------- COMANDOS DE CANALES -------------- #

@bot.command()
async def setcanal(ctx, categoria: str):
    if not is_authorized(ctx):
        await ctx.send("❌ No tienes permiso.")
        return
    categoria = categoria.upper()
    if categoria not in ["BL", "GL", "+15", "+18"]:
        await ctx.send("❌ Categoría inválida.")
        return
    gd = get_guild_data(ctx.guild)
    gd["channels"][categoria] = ctx.channel.id
    save_data()
    await ctx.send(f"✅ Canal configurado para `{categoria}`.")

@bot.command()
async def vercanales(ctx):
    gd = get_guild_data(ctx.guild)
    canales = gd["channels"]
    texto = "📺 Canales configurados:\n"
    for cat, cid in canales.items():
        if cid:
            ch = ctx.guild.get_channel(cid)
            texto += f"- {cat}: {ch.mention}\n" if ch else f"- {cat}: (canal no existe)\n"
        else:
            texto += f"- {cat}: (sin canal asignado)\n"
    await ctx.send(texto)

# -------------- SET DONACIÓN -------------- #

@bot.command()
async def setdonacion(ctx):
    if not is_authorized(ctx):
        await ctx.send("❌ No tienes permiso.")
        return
    await ctx.send("💖 Escribe ahora el mensaje de donaciones.")
    def check(m): return m.author == ctx.author and m.channel == ctx.channel
    msg = await bot.wait_for("message", check=check)
    gd = get_guild_data(ctx.guild)
    gd["donacion"] = msg.content
    save_data()
    await ctx.send("✅ Mensaje de donaciones actualizado.")

# -------------- AGREGAR OBRA -------------- #

@bot.command()
async def agregarobra(ctx, categoria: str, *, nombre_obra: str):
    if not is_authorized(ctx):
        await ctx.send("❌ No tienes permiso.")
        return

    categoria = categoria.upper()
    if categoria not in ["BL", "GL", "+15", "+18"]:
        await ctx.send("❌ Categoría inválida.")
        return

    gd = get_guild_data(ctx.guild)
    works = gd["works"]

    if nombre_obra in works:
        await ctx.send("⚠️ Esa obra ya existe.")
        return

    pending_agregar_obra[ctx.author.id] = {
        "guild_id": ctx.guild.id,
        "categoria": categoria,
        "nombre": nombre_obra,
        "sinopsis": None,
        "link": None,
        "agradecimientos": None
    }

    await ctx.send(f"📚 Registrando **{nombre_obra}**.\n📝 Escribe la **sinopsis**.")
    def check(m): return m.author == ctx.author and m.channel == ctx.channel
    msg_sinopsis = await bot.wait_for("message", check=check)
    pending_agregar_obra[ctx.author.id]["sinopsis"] = msg_sinopsis.content

    await ctx.send("🔗 Escribe el link base de la obra.")
    msg_link = await bot.wait_for("message", check=check)
    pending_agregar_obra[ctx.author.id]["link"] = msg_link.content

    await ctx.send("🙌 Escribe los agradecimientos (o `default`).")
    msg_agr = await bot.wait_for("message", check=check)
    if msg_agr.content.lower().strip() == "default":
        agradecimientos = "Gracias al staff por el excelente trabajo realizado."
    else:
        agradecimientos = msg_agr.content
    pending_agregar_obra[ctx.author.id]["agradecimientos"] = agradecimientos

    if gd["donacion"] is None:
        await ctx.send("💖 No hay donaciones aún. Escríbelo (o `ninguno`).")
        msg_don = await bot.wait_for("message", check=check)
        if msg_don.content.lower().strip() != "ninguno":
            gd["donacion"] = msg_don.content

    info = pending_agregar_obra.pop(ctx.author.id)
    works[nombre_obra] = {
        "categoria": info["categoria"],
        "sinopsis": info["sinopsis"],
        "link": info["link"],
        "agradecimientos": info["agradecimientos"],
        "alias": None
    }
    save_data()
    await ctx.send(f"✅ Obra **{nombre_obra}** registrada.")

# -------------- VER OBRAS -------------- #

@bot.command()
async def verobras(ctx):
    gd = get_guild_data(ctx.guild)
    works = gd["works"]
    if not works:
        await ctx.send("ℹ️ No hay obras registradas.")
        return
    texto = "📚 Obras registradas:\n"
    for nombre, info in works.items():
        texto += f"- {nombre} ({info['categoria']})"
        if info.get("alias"):
            texto += f" | alias: `{info['alias']}`"
        texto += "\n"
    await ctx.send(texto)

@bot.command()
async def verobra(ctx, *, nombre_o_alias: str):
    nombre, info = find_work_by_name_or_alias(ctx.guild, nombre_o_alias)
    if not info:
        await ctx.send(f"❌ No se encontró `{nombre_o_alias}`.")
        return
    texto = (
        f"📚 **{nombre}**\n"
        f"📂 Categoría: {info['categoria']}\n"
        f"📝 Sinopsis: {info['sinopsis']}\n"
        f"🔗 Link: {info['link']}\n"
        f"🙌 Agradecimientos: {info['agradecimientos']}\n"
        f"🏷️ Alias: `{info['alias']}`"
    )
    await ctx.send(texto)

# -------------- SETALIAS -------------- #

@bot.command(name="setalias")
async def setalias(ctx, nombre_obra: str, alias: str):
    if not is_authorized(ctx):
        await ctx.send("❌ No tienes permiso.")
        return

    gd = get_guild_data(ctx.guild)
    works = gd["works"]

    if nombre_obra not in works:
        await ctx.send(f"❌ No se encontró la obra `{nombre_obra}`.")
        return

    for n, info in works.items():
        if info.get("alias") == alias:
            await ctx.send(f"❌ El alias `{alias}` ya está en uso.")
            return

    works[nombre_obra]["alias"] = alias
    save_data()
    await ctx.send(f"✅ Alias asignado: `{nombre_obra}` → `{alias}`.")

# -------------- EDITALIAS -------------- #

@bot.command(name="editalias")
async def editalias(ctx, alias_viejo: str, alias_nuevo: str):
    if not is_authorized(ctx):
        await ctx.send("❌ No tienes permiso.")
        return

    gd = get_guild_data(ctx.guild)
    works = gd["works"]

    obra_encontrada = None
    for n, info in works.items():
        if info.get("alias") == alias_viejo:
            obra_encontrada = n
            break

    if not obra_encontrada:
        await ctx.send(f"❌ El alias `{alias_viejo}` no existe.")
        return

    for n, info in works.items():
        if info.get("alias") == alias_nuevo:
            await ctx.send(f"❌ El alias `{alias_nuevo}` ya está en uso.")
            return

    works[obra_encontrada]["alias"] = alias_nuevo
    save_data()
    await ctx.send(f"✅ Alias actualizado: `{alias_viejo}` → `{alias_nuevo}`.")

# -------------- LISTALIAS -------------- #

@bot.command(name="listalias")
async def listalias(ctx):
    gd = get_guild_data(ctx.guild)
    works = gd["works"]

    texto = "🏷️ Alias registrados:\n"
    hay = False

    for nombre, info in works.items():
        if info.get("alias"):
            hay = True
            texto += f"- **{nombre}** → `{info['alias']}`\n"

    if not hay:
        texto += "(no hay alias registrados)\n"

    await ctx.send(texto)

# -------------- EDITAR LINK -------------- #

@bot.command()
async def editarlink(ctx, nombre_o_alias: str, *, nuevo_link: str):
    if not is_authorized(ctx):
        await ctx.send("❌ No tienes permiso.")
        return

    nombre, info = find_work_by_name_or_alias(ctx.guild, nombre_o_alias)
    if not info:
        await ctx.send(f"❌ No se encontró `{nombre_o_alias}`.")
        return

    info["link"] = nuevo_link
    save_data()
    await ctx.send(f"✅ Link actualizado para **{nombre}**.")

# -------------- ACTUALIZACIÓN -------------- #

@bot.command()
async def actualizacion(ctx, categoria: str, *, nombre_o_alias: str):
    if not is_authorized(ctx):
        await ctx.send("❌ No tienes permiso.")
        return

    categoria = categoria.upper()
    if categoria not in ["BL", "GL", "+15", "+18"]:
        await ctx.send("❌ Categoría inválida.")
        return

    gd = get_guild_data(ctx.guild)
    canal_id = gd["channels"].get(categoria)
    if not canal_id:
        await ctx.send("❌ No hay canal configurado.")
        return

    canal_destino = ctx.guild.get_channel(canal_id)
    if not canal_destino:
        await ctx.send("❌ El canal configurado ya no existe.")
        return

    nombre, info = find_work_by_name_or_alias(ctx.guild, nombre_o_alias)
    if not info:
        await ctx.send(f"❌ No se encontró `{nombre_o_alias}`.")
        return

    await ctx.send("📍 Escribe **solo el número del capítulo** y adjunta **la imagen**.")

    def check(m): return m.author == ctx.author and m.channel == ctx.channel
    msg = await bot.wait_for("message", check=check)

    if not msg.attachments:
        await ctx.send("❌ Debes adjuntar una imagen.")
        return

    capitulo = msg.content.strip()
    imagen = msg.attachments[0].url

    await ctx.send("🙌 ¿Cambiar agradecimientos? (`sí`/`no`)")
    msg_agr = await bot.wait_for("message", check=check)

    agradecimientos = info["agradecimientos"]
    if msg_agr.content.lower().strip() in ["sí", "si", "yes"]:
        await ctx.send("✏️ Escribe el nuevo texto.")
        msg_agr2 = await bot.wait_for("message", check=check)
        agradecimientos = msg_agr2.content

    donacion = gd.get("donacion")

    embed = discord.Embed(
        title=f"Nuevo capítulo: {nombre}",
        description=(
            f"📝 **Sinopsis:**\n{info['sinopsis']}\n\n"
            f"📍 **Capítulo:** {capitulo}\n\n"
            f"🙌 **Agradecimientos:** {agradecimientos}\n"
        ),
        color=discord.Color.blue()
    )

      # LINK OCULTO Y CLICKEABLE (en descripción)
    embed.description += f"\n📎 [Lee el capítulo aquí]({info['link']})\n"

    if donacion:
        embed.add_field(name="💖 Donaciones", value=donacion, inline=False)

    embed.set_image(url=imagen)

    await canal_destino.send("||@everyone||", embed=embed, allowed_mentions=discord.AllowedMentions(everyone=True))

    await ctx.send(f"✅ Actualización enviada en {canal_destino.mention}.")

# -------------- COMANDOS DE AYUDA -------------- #

@bot.command()
async def comandos(ctx):
    embed = discord.Embed(title="📖 Lista completa", color=discord.Color.green())
    embed.add_field(
        name="📚 Obras",
        value=(
            "`!agregarobra +CAT Nombre`\n"
            "`!verobras`\n"
            "`!verobra Nombre/Alias`"
        ),
        inline=False
    )
    embed.add_field(
        name="🏷️ Alias",
        value=(
            "`!setalias Obra Alias`\n"
            "`!editalias AliasViejo AliasNuevo`\n"
            "`!listalias`"
        ),
        inline=False
    )
    embed.add_field(
        name="🚀 Actualización",
        value="`!actualizacion +CAT Nombre/Alias`",
        inline=False
    )
    embed.add_field(
        name="🔗 Link",
        value="`!editarlink Nombre/Alias NuevoLink`",
        inline=False
    )
    embed.add_field(
        name="🔐 Configuración",
        value=(
            "`!addrol @Rol`\n"
            "`!delrol @Rol`\n"
            "`!verroles`\n"
            "`!setcanal CAT`\n"
            "`!vercanales`\n"
            "`!setdonacion`"
        ),
        inline=False
    )
    await ctx.send(embed=embed)

@bot.command(name="comandos_staff")
async def comandos_staff(ctx):
    if not is_authorized(ctx):
        await ctx.send("❌ No tienes permiso.")
        return

    embed = discord.Embed(title="📌 Comandos del staff", color=discord.Color.purple())
    embed.add_field(
        name="📚 Obras",
        value="`!agregarobra +CAT Nombre`\n`!verobras`\n`!verobra Nombre/Alias`",
        inline=False
    )
    embed.add_field(
        name="🏷️ Alias",
        value="`!setalias Obra Alias`\n`!editalias AliasViejo AliasNuevo`\n`!listalias`",
        inline=False
    )
    embed.add_field(
        name="🚀 Actualización",
        value="`!actualizacion +CAT Nombre/Alias`",
        inline=False
    )
    embed.add_field(
        name="🔗 Link",
        value="`!editarlink Nombre/Alias NuevoLink`",
        inline=False
    )
    await ctx.send(embed=embed)

# -------------- INICIAR BOT -------------- #

bot.run(BOT_TOKEN)