import discord
from discord.ext import commands
from discord import app_commands
import datetime
import aiosqlite
import csv
import os
import io
import asyncpg

TOKEN = os.environ['TOKEN']

# Enable intents for user interactions
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

# Create bot instance using discord.Client (for slash commands)
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

# Database Connection Function
async def connect_db():
    return await asyncpg.connect(os.getenv("DATABASE_URL"))

# Create Table in PostgreSQL
async def setup_db():
    conn = await connect_db()
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS work_sessions (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            username TEXT,
            task TEXT,
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            duration REAL
        )
    """)
    await conn.close()

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

    # Store session in PostgreSQL
    conn = await connect_db()
    await conn.execute(
        "INSERT INTO work_sessions (user_id, username, task, start_time, end_time, duration) VALUES ($1, $2, $3, $4, $5, $6)",
        user_id, interaction.user.name, task, start_time, end_time, duration
    )
    await conn.close()

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
    conn = await connect_db()
    rows = await conn.fetch("SELECT username, task, start_time, end_time, duration FROM work_sessions")
    await conn.close()

    if not rows:
        await interaction.response.send_message("No logs available to export.", ephemeral=True)
        return

    # Create CSV in-memory
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["User", "Task", "Start Time", "End Time", "Duration (mins)"])
    for row in rows:
        writer.writerow([row["username"], row["task"], row["start_time"], row["end_time"], row["duration"]])

    output.seek(0)
    await interaction.response.send_message("📂 Here is the exported work log:", file=discord.File(fp=output, filename="work_sessions.csv"))

# Bot Ready Event: Sync Commands
@bot.event
async def on_ready():
    await setup_db()
    await tree.sync()  # Sync slash commands
    print(f"✅ Logged in as {bot.user}")

# Run the bot
bot.run(TOKEN)
