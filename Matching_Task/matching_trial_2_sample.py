#!/usr/bin/env python
# coding: utf-8

# ============================================================
# Logging setup (ADD THIS AT THE VERY TOP)
# ============================================================

import logging
import sys
from datetime import datetime

LOG_FILE = "matching_2.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="a"),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)

logger.info("=" * 90)
logger.info("MATCHING SCRIPT STARTED")
logger.info(f"Start time: {datetime.now()}")

# ============================================================
# Imports
# ============================================================

import pandas as pd
import re
import dask.dataframe as dd
import ast
import duckdb

from splink import Linker, SettingsCreator, block_on
from splink.backends.duckdb import DuckDBAPI


# ============================================================
# Main execution wrapper (CRITICAL)
# ============================================================

try:
    # ========================================================
    # Read LinkedIn data
    # ========================================================
    logger.info("Reading LinkedIn parquet file")

    linkedin_data = pd.read_parquet("joined_sample_us.parquet")
    logger.info(f"LinkedIn data loaded: shape={linkedin_data.shape}")

    linkedin_title = (
        linkedin_data[['title_raw', 'user_id', 'startdate', 'enddate']]
        .drop_duplicates()
        .reset_index(drop=True)
    )

    linkedin_data = (
        linkedin_data[['fullname', 'firstname', 'lastname', 'user_id', 'url_merged']]
        .drop_duplicates()
        .reset_index(drop=True)
    )

    logger.info(f"LinkedIn matching table prepared: shape={linkedin_data.shape}")

    # ========================================================
    # Keyword extraction
    # ========================================================
    logger.info("Extracting LinkedIn URL keywords")

    def extract_dot_keywords(x):
        if pd.isna(x):
            return None
        s = str(x).strip().lower()
        if not s:
            return None
        s = re.sub(r"^https?://", "", s)
        s = s.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
        if s.startswith("www."):
            s = s[4:]
        parts = [p for p in s.split(".") if p]
        return [[p] for p in parts] if parts else None

    linkedin_data["keywords"] = linkedin_data["url_merged"].apply(extract_dot_keywords)

    logger.info("Extracting officer email keywords")

    def extract_domain(email):
        if pd.isna(email) or "@" not in email:
            return None
        return email.split("@", 1)[1].lower()

    def email_to_keywords(email):
        domain = extract_domain(email)
        if not domain:
            return None
        return [[p] for p in domain.split(".") if p]

    officer_data = pd.read_csv("unmatched_sample.csv")
    logger.info("Officer keywords extracted and saved")

    # ========================================================
    # Pre-cleaning helpers
    # ========================================================
    logger.info("Normalizing names and parsing keyword tokens")

    def norm_series(s: pd.Series) -> pd.Series:
        return (
            s.astype("string")
             .fillna("")
             .str.strip()
             .str.lower()
             .replace({"": None})
        )

    def parse_keywords_to_tokens(x):
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return []
        if isinstance(x, (list, tuple)):
            toks = []
            for item in x:
                if isinstance(item, (list, tuple)) and len(item) > 0:
                    toks.append(str(item[0]).lower())
                else:
                    toks.append(str(item).lower())
        else:
            try:
                return parse_keywords_to_tokens(ast.literal_eval(str(x)))
            except Exception:
                toks = re.split(r"[.@_-]", str(x).lower())
        return sorted(set(t for t in toks if t))

    for c in ["firstname", "lastname", "fullname"]:
        officer_data[c] = norm_series(officer_data[c])
        linkedin_data[c] = norm_series(linkedin_data[c])

    officer_data["keywords_tokens"] = officer_data["keywords"].apply(parse_keywords_to_tokens)
    linkedin_data["keywords_tokens"] = linkedin_data["keywords"].apply(parse_keywords_to_tokens)

    linkedin_data["unique_id"] = linkedin_data["user_id"]

    # ========================================================
    # Prepare Splink inputs
    # ========================================================
    logger.info("Preparing Splink input tables")

    cols = ["unique_id", "firstname", "lastname", "fullname", "keywords_tokens"]
    officer_splink = officer_data[cols].copy()
    linkedin_splink = linkedin_data[cols].copy()

    # ========================================================
    # Splink settings
    # ========================================================
    logger.info("Building Splink settings")

    comparisons = [
        {
            "output_column_name": "firstname_cmp",
            "comparison_levels": [
                {"sql_condition": "firstname_l IS NULL OR firstname_r IS NULL", "is_null_level": True},
                {"sql_condition": "firstname_l = firstname_r"},
                {"sql_condition": "jaro_winkler_similarity(firstname_l, firstname_r) >= 0.95"},
                {"sql_condition": "TRUE"},
            ],
        },
        {
            "output_column_name": "lastname_cmp",
            "comparison_levels": [
                {"sql_condition": "lastname_l IS NULL OR lastname_r IS NULL", "is_null_level": True},
                {"sql_condition": "lastname_l = lastname_r"},
                {"sql_condition": "jaro_winkler_similarity(lastname_l, lastname_r) >= 0.95"},
                {"sql_condition": "TRUE"},
            ],
        },
        {
            "output_column_name": "fullname_cmp",
            "comparison_levels": [
                {"sql_condition": "fullname_l IS NULL OR fullname_r IS NULL", "is_null_level": True},
                {"sql_condition": "fullname_l = fullname_r"},
                {"sql_condition": "jaro_winkler_similarity(fullname_l, fullname_r) >= 0.94"},
                {"sql_condition": "TRUE"},
            ],
        },
        {
            "output_column_name": "keywords_overlap",
            "comparison_levels": [
                {"sql_condition": "list_count(keywords_tokens_l)=0 OR list_count(keywords_tokens_r)=0"},
                {"sql_condition": "list_count(list_intersect(keywords_tokens_l, keywords_tokens_r)) >= 2"},
                {"sql_condition": "list_count(list_intersect(keywords_tokens_l, keywords_tokens_r)) = 1"},
                {"sql_condition": "TRUE"},
            ],
        },
    ]

    blocking_rules = [
    """
    l.lastname = r.lastname
    AND list_count(coalesce(l.keywords_tokens, [])) > 0
    AND list_count(coalesce(r.keywords_tokens, [])) > 0
    AND list_count(list_intersect(
        coalesce(l.keywords_tokens, []),
        coalesce(r.keywords_tokens, [])
    )) >= 1
    """
    ]


    settings = SettingsCreator(
    link_type="link_only",
    unique_id_column_name="unique_id",
    comparisons=comparisons,
    blocking_rules_to_generate_predictions=blocking_rules,
    )

    # ========================================================
    # Run Splink
    # ========================================================
    logger.info("Starting Splink (DuckDB backend)")

    con = duckdb.connect()
    db_api = DuckDBAPI(connection=con)

    linker = Linker(
        [officer_splink, linkedin_splink],
        settings,
        db_api=db_api,
        input_table_aliases=["officer", "linkedin"]
    )

    logger.info("Estimating u parameters")
    linker.training.estimate_u_using_random_sampling(max_pairs=2_000_000)

    logger.info("Running EM training")
    linker.training.estimate_parameters_using_expectation_maximisation(
        "l.lastname = r.lastname"
    )

    logger.info("Running prediction")
    pred_df = linker.inference.predict().as_pandas_dataframe()
    logger.info(f"Predictions completed: {len(pred_df):,} rows")

    # ========================================================
    # Post-processing
    # ========================================================
    logger.info("Filtering and ranking matches")

    #pred_df = pred_df[pred_df["gamma_keywords_overlap"].isin([1, 2])]

    top_10 = (
        pred_df
        .sort_values(["unique_id_r", "match_probability"], ascending=[True, False])
        .groupby("unique_id_r", as_index=False)
        .head(10)
    )

    top_10 = top_10[top_10["match_probability"] >= 0.8]

    logger.info(f"Final matches retained: {len(top_10):,}")

    top_10 = top_10.merge(
        linkedin_title,
        left_on="unique_id_l",
        right_on="user_id",
        how="left"
    ).drop_duplicates(
        subset=["unique_id_l", "unique_id_r", "title_raw"]
    )

    top_10.to_csv("linkedin_officer_sample.csv", index=False)
    logger.info("Final output written to \\Final\\linkedin_officer_sample.csv")

    logger.info("SCRIPT COMPLETED SUCCESSFULLY")

except Exception:
    logger.exception("SCRIPT FAILED WITH ERROR")
    raise
