CREATE DATABASE IF NOT EXISTS sensor_demo;
USE sensor_demo;

CREATE TABLE IF NOT EXISTS readings (
    sensor VARCHAR(10) NOT NULL,
    ts DATETIME(3) NOT NULL,
    val DOUBLE NOT NULL,
    KEY idx_sensor_ts (sensor, ts)
) PARTITION BY RANGE (TO_DAYS(ts)) (
    PARTITION pmax VALUES LESS THAN MAXVALUE
);

CREATE TABLE IF NOT EXISTS alerts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sensor VARCHAR(10) NOT NULL,
    ts DATETIME(3) NOT NULL,
    val DOUBLE NOT NULL,
    z_score DOUBLE NOT NULL,
    severity VARCHAR(4) NOT NULL,
    UNIQUE KEY uq_alert (sensor, ts)
);

CREATE TABLE IF NOT EXISTS readings_hourly (
    sensor VARCHAR(10) NOT NULL,
    hour_start DATETIME NOT NULL,
    avg_v DOUBLE,
    min_v DOUBLE,
    max_v DOUBLE,
    cnt INT,
    PRIMARY KEY (sensor, hour_start)
);

DROP PROCEDURE IF EXISTS sp_insert_reading;
DROP PROCEDURE IF EXISTS sp_detect;
DROP PROCEDURE IF EXISTS sp_maintain;
DROP PROCEDURE IF EXISTS sp_refresh_summary;
DROP PROCEDURE IF EXISTS sp_chart;
DROP PROCEDURE IF EXISTS sp_alerts;
DROP PROCEDURE IF EXISTS sp_get_summary;
DROP PROCEDURE IF EXISTS sp_partitions;
DROP PROCEDURE IF EXISTS sp_latest;

DELIMITER $$

CREATE PROCEDURE sp_insert_reading(IN p_sensor VARCHAR(10), IN p_val DOUBLE)
BEGIN
    INSERT INTO readings (sensor, ts, val) VALUES (p_sensor, NOW(3), p_val);
END$$

CREATE PROCEDURE sp_detect(IN p_z DOUBLE)
BEGIN
    INSERT IGNORE INTO alerts (sensor, ts, val, z_score, severity)
    SELECT sensor, ts, val, zs, IF(ABS(zs) > 8, 'HIGH', 'LOW')
    FROM (
        SELECT sensor, ts, val,
               (val - AVG(val) OVER w) / NULLIF(STDDEV_SAMP(val) OVER w, 0) AS zs,
               COUNT(*) OVER w AS c
        FROM readings
        WHERE ts > NOW(3) - INTERVAL 5 MINUTE
        WINDOW w AS (PARTITION BY sensor ORDER BY ts
                     ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING)
    ) t
    WHERE c >= 10 AND ABS(zs) > p_z AND ts > NOW(3) - INTERVAL 10 SECOND;
END$$

CREATE PROCEDURE sp_maintain()
BEGIN
    DECLARE i INT DEFAULT 0;
    DECLARE pname VARCHAR(20);
    DECLARE next_num INT;

    WHILE i < 2 DO
        SET pname = CONCAT('p', DATE_FORMAT(CURDATE() + INTERVAL i DAY, '%Y%m%d'));
        SET next_num = TO_DAYS(CURDATE() + INTERVAL (i + 1) DAY);
        SELECT COUNT(*) INTO @found FROM information_schema.partitions
        WHERE table_schema = DATABASE() AND table_name = 'readings'
          AND partition_name = pname;
        IF @found = 0 THEN
            SET @sql = CONCAT('ALTER TABLE readings REORGANIZE PARTITION pmax INTO (',
                'PARTITION ', pname, ' VALUES LESS THAN (', next_num, '), ',
                'PARTITION pmax VALUES LESS THAN MAXVALUE)');
            PREPARE st FROM @sql;
            EXECUTE st;
            DEALLOCATE PREPARE st;
        END IF;
        SET i = i + 1;
    END WHILE;

    SELECT GROUP_CONCAT(partition_name) INTO @old FROM information_schema.partitions
    WHERE table_schema = DATABASE() AND table_name = 'readings'
      AND partition_name IS NOT NULL AND partition_name <> 'pmax'
      AND partition_name < CONCAT('p', DATE_FORMAT(CURDATE() - INTERVAL 2 DAY, '%Y%m%d'));
    IF @old IS NOT NULL THEN
        SET @sql = CONCAT('ALTER TABLE readings DROP PARTITION ', @old);
        PREPARE st FROM @sql;
        EXECUTE st;
        DEALLOCATE PREPARE st;
    END IF;
END$$

CREATE PROCEDURE sp_refresh_summary()
BEGIN
    REPLACE INTO readings_hourly (sensor, hour_start, avg_v, min_v, max_v, cnt)
    SELECT sensor, DATE_FORMAT(ts, '%Y-%m-%d %H:00:00'),
           AVG(val), MIN(val), MAX(val), COUNT(*)
    FROM readings
    WHERE ts >= DATE_FORMAT(NOW() - INTERVAL 1 HOUR, '%Y-%m-%d %H:00:00')
    GROUP BY sensor, DATE_FORMAT(ts, '%Y-%m-%d %H:00:00');
END$$

CREATE PROCEDURE sp_chart(IN p_sensor VARCHAR(10))
BEGIN
    SELECT t.ts, t.val, t.roll_avg, t.roll_std, t.roll_cnt,
           (a.id IS NOT NULL) AS flagged
    FROM (
        SELECT sensor, ts, val,
               AVG(val) OVER w AS roll_avg,
               STDDEV_SAMP(val) OVER w AS roll_std,
               COUNT(*) OVER w AS roll_cnt
        FROM readings
        WHERE sensor = p_sensor AND ts > NOW(3) - INTERVAL 5 MINUTE
        WINDOW w AS (ORDER BY ts ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING)
    ) t
    LEFT JOIN alerts a ON a.sensor = t.sensor AND a.ts = t.ts
    ORDER BY t.ts DESC
    LIMIT 60;
END$$

CREATE PROCEDURE sp_alerts()
BEGIN
    SELECT ts, sensor, val, z_score, severity
    FROM alerts ORDER BY ts DESC LIMIT 10;
END$$

CREATE PROCEDURE sp_get_summary()
BEGIN
    SELECT sensor, hour_start, avg_v, min_v, max_v, cnt
    FROM readings_hourly ORDER BY hour_start DESC, sensor LIMIT 8;
END$$

CREATE PROCEDURE sp_latest(IN p_a VARCHAR(10), IN p_b VARCHAR(10))
BEGIN
    SELECT ts, sensor, val
    FROM readings
    WHERE sensor IN (p_a, p_b) AND ts > NOW(3) - INTERVAL 1 MINUTE
    ORDER BY ts DESC
    LIMIT 12;
END$$

DELIMITER ;

CALL sp_maintain();