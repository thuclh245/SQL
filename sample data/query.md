refresh table hive.netbi.f_location_new;
refresh table hive.npms.kpi_access5g_5g_cell_peak_view;

WITH raw_data AS (
    SELECT
        CONCAT('${ETL_DATE}', '-00') AS date_hour,
        province_code,
        area_code,
        district_code,
        object_id,
        COUNT(*) AS no_bad_day,
        AVG(CAST(dl_user_throughput_mbps AS double)) AS dl_user_throughput_mbps
    FROM hive.npms.kpi_access5g_5g_cell_peak_view t
    WHERE country = 'VNM'
      and date_hour >= concat(date_format(date_sub(to_date('${ETL_DATE}'), 6), 'yyyy-MM-dd'), '-00')
        and date_hour <= concat(date_format(to_date('${ETL_DATE}'), 'yyyy-MM-dd'), '-00')
      AND CAST(nr_ps_traffic_total_gb as double) > 0
      AND CAST(dl_user_throughput_mbps as double) < 5
      AND CAST(dl_user_throughput_mbps as double) > 0
      AND NOT EXISTS (
          SELECT 1
          FROM hive.npms.occean_cell c
          WHERE c.object_id = t.object_id
            AND c.date_hour = '2026-01-01-00'
      )
    GROUP BY
        province_code,
        area_code,
        district_code,
        object_id
    HAVING COUNT(*) > 3
),
result AS (
    SELECT
        'VNM' AS country,
        area_code AS area_name,
        province_code,
        COUNT(object_id) AS kpi_value,
        date_hour,
        'bad_cell_throughput_5g' AS kpi_code
    FROM raw_data
    GROUP BY GROUPING SETS (
        (area_code, province_code, date_hour),
        (area_code, date_hour),
        (date_hour)
    )
)
SELECT
    r.country,
    r.area_name,
    r.province_code,
    f.province_name,
    r.kpi_value,
    CASE
        WHEN r.area_name IS NOT NULL AND r.province_code IS NOT NULL THEN 'province'
        WHEN r.area_name IS NOT NULL AND r.province_code IS NULL THEN 'area'
        WHEN r.area_name IS NULL AND r.province_code IS NULL THEN 'network'
    END AS location_level,
    r.date_hour,
    r.kpi_code
FROM result r
LEFT JOIN hive.netbi.f_location_new f
    ON r.province_code = f.province_code;