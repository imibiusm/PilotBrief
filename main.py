
import os
import json
import asyncio
import aiohttp
import discord

from pathlib import Path
from dotenv import load_dotenv
from discord import app_commands
import requests

load_dotenv()

# ==========================================
# CONFIGURATION
# ==========================================

SIMBRIEF_URL = "https://www.simbrief.com/api/xml.fetcher.php"
DATA_FILE = Path("pilot_ids.json")
GUILD_ID = 1361644950307213413

intents = discord.Intents.default()

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ==========================================
# PILOT ID STORAGE
# ==========================================

def load_pilot_ids():
    if not DATA_FILE.exists():
        return {}

    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_pilot_ids(data):
    with DATA_FILE.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


pilot_ids = load_pilot_ids()


# ==========================================
# SIMBRIEF API
# ==========================================

async def fetch_simbrief_plan(pilot_id):
    params = {
        "userid": pilot_id,
        "json": "v2",
    }

    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(
            SIMBRIEF_URL,
            params=params,
        ) as response:

            if response.status != 200:
                raise RuntimeError(
                    f"SimBrief returned HTTP {response.status}."
                )

            try:
                data = await response.json(content_type=None)
            except (ValueError, aiohttp.ClientError):
                raise RuntimeError(
                    "SimBrief returned an invalid response."
                )

            if not isinstance(data, dict) or "general" not in data:
                raise RuntimeError(
                    "No flight plan found. Check your Pilot ID "
                    "and generate a flight plan on SimBrief."
                )

            return data


def get_airport(data, section):
    airport = data.get(section) or {}

    if not isinstance(airport, dict):
        return "Unknown"

    return (
        airport.get("icao_code")
        or airport.get("icao")
        or airport.get("iata_code")
        or airport.get("iata")
        or "Unknown"
    )


# ==========================================
# BOT READY
# ==========================================

 
@client.event
async def on_ready():
    try:
        synced = await tree.sync()
        print(f"Logged in as {client.user}")
        print(f"Synced {len(synced)} global slash commands")
        print("Bot ready!")
    except Exception as error:
        print(f"Failed to sync commands: {error}")



# ==========================================
# /setpilot
# ==========================================

@tree.command(
    name="setpilot",
    description="Link your SimBrief Pilot ID",
)
@app_commands.describe(pilot_id="Your numeric SimBrief Pilot ID")
async def setpilot(interaction: discord.Interaction, pilot_id: str):
    if not pilot_id.isdigit() or len(pilot_id) > 20:
        await interaction.response.send_message(
            "Enter a valid numeric SimBrief Pilot ID.",
            ephemeral=True,
        )
        return

    user_key = str(interaction.user.id)
    previous_id = pilot_ids.get(user_key)
    pilot_ids[user_key] = pilot_id

    try:
        save_pilot_ids(pilot_ids)
    except OSError:
        if previous_id is None:
            pilot_ids.pop(user_key, None)
        else:
            pilot_ids[user_key] = previous_id

        await interaction.response.send_message(
            "Couldn't save your Pilot ID. Please try again.",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        f"Your SimBrief Pilot ID has been saved as `{pilot_id}`.\n"
        "Use `/recent-flight-plan` to retrieve your flight plan.",
        ephemeral=True,
    )


# ==========================================
# /mypilot
# ==========================================

@tree.command(
    name="mypilot",
    description="View your saved SimBrief Pilot ID",
)
async def mypilot(interaction: discord.Interaction):
    pilot_id = pilot_ids.get(str(interaction.user.id))

    if not pilot_id:
        await interaction.response.send_message(
            "You haven't linked a Pilot ID yet. Use `/setpilot`.",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        f"Your saved SimBrief Pilot ID is `{pilot_id}`.",
        ephemeral=True,
    )


# ==========================================
# /delpilot
# ==========================================

@tree.command(
    name="delpilot",
    description="Remove your saved SimBrief Pilot ID",
)
async def delpilot(interaction: discord.Interaction):
    user_key = str(interaction.user.id)
    old_id = pilot_ids.pop(user_key, None)

    if old_id is None:
        await interaction.response.send_message(
            "You don't have a saved Pilot ID.",
            ephemeral=True,
        )
        return

    try:
        save_pilot_ids(pilot_ids)
    except OSError:
        pilot_ids[user_key] = old_id

        await interaction.response.send_message(
            "Couldn't remove your Pilot ID. Try again.",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        "Your saved Pilot ID has been removed.",
        ephemeral=True,
    )


# ==========================================
# /recent-flight-plan
# ==========================================

@tree.command(
    name="recent-flight-plan",
    description="Get your latest SimBrief flight plan",
)
async def recent_flight_plan(interaction: discord.Interaction):
    pilot_id = pilot_ids.get(str(interaction.user.id))

    if not pilot_id:
        await interaction.response.send_message(
            "Link your SimBrief account first using `/setpilot`.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(thinking=True)

    try:
        data = await fetch_simbrief_plan(pilot_id)

        general = data.get("general") or {}
        aircraft = data.get("aircraft") or {}

        departure = get_airport(data, "origin")
        arrival = get_airport(data, "destination")

        flight_number = general.get("flight_number") or "N/A"
        aircraft_type = (
            aircraft.get("icaocode")
            or aircraft.get("icao_code")
            or "N/A"
        )
        route = general.get("route") or "N/A"

        embed = discord.Embed(
            title=" SimBrief Flight Plan",
            description=f"**{departure} → {arrival}**",
            color=discord.Color.purple(),
        
        )

        embed.add_field(
            name="Flight Number",
            value=str(flight_number),
            inline=True,
        )
        embed.add_field(
            name="Aircraft",
            value=str(aircraft_type),
            inline=True,
        )
        embed.add_field(
            name="Departure",
            value=str(departure),
            inline=True,
        )
        embed.add_field(
            name="Arrival",
            value=str(arrival),
            inline=True,
        )
        embed.add_field(
            name="ATC Route",
            value=str(route)[:1024],
            inline=False,
        )

        embed.set_footer(
            text=f"Requested by {interaction.user.display_name}"
        )

        await interaction.followup.send(
            embed=embed,
            ephemeral=True
        )

    except (
        aiohttp.ClientError,
        asyncio.TimeoutError,
        RuntimeError,
        ValueError,
    ) as error:
        await interaction.followup.send(
            f" Couldn't retrieve the flight plan: {error}",
            ephemeral=True,
        )

    except Exception as error:
        print(f"Unexpected flight-plan error: {error}")
        await interaction.followup.send(
            " An unexpected error occurred.",
            ephemeral=True,
        )


WEATHERAPI_KEY = os.getenv("WEATHERAPI_KEY")

@tree.command(
    name="metar",
    description="Get airport weather",
)
@app_commands.describe(
    airport="ICAO airport code, e.g. EGLL"
)
async def metar(
    interaction: discord.Interaction,
    airport: str,
):
    airport = airport.strip().upper()

    if len(airport) != 4 or not airport.isalpha() or not airport.isascii():
        await interaction.response.send_message(
            "Enter a valid four-letter ICAO code, e.g. EGLL.",
            ephemeral=True,
        )
        return

    if not WEATHERAPI_KEY:
        await interaction.response.send_message(
            "WEATHERAPI_KEY is missing from your .env file.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(thinking=True)

    params = {
        "key": WEATHERAPI_KEY,
        "q": f"metar:{airport}",
        "aqi": "no",
    }

    try:
        # requests is synchronous, so run it in a worker thread
        response = await asyncio.to_thread(
            requests.get,
            "https://api.weatherapi.com/v1/current.json",
            params=params,
            timeout=15,
        )

        data = response.json()

        if response.status_code != 200 or "error" in data:
            error = data.get("error", {}).get(
                "message", f"HTTP {response.status_code}"
            )
            await interaction.followup.send(
                f"Weather lookup failed: {error}",
                ephemeral=True,
            )
            return

        location = data.get("location", {})
        current = data.get("current", {})
        condition = current.get("condition") or {}

        embed = discord.Embed(
            title=f"Airport Weather — {airport}",
            description=(
                f"**{location.get('name', airport)}**\n"
                f"{condition.get('text', 'Unknown conditions')}"
            ),
            color=discord.Color.purple(),
        )

        embed.add_field(
            name="Temperature",
            value=f"{current.get('temp_c', 'N/A')} °C",
            inline=True,
        )
        embed.add_field(
            name="Wind",
            value=(
                f"{current.get('wind_dir', 'N/A')} "
                f"{current.get('wind_kph', 'N/A')} km/h"
            ),
            inline=True,
        )
        embed.add_field(
            name="Visibility",
            value=f"{current.get('vis_km', 'N/A')} km",
            inline=True,
        )
        embed.add_field(
            name="Pressure",
            value=f"{current.get('pressure_mb', 'N/A')} hPa",
            inline=True,
        )
        embed.add_field(
            name="Humidity",
            value=f"{current.get('humidity', 'N/A')}%",
            inline=True,
        )
        embed.add_field(
            name="Cloud Cover",
            value=f"{current.get('cloud', 'N/A')}%",
            inline=True,
        )
        embed.add_field(
            name="Last Updated",
            value=str(current.get("last_updated", "Unknown")),
            inline=False,
        )
        embed.set_footer(
            text="Source: WeatherAPI.com"
        )

        await interaction.followup.send(embed=embed)

    except requests.RequestException as error:
        print(f"WeatherAPI request failed: {error}")
        await interaction.followup.send(
            "Could not connect to WeatherAPI.",
            ephemeral=True,
        )
    except (ValueError, asyncio.TimeoutError):
        await interaction.followup.send(
            "The weather service returned an invalid response or timed out.",
            ephemeral=True,
        )



# ==========================================
# START BOT
# ==========================================

token = os.getenv("DISCORD_TOKEN")

if not token:
    raise RuntimeError(
        "DISCORD_TOKEN is missing from your .env file."
    )

client.run(token)




