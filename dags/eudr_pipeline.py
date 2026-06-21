from airflow.decorators import dag, task
from datetime import datetime, timedelta

@dag(
    schedule=None,
    start_date=datetime(2024,1,1),
    catchup=False,
    tags=["eudr"],
    default_args={
        "retries": 3,
        "retry_delay": timedelta(minutes=2),
        "retry_exponential_backoff": True,
    }
)
def eudr_pipeline():

    @task
    def detect_loss() -> int:
        """Per-plot Hansen post-2020 loss → upsert to plot_loss_results."""
        import geopandas as gpd
        from airflow.providers.postgres.hooks.postgres import PostgresHook
        from psycopg2.extras import execute_values
        from eudr.loss import loss_records
        import logging
        log = logging.getLogger("airflow.task")
        import os, subprocess, contextlib

        @contextlib.contextmanager
        def r2_credential(vault_path="/opt/airflow/secrets.enc.yaml"):
            """decrypt vault > set GDAL s3 env vars for the R2 read only then wipe"""
            raw = subprocess.run(
                ["sops", "-d", vault_path],
                capture_output=True, text=True, check=True,
            ).stdout
            vault = {
                k.strip(): v.strip().strip('""')
                for k, v in (l.split(":",1) for l in raw.splitlines() if ":" in l and not l.startswith(" "))
            }
            gdal_env = {
                "AWS_ACCESS_KEY_ID": vault["R2_ACCESS_KEY_ID"],
                "AWS_SECRET_ACCESS_KEY": vault["R2_SECRET_ACCESS_KEY"],
                "AWS_S3_ENDPOINT": vault["R2_ENDPOINT"].replace("https://", "").replace("http//",""),
                "AWS_VIRTUAL_HOSTING": "FALSE",
                "AWS_HTTPS": "YES",
            }
            os.environ.update(gdal_env)
            try:
                yield
            finally:
                for k in gdal_env:
                    os.environ.pop(k, None)

        #stream from R2 (private bucket)
        hansen_path = "/vsis3/eudr-data/hansen/Hansen_GFC-2024-v1.12_lossyear_00N_110E.tif"

        hook = PostgresHook(postgres_conn_id="eudr_postgres")
        conn = hook.get_conn()
        plots = gpd.read_postgis(
            "SELECT plot_id, expected_status, geom FROM plots",
            conn, geom_col="geom",
        )

        with r2_credential():
            records = loss_records(hansen_path, plots)     # pure logic in src/
        log.info("Computed loss for %d plots", len(records))

        with conn, conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS plot_loss_results (
                    plot_id text PRIMARY KEY,
                    expected_status text,
                    total_loss_px integer,
                    post2020_loss_px integer,
                    post2020_loss_ha real,
                    flagged boolean
                );
            """)
            execute_values(cur, """
                INSERT INTO plot_loss_results
                    (plot_id, expected_status, total_loss_px,
                     post2020_loss_px, post2020_loss_ha, flagged)
                VALUES %s
                ON CONFLICT (plot_id) DO UPDATE
                  SET expected_status  = EXCLUDED.expected_status,
                      total_loss_px    = EXCLUDED.total_loss_px,
                      post2020_loss_px = EXCLUDED.post2020_loss_px,
                      post2020_loss_ha = EXCLUDED.post2020_loss_ha,
                      flagged          = EXCLUDED.flagged;
            """, records)

        conn.close()
        log.info("Upserted %d rows to plot_loss_results", len(records))
        return len(records)

    @task
    def fetch_scenes() -> dict:
        """Find baseline and current Sentinel-2 scene IDs over the AOI"""
        import pystac_client
        import planetary_computer

        catalog = pystac_client.Client.open(
            "https://planetarycomputer.microsoft.com/api/stac/v1",
            modifier=planetary_computer.sign_inplace
        )

        bbox = [110.09, -1.89, 110.20, -1.83]

        def clearest(start,end):
            search = catalog.search(
                collections=["sentinel-2-l2a"],
                bbox=bbox,
                datetime=f"{start}/{end}",
                query={"eo:cloud_cover":{"lt": 20}},
            )
            items = [i for i in search.items() if "T49MCT" in i.id]
            items.sort(key=lambda i: i.properties["eo:cloud_cover"])
            return items[0].id #take only the id string
        
        return {
            "baseline" : clearest("2020-05-01","2020-07-31"),
            "current": clearest("2025-05-01","2025-07-31"),
        }
    
    @task
    def compute_ndvi(scenes: dict) -> int:
        """Read NDVI per plot for both scenes, upsert to ndvi_observations."""
        import geopandas as gpd
        from airflow.providers.postgres.hooks.postgres import PostgresHook
        from psycopg2.extras import execute_values
        from eudr.ndvi import open_scenes, ndvi_records
        import logging
        log = logging.getLogger("airflow.task")

        items = open_scenes(scenes)                  # logic in src/
        log.info("Re-opened scenes: %s", list(items.keys()))

        hook = PostgresHook(postgres_conn_id="eudr_postgres")
        conn = hook.get_conn()
        plots = gpd.read_postgis("SELECT plot_id, geom FROM plots", conn, geom_col="geom")

        records = ndvi_records(items, plots)         # logic in src/
        log.info("Computed NDVI for %d plot-date rows", len(records))

        with conn, conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ndvi_observations (
                    plot_id text NOT NULL, obs_date date NOT NULL,
                    mean_ndvi real NOT NULL, scene_id text,
                    created_at timestamptz DEFAULT now(),
                    PRIMARY KEY (plot_id, obs_date)
                );
            """)
            execute_values(cur, """
                INSERT INTO ndvi_observations (plot_id, obs_date, mean_ndvi, scene_id)
                VALUES %s
                ON CONFLICT (plot_id, obs_date) DO UPDATE
                SET mean_ndvi = EXCLUDED.mean_ndvi,
                    scene_id  = EXCLUDED.scene_id,
                    created_at = now();
            """, records)

        conn.close()
        log.info("Upserted %d rows to ndvi_observations", len(records))
        return len(records)
    
    @task
    def cross_check_hansen() -> int:
        """Join Hansen + NDVI, classify each plot, upsert to plot_compliance."""
        from airflow.providers.postgres.hooks.postgres import PostgresHook
        from psycopg2.extras import execute_values
        from eudr.cross_check import JOIN_QUERY, build_verdicts

        hook = PostgresHook(postgres_conn_id="eudr_postgres")
        conn = hook.get_conn()

        with conn.cursor() as cur:
            cur.execute(JOIN_QUERY)
            rows = cur.fetchall()          # the joined data, server-side

        verdicts = build_verdicts(rows)    # pure transform → verdict tuples

        with conn, conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS plot_compliance (
                    plot_id text PRIMARY KEY,
                    status text NOT NULL,
                    ndvi_delta real,
                    post2020_loss_ha real,
                    expected_status text,
                    checked_at timestamptz DEFAULT now()
                );
            """)
            execute_values(cur, """
                INSERT INTO plot_compliance
                    (plot_id, status, ndvi_delta, post2020_loss_ha, expected_status)
                VALUES %s
                ON CONFLICT (plot_id) DO UPDATE
                  SET status = EXCLUDED.status,
                      ndvi_delta = EXCLUDED.ndvi_delta,
                      post2020_loss_ha = EXCLUDED.post2020_loss_ha,
                      expected_status = EXCLUDED.expected_status,
                      checked_at = now();
            """, verdicts)

        conn.close()
        return len(verdicts)
    
    scenes = fetch_scenes()
    ndvi = compute_ndvi(scenes)
    loss = detect_loss()
    cross = cross_check_hansen()
    [ndvi, loss] >> cross

eudr_pipeline()