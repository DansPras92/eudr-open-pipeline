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
    cross = cross_check_hansen()
    ndvi >> cross

eudr_pipeline()