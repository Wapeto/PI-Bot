import discord
from discord.ext import commands
from discord import app_commands
import datetime
import aiosqlite
import csv
import os

TOKEN = os.environ['TOKEN']

# Enable intents for user interactions
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

# Create bot instance using discord.Client (for slash commands)
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

DATABASE = "work_sessions.db"

# Create Database Table
async def setup_db():
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS work_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                task TEXT,
                start_time TEXT,
                end_time TEXT,
                duration REAL
            )
        """)
        await db.commit()

# Store active work sessions in memory
active_sessions = {}  # {user_id: (start_time, task)}

# Slash command to Start Work with Task Name
@tree.command(name="startwork", description="Start tracking your work session.")
async def startwork(interaction: discord.Interaction, task: str):
    user_id = interaction.user.id

    if user_id in active_sessions:
        await interaction.response.send_message(f"{interaction.user.mention}, you're already tracking a session!", ephemeral=True)
        return

    start_time = datetime.datetime.now()
    active_sessions[user_id] = (start_time, task)

    await interaction.response.send_message(f"⏳ {interaction.user.mention} started working on **{task}** at {start_time.strftime('%H:%M:%S')}.")

# Slash command to Stop Work
@tree.command(name="stopwork", description="Stop your current work session.")
async def stopwork(interaction: discord.Interaction):
    user_id = interaction.user.id

    if user_id not in active_sessions:
        await interaction.response.send_message(f"{interaction.user.mention}, you haven't started tracking yet!", ephemeral=True)
        return

    start_time, task = active_sessions.pop(user_id)
    end_time = datetime.datetime.now()
    duration = (end_time - start_time).total_seconds() / 60  # Convert to minutes

    # Store session in database
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("INSERT INTO work_sessions (user_id, username, task, start_time, end_time, duration) VALUES (?, ?, ?, ?, ?, ?)",
                         (user_id, interaction.user.name, task, start_time.strftime("%Y-%m-%d %H:%M:%S"),
                          end_time.strftime("%Y-%m-%d %H:%M:%S"), duration))
        await db.commit()

    await interaction.response.send_message(f"✅ {interaction.user.mention} stopped working on **{task}**. Duration: {duration:.2f} minutes.")

# Slash command to Check Active Sessions
@tree.command(name="status", description="See all active work sessions.")
async def status(interaction: discord.Interaction):
    if not active_sessions:
        await interaction.response.send_message("No active work sessions.", ephemeral=True)
        return

    response = "**Active Work Sessions:**\n"
    for user_id, (start_time, task) in active_sessions.items():
        user = interaction.guild.get_member(user_id)
        response += f"🔹 **{user.name}** - {task} (since {start_time.strftime('%H:%M:%S')})\n"

    await interaction.response.send_message(response)

# Slash command to Export Data to CSV
@tree.command(name="exportcsv", description="Export work logs as a CSV file.")
async def exportcsv(interaction: discord.Interaction):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("SELECT username, task, start_time, end_time, duration FROM work_sessions")
        logs = await cursor.fetchall()

    if not logs:
        await interaction.response.send_message("No logs available to export.", ephemeral=True)
        return

    filename = "work_sessions.csv"
    with open(filename, mode="w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["User", "Task", "Start Time", "End Time", "Duration (mins)"])
        writer.writerows(logs)

    await interaction.response.send_message(file=discord.File(filename))

# Bot Ready Event: Sync Commands
@bot.event
async def on_ready():
    await setup_db()
    await tree.sync()  # Sync slash commands
    print(f"✅ Logged in as {bot.user}")

# Run the bot
bot.run(TOKEN)
