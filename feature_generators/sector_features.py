# -*- coding: utf-8 -*-
"""
sector_features.py

Generates features.sector_features from raw.sector_data

Usage

python feature_generators/sector_features.py
"""

import os
import sys
import pandas as pd

sys.path.append(
    os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )
)

from database.db_utils import (
    get_connection,
    upsert_dataframe,
)

from indicators import sector


def compute_all_sectors(progress_callback=None):

    def log(msg):
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)

    con = get_connection()

    try:

        sectors = con.execute(
            """
            SELECT DISTINCT sector

            FROM raw.sector_data

            ORDER BY sector
            """
        ).fetchdf()

        total_rows = 0

        for i, row in sectors.iterrows():

            sector_name = row["sector"]

            df = con.execute(
                """
                SELECT

                    date,
                    close,
                    volume

                FROM raw.sector_data

                WHERE sector=?

                ORDER BY date
                """,
                [sector_name],
            ).fetchdf()

            if len(df) < 200:
                continue

            df = (
                df
                .set_index(
                    pd.to_datetime(df["date"])
                )
                .drop(columns=["date"])
            )

            try:

                feats = sector.compute_all(df)

            except Exception as e:

                print(f"{sector_name}: {e}")

                continue

            feats.insert(
                0,
                "sector",
                sector_name,
            )

            feats.insert(
                1,
                "date",
                feats.index.date,
            )

            feats = feats.reset_index(drop=True)

            n = upsert_dataframe(
                con,
                feats,
                "features.sector_features",
                keys=[
                    "sector",
                    "date",
                ],
            )

            total_rows += n

            log(
                f"[{i+1}/{len(sectors)}] "
                f"{sector_name} "
                f"{n} rows"
            )

        # ---------------------------------------------------
        # Compute daily sector ranks
        # ---------------------------------------------------

        con.execute(
            """
            UPDATE features.sector_features t

            SET sector_rank = r.rank

            FROM (

                SELECT

                    sector,

                    date,

                    RANK() OVER(

                        PARTITION BY date

                        ORDER BY relative_strength DESC

                    ) AS rank

                FROM features.sector_features

            ) r

            WHERE

                t.sector=r.sector

                AND

                t.date=r.date
            """
        )

        log("Sector ranking complete.")

        return total_rows

    finally:

        con.close()


if __name__ == "__main__":

    n = compute_all_sectors()

    print(
        f"\n✅ Upserted {n} rows into "
        f"features.sector_features"
    )