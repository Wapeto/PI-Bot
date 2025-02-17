import discord
from discord.ext import commands
from discord import app_commands
import datetime
import asyncpg
import csv
import os
import io

TOKEN = os.environ["TOKEN"]

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
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS work_sessions (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            username TEXT,
            task TEXT,
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            duration REAL
        )
        """
    )
    await conn.close()


# Store active work sessions in memory
active_sessions = {}  # {user_id: (start_time, task)}


# Slash command to Start Work with Task Name
@tree.command(name="startwork", description="Start tracking your work session.")
async def startwork(interaction: discord.Interaction, task: str):
    user_id = interaction.user.id
    guild = interaction.guild
    working_role = discord.utils.get(guild.roles, name="Working")

    if user_id in active_sessions:
        await interaction.response.send_message(
            f"{interaction.user.mention}, you're already tracking a session!",
            ephemeral=True,
        )
        return

    start_time = datetime.datetime.now()
    active_sessions[user_id] = (start_time, task)

    # Assign "Working" role
    if working_role:
        await interaction.user.add_roles(working_role)

    await interaction.response.send_message(
        f"⏳ {interaction.user.mention} started working on **{task}** at {start_time.strftime('%H:%M:%S')}."
    )


# Slash command to Stop Work
@tree.command(name="stopwork", description="Stop your current work session.")
async def stopwork(interaction: discord.Interaction):
    user_id = interaction.user.id
    guild = interaction.guild
    working_role = discord.utils.get(guild.roles, name="Working")

    if user_id not in active_sessions:
        await interaction.response.send_message(
            f"{interaction.user.mention}, you haven't started tracking yet!",
            ephemeral=True,
        )
        return

    start_time, task = active_sessions.pop(user_id)
    end_time = datetime.datetime.now()
    duration = (end_time - start_time).total_seconds() / 60  # Convert to minutes

    # Store session in PostgreSQL
    conn = await connect_db()
    await conn.execute(
        "INSERT INTO work_sessions (user_id, username, task, start_time, end_time, duration) VALUES ($1, $2, $3, $4, $5, $6)",
        user_id,
        interaction.user.name,
        task,
        start_time,
        end_time,
        duration,
    )
    await conn.close()

    # Remove "Working" role
    if working_role:
        await interaction.user.remove_roles(working_role)

    await interaction.response.send_message(
        f"✅ {interaction.user.mention} stopped working on **{task}**. Duration: {duration:.2f} minutes."
    )


# Slash command to Export Data to CSV
@tree.command(name="exportcsv", description="Export work logs as a CSV file.")
async def exportcsv(interaction: discord.Interaction):
    conn = await connect_db()
    rows = await conn.fetch(
        "SELECT username, task, start_time, end_time, duration FROM work_sessions"
    )
    await conn.close()

    if not rows:
        await interaction.response.send_message(
            "No logs available to export.", ephemeral=True
        )
        return

    # Create CSV in-memory
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["User", "Task", "Start Time", "End Time", "Duration (mins)"])
    for row in rows:
        writer.writerow(
            [
                row["username"],
                row["task"],
                row["start_time"],
                row["end_time"],
                row["duration"],
            ]
        )

    output.seek(0)
    await interaction.response.send_message(
        "📂 Here is the exported work log:",
        file=discord.File(fp=output, filename="work_sessions.csv"),
    )


# Slash command to Check Work Stats
@tree.command(name="stats", description="Check your work stats.")
async def stats(interaction: discord.Interaction):
    conn = await connect_db()
    row = await conn.fetchrow(
        "SELECT SUM(duration) as total_time FROM work_sessions WHERE user_id=$1",
        interaction.user.id,
    )
    await conn.close()

    total_time = row["total_time"] or 0  # Handle None case
    await interaction.response.send_message(
        f"📊 **Total Time Worked:** {total_time:.2f} minutes."
    )


# Modal for Manual Time Entry
class ManualTimeModal(discord.ui.Modal, title="Manual Time Entry"):
    task_name = discord.ui.TextInput(
        label="Task Name", placeholder="Enter task description", required=True
    )
    start_time = discord.ui.TextInput(
        label="Start Time", placeholder="YYYY-MM-DD HH:MM", required=True
    )
    end_time = discord.ui.TextInput(
        label="End Time", placeholder="YYYY-MM-DD HH:MM", required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        username = interaction.user.name

        try:
            start_time = datetime.datetime.strptime(
                self.start_time.value, "%Y-%m-%d %H:%M"
            )
            end_time = datetime.datetime.strptime(self.end_time.value, "%Y-%m-%d %H:%M")
            duration = (end_time - start_time).total_seconds() / 60  # Convert to minutes

            # Store session in database
            conn = await connect_db()
            await conn.execute(
                "INSERT INTO work_sessions (user_id, username, task, start_time, end_time, duration) VALUES ($1, $2, $3, $4, $5, $6)",
                user_id,
                username,
                self.task_name.value,
                start_time,
                end_time,
                duration,
            )
            await conn.close()

            await interaction.response.send_message(
                f"✅ Manual entry added for **{self.task_name.value}**.\n⏳ Start: {self.start_time.value}\n🛑 End: {self.end_time.value}\n📊 Duration: {duration:.2f} mins.",
                ephemeral=True,
            )

        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid time format! Use `YYYY-MM-DD HH:MM`.", ephemeral=True
            )


# Slash Command to Trigger the Modal
@tree.command(name="manualtime", description="Manually add a work session.")
async def manualtime(interaction: discord.Interaction):
    await interaction.response.send_modal(ManualTimeModal())


# Bot Ready Event: Sync Commands
@bot.event
async def on_ready():
    await setup_db()
    await tree.sync()
    print(f"✅ Logged in as {bot.user}")


# Run the bot
bot.run(TOKEN)
