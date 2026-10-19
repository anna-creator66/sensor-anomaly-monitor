import tkinter as tk
from tkinter import ttk, messagebox
import backend

BG = "#0f172a"
CARD = "#1e293b"
LINE = "#334155"
TEXT = "#e2e8f0"
MUTED = "#94a3b8"
BAND = "#1e4455"
ACCENT = "#38bdf8"
RED = "#ef4444"
COLORS = {"Heat": "#fb923c", "Light": "#38bdf8", "Humidity": "#4ade80", "Pressure": "#c084fc"}


class Chart:
    def __init__(self, parent):
        self.sensor = None
        self.unit = ""
        self.color = ACCENT
        self.rows = []
        self.frame = tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        head = tk.Frame(self.frame, bg=CARD)
        head.pack(fill="x", padx=12, pady=(10, 0))
        self.title = tk.Label(head, bg=CARD, fg=TEXT, font=("Segoe UI", 13, "bold"))
        self.title.pack(side="left")
        self.sub = tk.Label(head, bg=CARD, fg=MUTED, font=("Segoe UI", 10))
        self.sub.pack(side="right")
        self.value = tk.Label(self.frame, bg=CARD, font=("Segoe UI", 24, "bold"), anchor="w")
        self.value.pack(fill="x", padx=12)
        self.canvas = tk.Canvas(self.frame, bg=CARD, height=230, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.canvas.bind("<Configure>", lambda e: self.draw())

    def set_sensor(self, name):
        self.sensor = name
        self.unit = backend.SENSORS[name]["unit"]
        self.color = COLORS[name]
        self.rows = []
        self.title.config(text=name + " sensor")
        self.value.config(text="--", fg=self.color)
        self.sub.config(text="")
        self.draw()

    def update(self, rows):
        self.rows = rows
        if rows:
            last = rows[-1]
            sd = last["roll_std"]
            self.value.config(text="%.1f %s" % (last["val"], self.unit))
            self.sub.config(text="Rolling std dev: %s" % ("-" if sd is None else "%.2f" % sd))
        self.draw()

    def draw(self):
        c = self.canvas
        c.delete("all")
        if not self.sensor:
            return
        w, h = c.winfo_width(), c.winfo_height()
        rows = self.rows
        if len(rows) < 2:
            c.create_text(w / 2, h / 2, text="Collecting data...", fill=MUTED)
            return
        z = backend.params["z"]
        left, right, top, bottom = 55, 15, 12, 26
        vals = [r["val"] for r in rows]
        lo, hi = min(vals), max(vals)
        pad = (hi - lo) * 0.15 or 1
        lo, hi = lo - pad, hi + pad
        step = (w - left - right) / (len(rows) - 1)

        def x(i):
            return left + i * step

        def y(v):
            v = max(lo, min(hi, v))
            return h - bottom - (v - lo) / (hi - lo) * (h - top - bottom)

        for i in range(5):
            v = lo + (hi - lo) * i / 4
            c.create_line(left, y(v), w - right, y(v), fill=LINE)
            c.create_text(left - 6, y(v), text="%.1f" % v, anchor="e", fill=MUTED)

        upper, lower = [], []
        for i, r in enumerate(rows):
            if r["roll_cnt"] >= 10:
                upper.append((x(i), y(r["roll_avg"] + z * r["roll_std"])))
                lower.append((x(i), y(r["roll_avg"] - z * r["roll_std"])))
        if len(upper) > 1:
            pts = upper + lower[::-1]
            c.create_polygon([p for xy in pts for p in xy], fill=BAND, outline="")

        line = [p for i, r in enumerate(rows) for p in (x(i), y(r["val"]))]
        c.create_line(line, fill=self.color, width=2, smooth=True)

        for i, r in enumerate(rows):
            if r["flagged"]:
                c.create_oval(x(i) - 6, y(r["val"]) - 6, x(i) + 6, y(r["val"]) + 6,
                              fill=RED, outline="white", width=2)

        c.create_text(left, h - 10, text=rows[0]["ts"].strftime("%H:%M:%S"),
                      anchor="w", fill=MUTED)
        c.create_text(w - right, h - 10, text=rows[-1]["ts"].strftime("%H:%M:%S"),
                      anchor="e", fill=MUTED)


class App:
    def __init__(self, root):
        self.root = root
        self.running = True
        root.title("Sensor Anomaly Monitor")
        root.geometry("1150x780")
        root.minsize(950, 680)
        root.configure(bg=BG)
        self.setup_style()

        header = tk.Frame(root, bg=BG)
        header.pack(fill="x", padx=16, pady=(14, 4))
        tk.Label(header, text="Sensor Anomaly Monitor", bg=BG, fg=TEXT,
                 font=("Segoe UI", 20, "bold")).pack(side="left")
        tk.Label(header, text="  live z-score detection on MySQL", bg=BG, fg=MUTED,
                 font=("Segoe UI", 11)).pack(side="left", pady=(8, 0))
        self.status = tk.Label(header, text="", bg=BG, fg=RED, font=("Segoe UI", 10))
        self.status.pack(side="right")

        bar = tk.Frame(root, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        bar.pack(fill="x", padx=16, pady=8)
        self.btn = self.button(bar, "Pause", self.toggle)
        self.btn.pack(side="left", padx=10, pady=10)

        names = list(backend.SENSORS)
        self.v1 = tk.StringVar(value=backend.active[0])
        self.v2 = tk.StringVar(value=backend.active[1])
        self.label(bar, "Chart 1").pack(side="left", padx=(12, 4))
        c1 = ttk.Combobox(bar, textvariable=self.v1, values=names, width=10, state="readonly")
        c1.pack(side="left")
        c1.bind("<<ComboboxSelected>>", lambda e: self.sensors_changed(1))
        self.label(bar, "Chart 2").pack(side="left", padx=(12, 4))
        c2 = ttk.Combobox(bar, textvariable=self.v2, values=names, width=10, state="readonly")
        c2.pack(side="left")
        c2.bind("<<ComboboxSelected>>", lambda e: self.sensors_changed(2))

        self.spike1 = self.button(bar, "", lambda: backend.inject_spike(self.v1.get()), RED)
        self.spike1.pack(side="left", padx=(20, 4))
        self.spike2 = self.button(bar, "", lambda: backend.inject_spike(self.v2.get()), RED)
        self.spike2.pack(side="left", padx=4)

        self.z = tk.Scale(bar, from_=2, to=6, resolution=0.5, orient="horizontal", length=140,
                          command=lambda v: backend.set_z(v), bg=CARD, fg=TEXT,
                          troughcolor=BG, highlightthickness=0, bd=0, activebackground=ACCENT)
        self.z.set(4)
        self.z.pack(side="right", padx=10)
        self.label(bar, "Alert if |z| above").pack(side="right")

        mid = tk.Frame(root, bg=BG)
        mid.pack(fill="both", expand=True, padx=12)
        mid.rowconfigure(0, weight=1)
        self.charts = []
        for i in range(2):
            mid.columnconfigure(i, weight=1, uniform="c")
            chart = Chart(mid)
            chart.frame.grid(row=0, column=i, sticky="nsew", padx=4)
            self.charts.append(chart)

        bottom = tk.Frame(root, bg=BG)
        bottom.pack(fill="x", padx=12, pady=(8, 14))
        self.t_alert = self.make_tree(bottom, 0, "Alerts",
                                      ("Time", "Sensor", "Value", "z", "Level"), 3)
        self.t_read = self.make_tree(bottom, 1, "Latest readings",
                                     ("Time", "Sensor", "Value"), 2)
        self.t_sum = self.make_tree(bottom, 2, "Hourly summary",
                                    ("Sensor", "Hour", "Avg", "Min", "Max", "Count"), 4)

        self.apply_sensors()
        self.refresh()

    def setup_style(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT,
                    rowheight=24, borderwidth=0)
        s.configure("Treeview.Heading", background=LINE, foreground=TEXT, relief="flat",
                    font=("Segoe UI", 9, "bold"))
        s.map("Treeview", background=[("selected", LINE)])
        s.map("Treeview.Heading", background=[("active", LINE)])
        s.configure("TCombobox", fieldbackground=CARD, background=LINE, foreground=TEXT,
                    arrowcolor=TEXT, bordercolor=LINE)
        s.map("TCombobox", fieldbackground=[("readonly", CARD)],
              foreground=[("readonly", TEXT)])
        self.root.option_add("*TCombobox*Listbox.background", CARD)
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT)

    def label(self, parent, text):
        return tk.Label(parent, text=text, bg=CARD, fg=MUTED, font=("Segoe UI", 10))

    def button(self, parent, text, cmd, color=ACCENT):
        return tk.Button(parent, text=text, command=cmd, bg=color, fg="white", bd=0,
                         relief="flat", padx=14, pady=6, cursor="hand2",
                         font=("Segoe UI", 10, "bold"), activebackground=LINE,
                         activeforeground="white")

    def make_tree(self, parent, col, title, cols, weight):
        card = tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        card.grid(row=0, column=col, sticky="nsew", padx=4)
        parent.columnconfigure(col, weight=weight, uniform="b")
        tk.Label(card, text=title, bg=CARD, fg=TEXT,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=10, pady=(8, 2))
        tree = ttk.Treeview(card, columns=cols, show="headings", height=7)
        for name in cols:
            tree.heading(name, text=name)
            tree.column(name, width=50, anchor="center")
        tree.tag_configure("HIGH", foreground="#f87171")
        tree.tag_configure("LOW", foreground="#fbbf24")
        tree.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        return tree

    def fill(self, tree, rows, tags=None):
        tree.delete(*tree.get_children())
        for i, r in enumerate(rows):
            tree.insert("", "end", values=r, tags=(tags[i],) if tags else ())

    def sensors_changed(self, which):
        if self.v1.get() == self.v2.get():
            other = [n for n in backend.SENSORS if n != self.v1.get()][0]
            (self.v2 if which == 1 else self.v1).set(other)
        self.apply_sensors()

    def apply_sensors(self):
        names = [self.v1.get(), self.v2.get()]
        backend.set_active(names)
        for chart, name in zip(self.charts, names):
            if chart.sensor != name:
                chart.set_sensor(name)
        self.spike1.config(text="Spike " + names[0])
        self.spike2.config(text="Spike " + names[1])

    def toggle(self):
        if self.running:
            backend.stop()
            self.btn.config(text="Resume")
        else:
            backend.start()
            self.btn.config(text="Pause")
        self.running = not self.running

    def refresh(self):
        errors = []
        for chart in self.charts:
            try:
                chart.update(backend.get_chart(chart.sensor))
            except Exception as e:
                errors.append(str(e))
        try:
            alerts = backend.get_alerts()
            self.fill(self.t_alert, [
                (a["ts"].strftime("%H:%M:%S"), a["sensor"], "%.1f" % a["val"],
                 "%.1f" % a["z_score"], a["severity"]) for a in alerts],
                [a["severity"] for a in alerts])
        except Exception as e:
            errors.append(str(e))
        try:
            self.fill(self.t_read, [
                (r["ts"].strftime("%H:%M:%S"), r["sensor"],
                 "%.1f %s" % (r["val"], backend.SENSORS[r["sensor"]]["unit"]))
                for r in backend.get_latest()])
        except Exception as e:
            errors.append(str(e))
        try:
            self.fill(self.t_sum, [
                (s["sensor"], s["hour_start"].strftime("%d %b %H:00"), "%.1f" % s["avg_v"],
                 "%.1f" % s["min_v"], "%.1f" % s["max_v"], s["cnt"])
                for s in backend.get_summary()])
        except Exception as e:
            errors.append(str(e))
        self.status.config(text="Error: %s" % errors[0] if errors else "")
        self.root.after(2000, self.refresh)

if __name__ == "__main__":
    root = tk.Tk()
    try:
        backend.start()
    except Exception as e:
        messagebox.showerror("Startup error",
                             "%s\n\nHave you run schema.sql in MySQL?" % e)
        root.destroy()
        raise SystemExit
    App(root)
    root.mainloop()