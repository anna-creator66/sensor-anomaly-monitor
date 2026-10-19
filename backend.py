import os
import sys
import threading
import time
import random
import configparser
import mysql.connector

BASE = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) \
    else os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE, "config.ini")

SENSORS = {
    "Heat": {"unit": "°C", "base": 30.0, "noise": 0.5, "spike": (6, 12)},
    "Light": {"unit": "lux", "base": 500.0, "noise": 8.0, "spike": (80, 160)},
    "Humidity": {"unit": "%", "base": 55.0, "noise": 1.0, "spike": (12, 22)},
    "Pressure": {"unit": "hPa", "base": 1013.0, "noise": 1.5, "spike": (15, 30)},
}
CFG = {}
params = {"z": 4.0}
active = ["Heat", "Light"]
running = threading.Event()
worker = None


def load_config():
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w") as f:
            f.write("[mysql]\nhost = localhost\nuser = root\npassword =\n"
                    "database = sensor_demo\n")
        raise FileNotFoundError(
            "config.ini was created at " + CONFIG_FILE +
            ". Put your MySQL password in it and start the app again.")
    cp = configparser.ConfigParser()
    cp.read(CONFIG_FILE)
    s = cp["mysql"]
    return {
        "host": s.get("host", "localhost"),
        "user": s.get("user", "root"),
        "password": os.environ.get("DB_PASSWORD", s.get("password", "")),
        "database": s.get("database", "sensor_demo"),
    }


def call(proc, args=()):
    conn = mysql.connector.connect(**CFG)
    try:
        cur = conn.cursor()
        cur.callproc(proc, args)
        rows = []
        for result in cur.stored_results():
            cols = [c[0] for c in result.description]
            rows = [dict(zip(cols, r)) for r in result.fetchall()]
        conn.commit()
        cur.close()
        return rows
    finally:
        conn.close()


def insert_reading(sensor, spike=False):
    s = SENSORS[sensor]
    v = random.gauss(s["base"], s["noise"])
    if spike or random.random() < 0.01:
        v += random.uniform(*s["spike"])
    call("sp_insert_reading", (sensor, v))


def _loop():
    n = 1
    while running.is_set():
        try:
            for sensor in list(active):
                insert_reading(sensor)
            call("sp_detect", (params["z"],))
            if n % 10 == 0:
                call("sp_refresh_summary")
            if n % 60 == 0:
                call("sp_maintain")
            n += 1
        except Exception as e:
            print("backend error:", e)
        time.sleep(1)


def start():
    global worker
    if running.is_set():
        return
    CFG.update(load_config())
    call("sp_maintain")
    call("sp_refresh_summary")
    running.set()
    worker = threading.Thread(target=_loop, daemon=True)
    worker.start()


def stop():
    running.clear()
    if worker:
        worker.join()


def set_active(names):
    active[:] = list(names)


def inject_spike(sensor):
    insert_reading(sensor, spike=True)
    call("sp_detect", (params["z"],))


def set_z(z):
    params["z"] = float(z)


def get_chart(sensor):
    return call("sp_chart", (sensor,))[::-1]


def get_alerts():
    return call("sp_alerts")


def get_summary():
    return call("sp_get_summary")


def get_latest():
    return call("sp_latest", (active[0], active[-1]))