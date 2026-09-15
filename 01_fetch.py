import time
import os
import requests
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd


env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

USERNAME = os.getenv("EPIAS_USERNAME")
PASSWORD = os.getenv("EPIAS_PASSWORD")

AUTH_URL = "https://giris.epias.com.tr/cas/v1/tickets"

CONSUMPTION_URL = (
    "https://seffaflik.epias.com.tr/"
    "electricity-service/v1/consumption/data/realtime-consumption"
)


def get_tgt(username, password):
    response = requests.post(
        AUTH_URL,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "text/plain",
        },
        data={
            "username": username,
            "password": password,
        },
        timeout=30,
    )

    response.raise_for_status()

    return response.text.strip()


def monthly_chunks(start_date, end_date):
    start = pd.Timestamp(start_date, tz="Europe/Istanbul")
    end = pd.Timestamp(end_date, tz="Europe/Istanbul")

    current = start

    while current <= end:
        next_month = current + pd.offsets.MonthBegin(1)

        chunk_end = min(
            next_month - pd.Timedelta(hours=1),
            end
        )

        yield current, chunk_end

        current = next_month


def fetch_consumption_chunk(tgt, start_date, end_date):
    response = requests.post(
        CONSUMPTION_URL,
        headers={
            "TGT": tgt,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        json={
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
        },
        timeout=60,
    )

    response.raise_for_status()

    data = response.json()

    return pd.DataFrame(data["items"])


def fetch_consumption(
    username,
    password,
    start_date,
    end_date,
    sleep_seconds=1
):
    all_dataframes = []

    # Get the initial TGT
    tgt = get_tgt(username, password)

    # Record when the TGT was created
    tgt_created_at = time.monotonic()

    # Iterate through the requested date range month by month
    for chunk_start, chunk_end in monthly_chunks(
        start_date,
        end_date
    ):

        # Calculate how long the current TGT has been active
        tgt_age = time.monotonic() - tgt_created_at

        # Refresh the TGT if it is older than 90 minutes
        if tgt_age > 90 * 60:
            print("Refreshing TGT...")

            tgt = get_tgt(
                username,
                password
            )

            tgt_created_at = time.monotonic()

        # Log the current monthly chunk being fetched
        print(
            f"Fetching: "
            f"{chunk_start:%Y-%m-%d} -> "
            f"{chunk_end:%Y-%m-%d}"
        )

        # Fetch consumption data for the current month
        df_month = fetch_consumption_chunk(
            tgt,
            chunk_start,
            chunk_end
        )

        # Store the monthly DataFrame
        all_dataframes.append(df_month)

        # Pause briefly to avoid sending requests too quickly
        time.sleep(sleep_seconds)

    # Combine all monthly DataFrames into a single DataFrame
    df = pd.concat(
        all_dataframes,
        ignore_index=True
    )

    return df


if __name__ == "__main__":

    # Define the output file path
    output_path = (
        Path(__file__).parent
        / "data"
        / "raw"
        / "consumption_2017_2026.parquet"
    )

    # Make sure the output directory exists
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # Fetch the full historical consumption dataset
    df = fetch_consumption(
        username=USERNAME,
        password=PASSWORD,
        start_date="2017-01-01 00:00:00",
        end_date="2026-08-30 23:00:00",
        sleep_seconds=1
    )

    # Save the raw dataset to disk
    df.to_parquet(
        output_path,
        index=False
    )

    print()
    print("Backfill completed.")
    print("Total rows:", len(df))
    print("Saved to:", output_path)