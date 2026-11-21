import json
import os
import platform
import subprocess
import threading
import tkinter as tk
from tkinter import ttk


def format_ram_gb(size_bytes):
    """メモリ用(1024進数)で綺麗にGB表記にする"""
    if not size_bytes:
        return "不明"
    gb = int(size_bytes) / (1024**3)
    if abs(gb - round(gb)) < 0.05:
        return f"{int(round(gb))}GB"
    return f"{gb:.1f}GB"


def format_ssd_size(size_bytes):
    """SSD/ストレージ用(1000進数・市販表記)でGB/TB表記にする"""
    if not size_bytes:
        return "不明"
    gb = float(size_bytes) / (1000**3)
    if gb >= 1000:
        tb = gb / 1000.0
        if abs(tb - round(tb)) < 0.05:
            return f"{int(round(tb))}TB"
        return f"{tb:.1f}TB"
    if abs(gb - round(gb)) < 5:
        # 512.1GB -> 512GB のように丸める
        return f"{int(round(gb))}GB"
    return f"{int(round(gb))}GB"


def clean_str(s):
    return " ".join((s or "").split())


def get_windows_specs_dict():
    ps_script = r"""
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $cpu = @(Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors)
    $gpu = @(Get-CimInstance Win32_VideoController | Select-Object Name)
    $ram = @(Get-CimInstance Win32_PhysicalMemory | Select-Object Capacity, Speed)
    try {
        $disk = @(Get-PhysicalDisk | Select-Object FriendlyName, MediaType, BusType, Size)
    } catch {
        $disk = @(Get-CimInstance Win32_DiskDrive | Select-Object @{N='FriendlyName';E={$_.Model}}, @{N='MediaType';E={'不明'}}, @{N='BusType';E={$_.InterfaceType}}, Size)
    }
    @{
        cpu = $cpu
        gpu = $gpu
        ram = $ram
        disk = $disk
    } | ConvertTo-Json -Depth 4
    """

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        creationflags=creationflags,
        check=True,
    )
    data = json.loads(result.stdout)

    # CPU
    cpu_list = []
    for c in data.get("cpu", []):
        name = clean_str(c.get("Name")) or "不明"
        cores = c.get("NumberOfCores", "?")
        threads = c.get("NumberOfLogicalProcessors", "?")
        cpu_list.append(f"{name} ({cores}コア/{threads}スレッド)")
    cpu_text = " / ".join(cpu_list) if cpu_list else "取得不可"

    # GPU
    gpu_list = [clean_str(g.get("Name")) for g in data.get("gpu", []) if clean_str(g.get("Name"))]
    gpu_text = " / ".join(gpu_list) if gpu_list else "取得不可"

    # メモリ
    rams = data.get("ram", [])
    if rams:
        total_bytes = sum(int(r.get("Capacity") or 0) for r in rams)
        caps = [format_ram_gb(r.get("Capacity")) for r in rams]
        speeds = sorted({str(r.get("Speed")) for r in rams if r.get("Speed")})

        if len(set(caps)) == 1:
            detail = f"{caps[0]}×{len(rams)}枚"
        else:
            detail = f"{'+'.join(caps)} / {len(rams)}枚"

        speed_str = f" / {'・'.join(speeds)}MHz" if speeds else ""
        ram_text = f"{format_ram_gb(total_bytes)} ({detail}{speed_str})"
    else:
        ram_text = "取得不可"

    # SSD / ストレージ
    disk_list = []
    for d in data.get("disk", []):
        name = clean_str(d.get("FriendlyName")) or "不明"
        mtype = d.get("MediaType") or ""
        bus = d.get("BusType") or ""
        size_str = format_ssd_size(d.get("Size"))

        tags = [t for t in [mtype, bus] if t and t not in ("Unspecified", "不明")]
        tag_str = f" [{'/'.join(tags)}]" if tags else ""
        disk_list.append(f"{name}{tag_str} ({size_str})")
    ssd_text = "\n".join(disk_list) if disk_list else "取得不可"

    return {
        "cpu": cpu_text,
        "gpu": gpu_text,
        "ram": ram_text,
        "ssd": ssd_text,
    }


def get_mac_specs_dict():
    res = subprocess.run(
        ["system_profiler", "SPHardwareDataType", "SPDisplaysDataType", "SPStorageDataType", "-json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    data = json.loads(res.stdout)
    hw = data.get("SPHardwareDataType", [{}])[0]

    cpu_name = hw.get("chip_type") or hw.get("cpu_type") or "不明"
    cores = hw.get("number_of_processors", "")
    cpu_text = f"{cpu_name} ({cores}コア)" if cores else cpu_name

    gpus = [g.get("sppci_model", "不明") for g in data.get("SPDisplaysDataType", [])]
    gpu_text = " / ".join(gpus) if gpus else "取得不可"

    ram_text = hw.get("physical_memory", "取得不可")

    ssds = []
    for s in data.get("SPStorageDataType", []):
        name = s.get("_name", "不明")
        size = format_ssd_size(s.get("size_in_bytes"))
        ssds.append(f"{name} ({size})")
    ssd_text = "\n".join(ssds) if ssds else "取得不可"

    return {
        "cpu": cpu_text,
        "gpu": gpu_text,
        "ram": ram_text,
        "ssd": ssd_text,
    }


def collect_specs_dict():
    system = platform.system()
    if system == "Windows":
        return get_windows_specs_dict()
    elif system == "Darwin":
        return get_mac_specs_dict()
    return {
        "cpu": f"{platform.machine()} ({os.cpu_count()}スレッド)",
        "gpu": "非対応OS",
        "ram": "非対応OS",
        "ssd": "非対応OS",
    }


class GFormSpecApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PCスペック取得（Googleフォーム入力用）")
        self.root.geometry("680x440")
        self.root.minsize(560, 380)

        self.font_family = "Yu Gothic UI" if platform.system() == "Windows" else "TkDefaultFont"
        self.specs = {"cpu": "", "gpu": "", "ram": "", "ssd": ""}
        self.widgets = {}
        self.status_timer = None

        main_frame = ttk.Frame(root, padding=14)
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            main_frame,
            text="各「コピー」ボタンを押して、Googleフォームの該当欄に貼り付け (Ctrl+V) してください",
            font=(self.font_family, 10, "bold"),
        ).pack(anchor=tk.W, pady=(0, 12))

        fields = [
            ("cpu", "CPU", 1),
            ("gpu", "GPU", 2),
            ("ram", "メモリ", 1),
            ("ssd", "SSD / ストレージ", 3),
        ]

        for key, label, height in fields:
            row = ttk.Frame(main_frame)
            row.pack(fill=tk.X, pady=5)

            lbl = ttk.Label(row, text=label, width=16, font=(self.font_family, 10, "bold"))
            lbl.pack(side=tk.LEFT, anchor=tk.N, pady=4)

            txt = tk.Text(
                row,
                height=height,
                font=(self.font_family, 10),
                wrap=tk.WORD,
                padx=6,
                pady=4,
                relief=tk.SOLID,
                borderwidth=1,
            )
            txt.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

            btn = ttk.Button(
                row,
                text="コピー",
                width=10,
                command=lambda k=key: self.copy_item(k),
            )
            btn.pack(side=tk.RIGHT, anchor=tk.N)

            self.widgets[key] = (txt, btn)

        # 下部コントロールエリア
        bottom = ttk.Frame(main_frame)
        bottom.pack(fill=tk.X, pady=(16, 0))

        self.reload_btn = ttk.Button(bottom, text="再取得", command=self.load_specs)
        self.reload_btn.pack(side=tk.LEFT)

        self.status_label = ttk.Label(bottom, text="", font=(self.font_family, 9, "bold"), foreground="#0078D7")
        self.status_label.pack(side=tk.LEFT, padx=12)

        self.copy_all_btn = ttk.Button(
            bottom,
            text="全項目をまとめてコピー（自由記述欄用）",
            command=self.copy_all,
        )
        self.copy_all_btn.pack(side=tk.RIGHT)

        self.load_specs()

    def load_specs(self):
        self.reload_btn.config(state=tk.DISABLED)
        self.copy_all_btn.config(state=tk.DISABLED)
        self.set_status("スペックを取得中...", auto_clear=False)

        for txt, btn in self.widgets.values():
            btn.config(state=tk.DISABLED)
            txt.config(state=tk.NORMAL)
            txt.delete("1.0", tk.END)
            txt.insert("1.0", "読み込み中...")
            txt.config(state=tk.DISABLED)

        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        try:
            res = collect_specs_dict()
            self.root.after(0, self._on_loaded, res, None)
        except Exception as e:
            self.root.after(0, self._on_loaded, None, str(e))

    def _on_loaded(self, res, error):
        if error:
            self.set_status(f"エラー: {error}", auto_clear=False)
            for txt, _ in self.widgets.values():
                txt.config(state=tk.NORMAL)
                txt.delete("1.0", tk.END)
                txt.insert("1.0", "取得失敗")
                txt.config(state=tk.DISABLED)
        else:
            self.specs = res
            for key, (txt, btn) in self.widgets.items():
                txt.config(state=tk.NORMAL)
                txt.delete("1.0", tk.END)
                txt.insert("1.0", res[key])
                txt.config(state=tk.DISABLED)
                btn.config(state=tk.NORMAL)
            self.copy_all_btn.config(state=tk.NORMAL)
            self.set_status("取得完了！")

        self.reload_btn.config(state=tk.NORMAL)

    def copy_to_clip(self, text, msg):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.set_status(msg)

    def copy_item(self, key):
        names = {"cpu": "CPU", "gpu": "GPU", "ram": "メモリ", "ssd": "SSD"}
        val = self.widgets[key][0].get("1.0", tk.END).strip()
        self.copy_to_clip(val, f"✓ {names[key]} をコピーしました")

    def copy_all(self):
        lines = [
            f"CPU: {self.specs['cpu']}",
            f"GPU: {self.specs['gpu']}",
            f"メモリ: {self.specs['ram']}",
            f"SSD: {self.specs['ssd'].replace(chr(10), ' / ')}",
        ]
        self.copy_to_clip("\n".join(lines), "✓ 全項目をまとめてコピーしました")

    def set_status(self, text, auto_clear=True):
        if self.status_timer:
            self.root.after_cancel(self.status_timer)
            self.status_timer = None
        self.status_label.config(text=text)
        if auto_clear:
            self.status_timer = self.root.after(2000, lambda: self.status_label.config(text=""))


if __name__ == "__main__":
    root = tk.Tk()
    app = GFormSpecApp(root)
    root.mainloop()
