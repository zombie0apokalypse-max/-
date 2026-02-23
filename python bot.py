import discord
from discord.ext import commands, tasks
import json, os
from datetime import datetime

import os
print("TOKEN:", os.getenv("TOKEN"))

import os
import discord

TOKEN = os.getenv("TOKEN")
print("TOKEN:", TOKEN)  # nur zum testen

client = discord.Client(intents=discord.Intents.default())

@client.event
async def on_ready():
    print("Bot ist online!")

client.run(TOKEN)


TOKEN = ""

PANEL_CHANNEL = "📉┃fahrzeug-leaderboard"
LOG_CHANNEL = "fahrzeug-logs"
LEADERBOARD_CHANNEL = "fahrzeug-leaderboard"

ADMIN_ROLES = ["Fahrzeug-Admin", "Gang-Leader"]

DATA_FILE = "fahrzeug_data.json"

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ================= DATA =================

def load_data():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE,"w") as f:
            json.dump({}, f)
    with open(DATA_FILE) as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE,"w") as f:
        json.dump(data,f,indent=4)

# ================= ADMIN =================

def is_admin(member):
    return any(r.name in ADMIN_ROLES for r in member.roles)

# ================= LOG =================

async def log(guild,msg):
    ch = discord.utils.get(guild.text_channels,name=LOG_CHANNEL)
    if ch:
        await ch.send(msg)

# ================= PANEL EMBED =================

def build_panel():
    data = load_data()

    embed = discord.Embed(
        title="🚗 Gang Fahrzeug Übersicht",
        color=discord.Color.green()
    )

    vehicles = []
    locations = {}

    for uid,info in data.items():
        if info["aktiv"]:
            vehicles.append((uid,info))
            locations.setdefault(info["ort"], []).append(info["fahrzeug"])

    embed.add_field(name="Aktive Fahrzeuge", value=len(vehicles), inline=False)

    if not vehicles:
        embed.description="Keine Fahrzeuge aktiv."
    else:
        vehicles.sort(key=lambda x: x[1]["ort"])

        for uid,info in vehicles:
            mitfahrer = ", ".join(info["mitfahrer"]) if info["mitfahrer"] else "Keine"
            embed.add_field(
                name=f"{info['fahrzeug']} ({info['typ']})",
                value=(
                    f"Fahrer: <@{uid}>\n"
                    f"Ort: {info['ort']}\n"
                    f"Sitze: {len(info['mitfahrer'])}/{info['sitze']}\n"
                    f"Mitfahrer: {mitfahrer}"
                ),
                inline=False
            )

    # Konvoi Radar
    for loc,vlist in locations.items():
        if len(vlist) >= 2:
            embed.add_field(name=f"⚡ Konvoi bei {loc}", value=", ".join(vlist), inline=False)

    return embed

# ================= VIEW =================

class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Einloggen", style=discord.ButtonStyle.green, custom_id="login")
    async def login(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(LoginModal())

    @discord.ui.button(label="Ausloggen", style=discord.ButtonStyle.red, custom_id="logout")
    async def logout(self, interaction: discord.Interaction, button: discord.ui.Button):

        data = load_data()
        uid = str(interaction.user.id)

        if uid not in data or not data[uid]["aktiv"]:
            return await interaction.response.send_message("Kein aktives Fahrzeug", ephemeral=True)

        data[uid]["aktiv"] = False
        save_data(data)

        await interaction.response.send_message("Ausgeloggt", ephemeral=True)

    @discord.ui.button(label="Beitreten", style=discord.ButtonStyle.blurple, custom_id="join")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):

        data = load_data()
        uid = str(interaction.user.id)

        for owner,info in data.items():
            if info["aktiv"] and len(info["mitfahrer"]) < info["sitze"]:
                if uid in info["mitfahrer"]:
                    return await interaction.response.send_message("Schon im Fahrzeug", ephemeral=True)
                info["mitfahrer"].append(uid)
                save_data(data)
                return await interaction.response.send_message("Beigetreten", ephemeral=True)

        await interaction.response.send_message("Kein freier Sitz", ephemeral=True)

    @discord.ui.button(label="Verlassen", style=discord.ButtonStyle.gray, custom_id="leave")
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        uid = str(interaction.user.id)

        for info in data.values():
            if uid in info["mitfahrer"]:
                info["mitfahrer"].remove(uid)
                save_data(data)
                return await interaction.response.send_message("Verlassen", ephemeral=True)

        await interaction.response.send_message("Nicht im Fahrzeug", ephemeral=True)

# ================= LOGIN MODAL =================

class LoginModal(discord.ui.Modal, title="Fahrzeug starten"):

    fahrzeug = discord.ui.TextInput(label="Fahrzeug Name")
    ort = discord.ui.TextInput(label="Ort")
    sitze = discord.ui.TextInput(label="Sitzplätze")
    typ = discord.ui.TextInput(label="Typ (Auto/Boot/Heli)")

    async def on_submit(self, interaction: discord.Interaction):
        if not self.sitze.value.isdigit():
            return await interaction.response.send_message("Sitze muss Zahl sein", ephemeral=True)

        data = load_data()
        uid = str(interaction.user.id)

        data[uid] = {
            "fahrzeug": self.fahrzeug.value,
            "ort": self.ort.value,
            "sitze": int(self.sitze.value),
            "typ": self.typ.value,
            "mitfahrer": [],
            "aktiv": True,
            "start": str(datetime.utcnow())
        }

        save_data(data)
        await interaction.response.send_message("Fahrzeug gestartet", ephemeral=True)

# ================= PANEL UPDATE =================

async def update_panel():
    channel = discord.utils.get(bot.get_all_channels(), name=PANEL_CHANNEL)
    if not channel:
        return

    async for msg in channel.history(limit=10):
        if msg.author == bot.user:
            await msg.edit(embed=build_panel())
            return

    await channel.send(embed=build_panel(), view=PanelView())

@tasks.loop(seconds=60)
async def auto_update():
    await update_panel()

# ================= LEADERBOARD =================

@tasks.loop(minutes=10)
async def leaderboard():
    data = load_data()
    totals = {}

    for uid,info in data.items():
        totals.setdefault(info["typ"], {})
        totals[info["typ"]][uid] = totals[info["typ"]].get(uid,0)+1

    ch = discord.utils.get(bot.get_all_channels(), name=LEADERBOARD_CHANNEL)
    if not ch:
        return

    embed = discord.Embed(title="🏆 Fahrzeug Leaderboard")

    for typ,users in totals.items():
        top = sorted(users.items(), key=lambda x:x[1], reverse=True)[:5]
        text="\n".join([f"<@{u}> — {t}" for u,t in top])
        embed.add_field(name=typ,value=text or "Keine Daten",inline=False)

    async for msg in ch.history(limit=5):
        if msg.author == bot.user:
            await msg.edit(embed=embed)
            return

    await ch.send(embed=embed)

# ================= READY =================

@bot.event
async def on_ready():
    bot.add_view(PanelView())
    await update_panel()
    auto_update.start()
    leaderboard.start()
    print("Bot bereit")

bot.run(TOKEN)
